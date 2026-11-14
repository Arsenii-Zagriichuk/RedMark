"""The route engine: a cost map from the layers and a minimum-cost path through it.

Every cell costs the seconds it takes to walk across it. Cells that break a hard
limit are left out of the walking graph, so the path search never enters them and no
returned route can break one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from fastapi import HTTPException
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra

from contracts.models.common import Point
from contracts.models.route_request import Limits
from contracts.models.route_response import Leg, LimitCheck, RouteResponse

# Tobler's hiking function: speed falls by exp(-3.5 * tan(slope)) against flat ground. The
# slope layer has no direction, so every slope is walked as uphill, the slower case.
TOBLER_RATE = 3.5
# Loose sand takes 1.6 to 2.5 times the work of firm ground (Lejeune et al. 1998); low end.
SAND_TIME_FACTOR = 1.6
# Climbing over a 1 to 2 m boxwork ridge: a RedMark assumption, not a measured figure.
RIDGE_TIME_FACTOR = 3.0


class NoSafeRoute(HTTPException):
    """No path from start to goal keeps every hard limit.

    An HTTPException, so the service passes it to the app as a 422 with the reason.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(422, f"no safe route: {reason}")


@dataclass(frozen=True)
class CostGrid:
    """The layers on one planning grid. Row 0 is the north edge, column 0 the west edge."""

    site: str
    min_x: float
    max_y: float
    cell_m: float
    slope_deg: np.ndarray
    sand: np.ndarray
    ridge: np.ndarray

    def cell(self, p: Point) -> tuple[int, int]:
        row = int((self.max_y - p.y) // self.cell_m)
        col = int((p.x - self.min_x) // self.cell_m)
        rows, cols = self.slope_deg.shape
        if not (0 <= row < rows and 0 <= col < cols):
            raise NoSafeRoute(f"({p.x}, {p.y}) is outside the walk area")
        return row, col

    def centre(self, row: int, col: int) -> Point:
        return Point(
            x=self.min_x + (col + 0.5) * self.cell_m, y=self.max_y - (row + 0.5) * self.cell_m
        )

    def distance_from(self, p: Point) -> np.ndarray:
        """Ground metres from p to every cell centre."""
        rows, cols = self.slope_deg.shape
        y = self.max_y - (np.arange(rows) + 0.5) * self.cell_m
        x = self.min_x + (np.arange(cols) + 0.5) * self.cell_m
        return np.hypot(x[None, :] - p.x, y[:, None] - p.y)


def plan_on_grid(
    grid: CostGrid, start: Point, goal: Point, habitat: Point, limits: Limits
) -> RouteResponse:
    blocked = blocked_cells(grid, habitat, limits)
    walk_s = _walk_seconds_per_cell(grid, limits.planning_speed_kmh)

    start_cell, goal_cell, habitat_cell = grid.cell(start), grid.cell(goal), grid.cell(habitat)
    if start_cell == goal_cell:
        raise HTTPException(422, "start and goal are in the same planning cell")
    shape = blocked.shape
    seconds, previous = dijkstra(
        _walking_graph(walk_s, blocked),
        directed=False,
        indices=[np.ravel_multi_index(c, shape) for c in (start_cell, habitat_cell)],
        return_predecessors=True,
    )
    cumulative, home = seconds[0].reshape(shape), seconds[1].reshape(shape)
    if not np.isfinite(cumulative[goal_cell]):
        raise NoSafeRoute("every path from start to goal breaks a hard limit")
    cells = _trace(previous[0], goal_cell, shape)

    # The search runs between cell centres; the walk runs between the exact points, so add
    # the stretch from each exact point to its cell's centre at that cell's walking pace.
    pace = walk_s / grid.cell_m  # seconds per metre in each cell
    to_start_s = _metres(start, grid.centre(*start_cell)) * pace[start_cell]
    to_goal_s = _metres(goal, grid.centre(*goal_cell)) * pace[goal_cell]
    to_habitat_s = _metres(habitat, grid.centre(*habitat_cell)) * pace[habitat_cell]
    stops = [_Stop(start, 0.0, to_start_s + home[start_cell] + to_habitat_s)]
    for c in cells:
        stops.append(_Stop(grid.centre(*c), to_start_s + cumulative[c], home[c] + to_habitat_s))
    walked_s = stops[-1].walked_s + to_goal_s
    stops.append(_Stop(goal, walked_s, to_goal_s + home[goal_cell] + to_habitat_s))
    stops = [
        b for a, b in zip([None, *stops], stops, strict=False) if a is None or b.point != a.point
    ]

    total_m = sum(_metres(a.point, b.point) for a, b in zip(stops, stops[1:], strict=False))
    total_s = stops[-1].walked_s
    max_walk_s = limits.max_walk_h * 3600
    if total_s > max_walk_s:
        raise NoSafeRoute(f"the fastest safe path takes {total_s / 3600:.1f} h")
    if not all(np.isfinite(stop.home_s) for stop in stops):
        raise NoSafeRoute("part of the route has no safe path back to the habitat")
    walk_back_margin_s = min(max_walk_s - stop.walked_s - stop.home_s for stop in stops)
    if walk_back_margin_s < 0:
        raise NoSafeRoute("part of the route is too far to walk home within the walk-time limit")
    furthest_m = max(_metres(habitat, stop.point) for stop in stops)
    if furthest_m > limits.max_distance_from_habitat_m:
        raise NoSafeRoute(f"the route reaches {furthest_m:.0f} m from the habitat")
    return RouteResponse(
        site=grid.site,
        mode="fastest",
        path=[stop.point for stop in stops],
        legs=_legs(stops),
        total_distance_m=total_m,
        total_time_s=total_s,
        walk_back_margin_s=walk_back_margin_s,
        extra_time_vs_fastest_s=None,
        limit_checks=[
            _check("slope", max(grid.slope_deg[c] for c in cells), limits.max_slope_deg, "deg"),
            _check("distance_from_habitat", furthest_m, limits.max_distance_from_habitat_m, "m"),
            _check(
                "planning_speed",
                total_m / total_s * 3.6 if total_s else 0.0,
                limits.planning_speed_kmh,
                "km/h",
            ),
            _check("walk_time", total_s / 3600, limits.max_walk_h, "h"),
        ],
        checkpoints=[],
    )


@dataclass(frozen=True)
class _Stop:
    """One point of the returned path, with the time walked to it and the time home from it."""

    point: Point
    walked_s: float
    home_s: float


def _metres(a: Point, b: Point) -> float:
    return math.hypot(b.x - a.x, b.y - a.y)


def _legs(stops: list[_Stop]) -> list[Leg]:
    """One leg per straight run of the path."""
    moves = [
        (b.point.x - a.point.x, b.point.y - a.point.y)
        for a, b in zip(stops, stops[1:], strict=False)
    ]
    turns = [i for i in range(1, len(moves)) if not _same_direction(moves[i - 1], moves[i])]
    ends = [0, *turns, len(stops) - 1]
    return [
        Leg(
            start_index=first,
            end_index=last,
            distance_m=sum(math.hypot(*m) for m in moves[first:last]),
            time_s=stops[last].walked_s - stops[first].walked_s,
        )
        for first, last in zip(ends, ends[1:], strict=False)
    ]


def _same_direction(a: tuple[float, float], b: tuple[float, float]) -> bool:
    cross, dot = a[0] * b[1] - a[1] * b[0], a[0] * b[0] + a[1] * b[1]
    return dot > 0 and abs(cross) <= 1e-9 * math.hypot(*a) * math.hypot(*b)


def _walk_seconds_per_cell(grid: CostGrid, planning_speed_kmh: float) -> np.ndarray:
    seconds = (3.6 / planning_speed_kmh) * grid.cell_m
    seconds = seconds * np.exp(TOBLER_RATE * np.tan(np.radians(np.minimum(grid.slope_deg, 89))))
    seconds = np.where(grid.sand, seconds * SAND_TIME_FACTOR, seconds)
    return np.where(grid.ridge, seconds * RIDGE_TIME_FACTOR, seconds)


def blocked_cells(grid: CostGrid, habitat: Point, limits: Limits) -> np.ndarray:
    """Cells no route may enter: too steep, no slope data, or too far from the habitat."""
    blocked = ~(grid.slope_deg <= limits.max_slope_deg)
    return blocked | (grid.distance_from(habitat) > limits.max_distance_from_habitat_m)


# Half the 8 neighbour steps; the graph is undirected, so these cover all 8.
_STEPS = ((0, 1), (1, 0), (1, 1), (1, -1))


def _walking_graph(walk_s: np.ndarray, blocked: np.ndarray):
    """Every step between two open cells, weighted by its walking time.

    A step costs the mean of its two cells' seconds times its length in cells. A diagonal
    step between two blocked cells that touch at a corner is left out, so no path slips
    through a diagonal wall, while both open cells stay walkable.
    """
    rows, cols = blocked.shape
    index = np.arange(blocked.size).reshape(rows, cols)
    heads, tails, seconds = [], [], []
    for dr, dc in _STEPS:
        here = (slice(0, rows - dr), slice(max(0, -dc), cols - max(0, dc)))
        there = (slice(dr, rows), slice(max(0, dc), cols + min(0, dc)))
        open_step = ~blocked[here] & ~blocked[there]
        if dr and dc:
            open_step &= ~(blocked[here[0], there[1]] & blocked[there[0], here[1]])
        heads.append(index[here][open_step])
        tails.append(index[there][open_step])
        seconds.append(((walk_s[here] + walk_s[there]) / 2 * np.hypot(dr, dc))[open_step])
    return coo_matrix(
        (np.concatenate(seconds), (np.concatenate(heads), np.concatenate(tails))),
        shape=(blocked.size, blocked.size),
    ).tocsr()


def _trace(previous: np.ndarray, goal_cell: tuple[int, int], shape) -> list[tuple[int, int]]:
    """The cells from the search's start to the goal, following each cell's predecessor."""
    node, nodes = int(np.ravel_multi_index(goal_cell, shape)), []
    while node >= 0:
        nodes.append(node)
        node = int(previous[node])
    return [tuple(int(i) for i in np.unravel_index(n, shape)) for n in reversed(nodes)]


def _check(limit: str, value: float, threshold: float, units: str) -> LimitCheck:
    value = float(value)
    return LimitCheck(
        limit=limit, passed=value <= threshold + 1e-9, value=value, threshold=threshold, units=units
    )
