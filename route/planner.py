"""The route engine: a cost map from the layers and a minimum-cost path through it.

Every cell costs the seconds it takes to walk across it. Cells that break a hard
limit are left out of the walking graph, so the path search never enters them and no
returned route can break one.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Sequence
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
    grid: CostGrid,
    start: Point,
    goal: Point,
    habitat: Point,
    limits: Limits,
    *,
    mode: str = "fastest",
    daylight_s: float | None = None,
    targets: Sequence[Point] = (),
) -> RouteResponse:
    """The crew's fastest safe route, the science alternative through targets, or the cart's
    route, by mode.

    daylight_s is the time from the walk's start to sunset. The cart cannot cross a ridge,
    and the walk-back rule and daylight limit are crew rules, so they don't apply to it.
    """
    cart = mode == "cart"
    blocked = blocked_cells(grid, habitat, limits)
    if cart:
        blocked |= grid.ridge
    if grid.cell(start) == grid.cell(goal):
        raise HTTPException(422, "start and goal are in the same planning cell")
    walk_s = _walk_seconds_per_cell(grid, limits.planning_speed_kmh)
    field = _Field(grid, walk_s, blocked, [habitat, start, *targets])
    rules = _Rules(habitat, limits, daylight_s, cart)
    fastest = _respond(grid, rules, _route(field, [start, goal]), "cart" if cart else "fastest")
    if mode != "science":
        return fastest

    # Walking times between every pair of waypoints, worked out once (indexes into stops).
    stops = [start, *targets, goal]
    hop_s = {
        (i, j): field.time(stops[i], stops[j])
        for i in range(len(stops) - 1)
        for j in range(1, len(stops))
        if i != j
    }

    def tour_s(order: Sequence[int]) -> float:
        visits = [0, *order, len(stops) - 1]
        return sum(hop_s[a, b] for a, b in zip(visits, visits[1:], strict=False))

    def keeps_limits(waypoints: Sequence[Point]) -> RouteResponse | None:
        try:
            return _respond(grid, rules, _route(field, waypoints), "science")
        except NoSafeRoute:
            return None

    # Only a target the crew could visit on its own, within every hard limit, is a candidate.
    chosen = [i for i in range(1, len(stops) - 1) if keeps_limits([start, stops[i], goal])]
    while chosen:
        order = min(itertools.permutations(chosen), key=tour_s)
        science = keeps_limits([start, *(stops[i] for i in order), goal])
        if science is not None:
            break
        # Drop the target whose visit costs the most time, then try again.
        chosen.remove(min(order, key=lambda t: tour_s([i for i in order if i != t])))
    else:
        science = fastest.model_copy(update={"mode": "science"})
    return science.model_copy(
        update={"extra_time_vs_fastest_s": science.total_time_s - fastest.total_time_s}
    )


@dataclass(frozen=True)
class _Rules:
    """Who walks the route and the hard limits it must keep."""

    habitat: Point
    limits: Limits
    daylight_s: float | None
    cart: bool


class _Field:
    """The fastest walking time from each origin to every cell, with the paths behind them.

    The search runs between cell centres; the walk runs between the exact points, so the
    stretch from an exact point to its cell's centre is added at that cell's pace.
    """

    def __init__(self, grid: CostGrid, walk_s: np.ndarray, blocked: np.ndarray, origins):
        self.grid, self.origins = grid, list(origins)
        self.pace = walk_s / grid.cell_m  # seconds per metre in each cell
        self.shape = blocked.shape
        self.cells = [grid.cell(p) for p in self.origins]
        seconds, self.previous = dijkstra(
            _walking_graph(walk_s, blocked),
            directed=False,
            indices=[np.ravel_multi_index(c, self.shape) for c in self.cells],
            return_predecessors=True,
        )
        self.seconds = seconds.reshape(len(self.origins), *self.shape)

    def _origin(self, p: Point) -> int:
        return next(i for i, o in enumerate(self.origins) if o == p)

    def _to_centre_s(self, p: Point, cell: tuple[int, int]) -> float:
        return _metres(p, self.grid.centre(*cell)) * self.pace[cell]

    def time(self, origin: Point, p: Point) -> float:
        """Seconds from an origin to any exact point."""
        i, cell = self._origin(origin), self.grid.cell(p)
        if cell == self.cells[i]:
            # The direct stretch stays inside this one cell.
            return _metres(origin, p) * self.pace[cell]
        return (
            self._to_centre_s(origin, self.cells[i])
            + self.seconds[i][cell]
            + self._to_centre_s(p, cell)
        )

    def walk(self, origin: Point, p: Point, walked_s: float) -> list[tuple[Point, float]]:
        """The points from an origin to p, each with the time walked to it."""
        i, cell = self._origin(origin), self.grid.cell(p)
        if cell == self.cells[i]:
            return [(origin, walked_s), (p, walked_s + self.time(origin, p))]
        set_off_s = walked_s + self._to_centre_s(origin, self.cells[i])
        cells = _trace(self.previous[i], cell, self.shape)
        centres = [(self.grid.centre(*c), set_off_s + self.seconds[i][c]) for c in cells]
        return [(origin, walked_s), *centres, (p, walked_s + self.time(origin, p))]


def _route(field: _Field, waypoints: Sequence[Point]) -> list[_Stop]:
    """The stops through every waypoint in turn, each with its time walked and time home."""
    habitat = field.origins[0]
    stops: list[_Stop] = []
    for a, b in zip(waypoints, waypoints[1:], strict=False):
        if not math.isfinite(field.time(a, b)):
            raise NoSafeRoute("every path from start to goal breaks a hard limit")
        walked_s = stops[-1].walked_s if stops else 0.0
        for point, at_s in field.walk(a, b, walked_s):
            if not stops or point != stops[-1].point:
                stops.append(_Stop(point, at_s, field.time(habitat, point)))
    return stops


def _respond(grid: CostGrid, rules: _Rules, stops: list[_Stop], mode: str) -> RouteResponse:
    """The route as a RouteResponse, or NoSafeRoute if it breaks a hard limit."""
    limits, habitat = rules.limits, rules.habitat
    total_m = sum(_metres(a.point, b.point) for a, b in zip(stops, stops[1:], strict=False))
    total_s = stops[-1].walked_s
    max_walk_s = limits.max_walk_h * 3600
    if total_s > max_walk_s:
        raise NoSafeRoute(f"the fastest safe path takes {total_s / 3600:.1f} h")
    if not all(math.isfinite(stop.home_s) for stop in stops):
        raise NoSafeRoute("part of the route has no safe path back to the habitat")
    walk_back_margin_s = _spare_s(max_walk_s, stops)
    checks = []
    if not rules.cart:
        if walk_back_margin_s < 0:
            raise NoSafeRoute(
                "part of the route is too far to walk home within the walk-time limit"
            )
        checks.append(_check("walk_back", walk_back_margin_s, 0, "s", at_least=True))
        if rules.daylight_s is not None:
            daylight_margin_s = _spare_s(rules.daylight_s, stops)
            if daylight_margin_s < 0:
                raise NoSafeRoute("the crew could not be back at the habitat before sunset")
            checks.append(_check("daylight", daylight_margin_s, 0, "s", at_least=True))
    furthest_m = max(_metres(habitat, stop.point) for stop in stops)
    if furthest_m > limits.max_distance_from_habitat_m:
        raise NoSafeRoute(f"the route reaches {furthest_m:.0f} m from the habitat")
    steepest = max(grid.slope_deg[grid.cell(stop.point)] for stop in stops)
    return RouteResponse(
        site=grid.site,
        mode=mode,
        path=[stop.point for stop in stops],
        legs=_legs(stops),
        total_distance_m=total_m,
        total_time_s=total_s,
        walk_back_margin_s=walk_back_margin_s,
        extra_time_vs_fastest_s=None,
        limit_checks=[
            _check("slope", steepest, limits.max_slope_deg, "deg"),
            _check("distance_from_habitat", furthest_m, limits.max_distance_from_habitat_m, "m"),
            _check(
                "planning_speed",
                total_m / total_s * 3.6 if total_s else 0.0,
                limits.planning_speed_kmh,
                "km/h",
            ),
            _check("walk_time", total_s / 3600, limits.max_walk_h, "h"),
            *checks,
        ],
        checkpoints=[],
    )


@dataclass(frozen=True)
class _Stop:
    """One point of the returned path, with the time walked to it and the time home from it."""

    point: Point
    walked_s: float
    home_s: float


def _spare_s(budget_s: float, stops: list[_Stop]) -> float:
    """The least time left in a budget if the crew turned for home at any stop."""
    return min(budget_s - stop.walked_s - stop.home_s for stop in stops)


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


def _check(
    limit: str, value: float, threshold: float, units: str, *, at_least: bool = False
) -> LimitCheck:
    """A limit the value must stay under, or reach when at_least (spare time, say)."""
    value = float(value)
    passed = value >= threshold - 1e-9 if at_least else value <= threshold + 1e-9
    return LimitCheck(limit=limit, passed=passed, value=value, threshold=threshold, units=units)
