"""The route engine: a cost map from the layers and a minimum-cost path through it.

Every cell costs the seconds it takes to walk across it. Cells that break a hard
limit cost infinity, so the path search never enters them and no returned route
can break one.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from skimage.graph import MCP_Geometric

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


class NoSafeRoute(Exception):
    """No path from start to goal keeps every hard limit."""


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
    from_habitat = grid.distance_from(habitat)
    blocked = ~(grid.slope_deg <= limits.max_slope_deg)
    blocked |= from_habitat > limits.max_distance_from_habitat_m
    walk_s = _walk_seconds_per_cell(grid, limits.planning_speed_kmh)
    cost = np.where(_seal_diagonal_gaps(blocked), np.inf, walk_s)

    start_cell, goal_cell = grid.cell(start), grid.cell(goal)
    if start_cell == goal_cell:
        raise ValueError("start and goal are in the same planning cell")
    mcp = MCP_Geometric(cost)
    cumulative, _ = mcp.find_costs([start_cell], [goal_cell])
    if not np.isfinite(cumulative[goal_cell]):
        raise NoSafeRoute("every path from start to goal breaks a hard limit")
    cells = [tuple(c) for c in mcp.traceback(goal_cell)]

    path = [grid.centre(r, c) for r, c in cells]
    steps = [
        float(np.hypot(r1 - r0, c1 - c0)) * grid.cell_m
        for (r0, c0), (r1, c1) in zip(cells, cells[1:], strict=False)
    ]
    total_m = sum(steps)
    total_s = float(cumulative[goal_cell])
    max_walk_s = limits.max_walk_h * 3600
    if total_s > max_walk_s:
        raise NoSafeRoute(f"the fastest safe path takes {total_s / 3600:.1f} h")
    home, _ = MCP_Geometric(cost).find_costs([grid.cell(habitat)])
    if not all(np.isfinite(home[c]) for c in cells):
        raise NoSafeRoute("part of the route has no safe path back to the habitat")
    walk_back_margin_s = float(min(max_walk_s - cumulative[c] - home[c] for c in cells))
    if walk_back_margin_s < 0:
        raise NoSafeRoute("part of the route is too far to walk home within the walk-time limit")
    return RouteResponse(
        site=grid.site,
        mode="fastest",
        path=path,
        legs=_legs(cells, steps, cumulative),
        total_distance_m=total_m,
        total_time_s=total_s,
        walk_back_margin_s=walk_back_margin_s,
        extra_time_vs_fastest_s=None,
        limit_checks=[
            _check("slope", max(grid.slope_deg[c] for c in cells), limits.max_slope_deg, "deg"),
            _check(
                "distance_from_habitat",
                max(from_habitat[c] for c in cells),
                limits.max_distance_from_habitat_m,
                "m",
            ),
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


def _legs(cells, steps: list[float], elapsed: np.ndarray) -> list[Leg]:
    """One leg per straight run of the path."""
    moves = [(r1 - r0, c1 - c0) for (r0, c0), (r1, c1) in zip(cells, cells[1:], strict=False)]
    turns = [i for i in range(1, len(moves)) if moves[i] != moves[i - 1]]
    ends = [0, *turns, len(cells) - 1]
    return [
        Leg(
            start_index=first,
            end_index=last,
            distance_m=sum(steps[first:last]),
            time_s=float(elapsed[cells[last]] - elapsed[cells[first]]),
        )
        for first, last in zip(ends, ends[1:], strict=False)
    ]


def _walk_seconds_per_cell(grid: CostGrid, planning_speed_kmh: float) -> np.ndarray:
    seconds = (3.6 / planning_speed_kmh) * grid.cell_m
    seconds = seconds * np.exp(TOBLER_RATE * np.tan(np.radians(np.minimum(grid.slope_deg, 89))))
    seconds = np.where(grid.sand, seconds * SAND_TIME_FACTOR, seconds)
    return np.where(grid.ridge, seconds * RIDGE_TIME_FACTOR, seconds)


def _seal_diagonal_gaps(blocked: np.ndarray) -> np.ndarray:
    """Close every gap where two blocked cells touch only at a corner.

    A path may step diagonally, so it could slip between two such cells and cross a
    diagonal wall. Blocking one more cell at each such corner makes every wall solid.
    """
    sealed = blocked.copy()
    while True:
        nw, ne, sw, se = sealed[:-1, :-1], sealed[:-1, 1:], sealed[1:, :-1], sealed[1:, 1:]
        falling = nw & se & ~ne & ~sw
        rising = ne & sw & ~nw & ~se
        if not (falling.any() or rising.any()):
            return sealed
        sealed[:-1, 1:] |= falling
        sealed[:-1, :-1] |= rising


def _check(limit: str, value: float, threshold: float, units: str) -> LimitCheck:
    value = float(value)
    return LimitCheck(
        limit=limit, passed=value <= threshold + 1e-9, value=value, threshold=threshold, units=units
    )
