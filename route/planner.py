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
from scipy.ndimage import distance_transform_edt
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree

from contracts.models.common import Point
from contracts.models.route_request import Limits, Mode
from contracts.models.route_response import (
    Checkpoint as RouteCheckpoint,
)
from contracts.models.route_response import (
    Leg,
    LimitCheck,
    RouteResponse,
)
from contracts.models.route_response import (
    Mode as ResponseMode,
)

# Tobler's hiking function: speed falls by exp(-3.5 * tan(slope)) against flat ground. The
# slope layer has no direction, so every slope is walked as uphill, the slower case.
TOBLER_RATE = 3.5
# Loose sand takes 1.6 to 2.5 times the work of firm ground (Lejeune et al. 1998); low end.
SAND_TIME_FACTOR = 1.6
# Climbing over a 1 to 2 m boxwork ridge: a RedMark assumption, not a measured figure.
RIDGE_TIME_FACTOR = 3.0


# Location-aware routing: on ground with no location quality a cell's search cost is up to
# 1 + LOCATION_WEIGHT times its walking time, so the route prefers ground where fixes work.
# A RedMark choice, not a measured figure; 0 turns location-aware routing off.
LOCATION_WEIGHT = 1.0
# Person 3's checkpoint candidates are the best spot in each 500 m square, so the route looks
# for one per 500 m of route, within half a square of it.
CHECKPOINT_STRETCH_M = 500.0
CHECKPOINT_REACH_M = 250.0


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
    # Location quality (layer 5), 0 to 1: how well position finding works in each cell.
    # None when the site has none, which counts as 1 everywhere.
    quality: np.ndarray | None = None

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
    mode: Mode = Mode.fastest,
    daylight_s: float | None = None,
    targets: Sequence[Point] = (),
    uncertainty_m: float = 0.0,
    location_weight: float = LOCATION_WEIGHT,
    checkpoint_candidates: Sequence[CheckpointCandidate] = (),
) -> RouteResponse:
    """The crew's fastest safe route, the science alternative through targets, or the cart's
    route, by mode.

    The hazard margin is the uncertainty circle: no cell closer than uncertainty_m to a hazard
    is entered, so the route moves away from hazards as the circle grows.
    daylight_s is the time from the walk's start to sunset. The cart cannot cross a ridge,
    and the walk-back rule and daylight limit are crew rules, so they don't apply to it.
    Location-aware routing: the search prefers ground where location quality is high, each
    cell costing its walking time x (1 + location_weight x (1 - quality)); every reported
    time is still the walking time, and the walk home is the fastest one.
    The crew's routes visit the best checkpoint candidate near each 500 m stretch, as long as
    every hard limit still holds; the cart's route has no checkpoints.
    """
    cart = mode == Mode.cart
    hazards = Hazards(grid, limits.max_slope_deg)
    for name, point in (("start", start), ("goal", goal)):
        if hazards.metres_from(point) <= uncertainty_m:
            raise NoSafeRoute(
                f"the {name} is within the {uncertainty_m:g} m circle of a hazard: "
                "stop and take a fix"
            )
    blocked = blocked_cells(grid, habitat, limits) | (hazards.cell_metres <= uncertainty_m)
    # A diagonal step comes closest to a hazard centre at an end or at its middle, the corner
    # between the two cells; a straight step comes no closer than its ends.
    corners_blocked = hazards.corner_metres <= uncertainty_m
    if cart:
        blocked |= grid.ridge
    if grid.cell(start) == grid.cell(goal):
        raise HTTPException(422, "start and goal are in the same planning cell")
    mapped_targets: list[Point] = []
    for target in targets:
        try:
            grid.cell(target)
        except NoSafeRoute:
            continue
        mapped_targets.append(target)
    targets = mapped_targets
    walk_s = _walk_seconds_per_cell(grid, limits.planning_speed_kmh)
    search_s = walk_s
    if grid.quality is not None and location_weight:
        search_s = walk_s * (1 + location_weight * (1 - grid.quality))
    rules = _Rules(habitat, limits, daylight_s, cart, uncertainty_m, hazards)
    # One step graph for the search and one for walking time, shared by every search below.
    walk_graph = _walking_graph(walk_s, blocked, corners_blocked)
    search_graph = (
        walk_graph if search_s is walk_s else _walking_graph(search_s, blocked, corners_blocked)
    )
    field = _Field(grid, walk_s, search_graph, [start, *targets], rules)
    home = _Field(grid, walk_s, walk_graph, [habitat], rules)
    fastest = _respond(
        grid,
        rules,
        _route(field, home, [start, goal]),
        ResponseMode.cart if cart else ResponseMode.fastest,
    )

    def usable(candidate: CheckpointCandidate) -> bool:
        """On the map, on open ground and outside every hazard's circle."""
        try:
            cell = grid.cell(candidate.position)
        except NoSafeRoute:
            return False
        return not blocked[cell] and hazards.metres_from(candidate.position) > uncertainty_m

    usable_candidates = [c for c in checkpoint_candidates if usable(c)]

    def visit_checkpoints(route: RouteResponse, waypoints: list[Point]) -> RouteResponse:
        if cart or not usable_candidates:
            return route
        chosen = _checkpoints_along(route, usable_candidates)
        # How far along the route each waypoint is, each found after the one before, so the
        # waypoints keep their order and each checkpoint goes between the two it falls between.
        along, found_at, waypoint_m = _along_m(route.path), 0, []
        for w in waypoints:
            found_at = route.path.index(w, found_at)
            waypoint_m.append(along[found_at])
        last = len(waypoints) - 2

        def in_walking_order(checkpoints: list[CheckpointCandidate]) -> list[Point]:
            points: list[Point] = []
            for i in range(len(waypoints) - 1):
                if i:
                    points.append(waypoints[i])
                low, high = waypoint_m[i], waypoint_m[i + 1]
                points += [
                    c.position
                    for c, at_m in chosen
                    if c in checkpoints and low <= at_m and (at_m < high or i == last)
                ]
            return points

        visits = _Field(
            grid,
            walk_s,
            search_graph,
            [start, *waypoints[1:-1], *(c.position for c, _ in chosen)],
            rules,
        )

        def search_cost_s(points: Sequence[Point]) -> float:
            stops = [start, *points, goal]
            return sum(visits.time(a, b) for a, b in zip(stops, stops[1:], strict=False))

        checkpoints = [c for c, _ in chosen]
        while checkpoints:
            try:
                stops = _route(visits, home, [start, *in_walking_order(checkpoints), goal])
                visited = _respond(grid, rules, stops, route.mode)
            except NoSafeRoute:
                # Drop the checkpoint that costs the most to visit (in search cost: walking
                # time weighted by location quality), then try again.
                checkpoints.remove(
                    min(
                        checkpoints,
                        key=lambda c: search_cost_s(
                            in_walking_order([k for k in checkpoints if k is not c])
                        ),
                    )
                )
                continue
            return visited.model_copy(
                update={
                    "checkpoints": [
                        RouteCheckpoint(id=c.id, position=c.position) for c in checkpoints
                    ]
                }
            )
        return route

    fastest = visit_checkpoints(fastest, [start, goal])
    if mode != Mode.science:
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
            return _respond(grid, rules, _route(field, home, waypoints), ResponseMode.science)
        except NoSafeRoute:
            return None

    # Only a target the crew could visit on its own, within every hard limit, is a candidate.
    chosen = [i for i in range(1, len(stops) - 1) if keeps_limits([start, stops[i], goal])]
    while chosen:
        order = min(itertools.permutations(chosen), key=tour_s)
        science_waypoints = [start, *(stops[i] for i in order), goal]
        science = keeps_limits(science_waypoints)
        if science is not None:
            science = visit_checkpoints(science, science_waypoints)
            break
        # Drop the target whose visit costs the most time, then try again.
        chosen.remove(min(order, key=lambda t: tour_s([i for i in order if i != t])))
    else:
        science = fastest.model_copy(update={"mode": ResponseMode.science})
    return science.model_copy(
        update={"extra_time_vs_fastest_s": science.total_time_s - fastest.total_time_s}
    )


@dataclass(frozen=True)
class CheckpointCandidate:
    """A spot where a photo fix works well, from Person 3's layer 5."""

    id: str
    position: Point
    score: float


def _along_m(path: Sequence[Point]) -> list[float]:
    """Ground metres walked to each point of a path."""
    along = [0.0]
    for a, b in zip(path, path[1:], strict=False):
        along.append(along[-1] + _metres(a, b))
    return along


def _checkpoints_along(
    route: RouteResponse, candidates: Sequence[CheckpointCandidate]
) -> list[tuple[CheckpointCandidate, float]]:
    """The best-scoring candidate near each stretch of the route, with how far along it is.

    A candidate belongs to the stretch of its nearest route point; ties go to the nearer.
    """
    along = _along_m(route.path)
    best: dict[int, tuple[CheckpointCandidate, float, float]] = {}
    for candidate in candidates:
        off_m, k = min((_metres(candidate.position, p), k) for k, p in enumerate(route.path))
        if off_m > CHECKPOINT_REACH_M:
            continue
        stretch = int(along[k] // CHECKPOINT_STRETCH_M)
        held = best.get(stretch)
        if held is None or (candidate.score, -off_m) > (held[0].score, -held[2]):
            best[stretch] = (candidate, along[k], off_m)
    return sorted(((c, at_m) for c, at_m, _ in best.values()), key=lambda pair: pair[1])


@dataclass(frozen=True)
class _Rules:
    """Who walks the route and the hard limits it must keep."""

    habitat: Point
    limits: Limits
    daylight_s: float | None
    cart: bool
    uncertainty_m: float
    hazards: Hazards


class _Field:
    """The cheapest path from each origin to every cell, by search cost.

    The search runs between cell centres; the walk runs between the exact points, so the
    stretch from an exact point to its cell's centre is added at that cell's pace. With the
    search cost equal to the walking time, time() is the fastest walking time; walk() always
    reports walking time along the path found.
    """

    def __init__(self, grid: CostGrid, walk_s: np.ndarray, graph, origins, rules: _Rules):
        self.grid, self.origins = grid, list(origins)
        self.rules = rules
        self.walk_s = walk_s
        self.pace = walk_s / grid.cell_m  # seconds per metre in each cell
        self.shape = walk_s.shape
        self.cells = [grid.cell(p) for p in self.origins]
        seconds, self.previous = dijkstra(
            graph,
            directed=False,
            indices=[np.ravel_multi_index(c, self.shape) for c in self.cells],
            return_predecessors=True,
        )
        self.seconds = seconds.reshape(len(self.origins), *self.shape)

    def _origin(self, p: Point) -> int:
        return next(i for i, o in enumerate(self.origins) if o == p)

    def _keeps_hazard_margin(self, a: Point, b: Point) -> bool:
        return self.rules.hazards.metres_from_stretch(a, b) > self.rules.uncertainty_m

    def _to_centre_s(self, p: Point, cell: tuple[int, int]) -> float:
        centre = self.grid.centre(*cell)
        if not self._keeps_hazard_margin(p, centre):
            return math.inf
        return _metres(p, centre) * self.pace[cell]

    def time(self, origin: Point, p: Point) -> float:
        """Seconds from an origin to any exact point."""
        i, cell = self._origin(origin), self.grid.cell(p)
        if cell == self.cells[i] and self._keeps_hazard_margin(origin, p):
            return _metres(origin, p) * self.pace[cell]
        return (
            self._to_centre_s(origin, self.cells[i])
            + self.seconds[i][cell]
            + self._to_centre_s(p, cell)
        )

    def walk(self, origin: Point, p: Point, walked_s: float) -> list[tuple[Point, float]]:
        """The points from an origin to p, each with the time walked to it."""
        i, cell = self._origin(origin), self.grid.cell(p)
        if cell == self.cells[i] and self._keeps_hazard_margin(origin, p):
            return [(origin, walked_s), (p, walked_s + self.time(origin, p))]
        at_s = walked_s + self._to_centre_s(origin, self.cells[i])
        cells = _trace(self.previous[i], cell, self.shape)
        centres = [(self.grid.centre(*cells[0]), at_s)]
        for a, b in zip(cells, cells[1:], strict=False):
            at_s += (self.walk_s[a] + self.walk_s[b]) / 2 * math.hypot(b[0] - a[0], b[1] - a[1])
            centres.append((self.grid.centre(*b), at_s))
        return [(origin, walked_s), *centres, (p, at_s + self._to_centre_s(p, cell))]


def _route(field: _Field, home: _Field, waypoints: Sequence[Point]) -> list[_Stop]:
    """The stops through every waypoint in turn, each with its time walked and time home."""
    habitat = home.origins[0]
    stops: list[_Stop] = []
    for a, b in zip(waypoints, waypoints[1:], strict=False):
        if not math.isfinite(field.time(a, b)):
            raise NoSafeRoute("every path from start to goal breaks a hard limit")
        walked_s = stops[-1].walked_s if stops else 0.0
        for point, at_s in field.walk(a, b, walked_s):
            if not stops or point != stops[-1].point:
                stops.append(_Stop(point, at_s, home.time(habitat, point)))
    return stops


def _respond(
    grid: CostGrid, rules: _Rules, stops: list[_Stop], mode: ResponseMode
) -> RouteResponse:
    """The route as a RouteResponse, or NoSafeRoute if it breaks a hard limit."""
    limits, habitat = rules.limits, rules.habitat
    total_m = sum(_metres(a.point, b.point) for a, b in zip(stops, stops[1:], strict=False))
    total_s = stops[-1].walked_s
    max_walk_s = limits.max_walk_h * 3600
    if total_s > max_walk_s:
        raise NoSafeRoute(f"the fastest safe path takes {total_s / 3600:.1f} h")
    home_reachable = all(math.isfinite(stop.home_s) for stop in stops)
    if not home_reachable and not rules.cart:
        raise NoSafeRoute("part of the route has no safe path back to the habitat")
    walk_back_margin_s = _spare_s(max_walk_s, stops) if home_reachable else 0.0
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
    # With no hazard on the map, the nearest is no closer than across the whole walk area.
    nearest_hazard_m = min(
        rules.hazards.metres_from_stretch(a.point, b.point)
        for a, b in zip(stops, stops[1:], strict=False)
    )
    if nearest_hazard_m <= rules.uncertainty_m:
        raise NoSafeRoute(
            f"the route comes within {nearest_hazard_m:.1f} m of a hazard, inside the "
            f"{rules.uncertainty_m:g} m circle"
        )
    walk_area_m = math.hypot(*rules.hazards.cell_metres.shape) * grid.cell_m
    nearest_hazard_m = min(nearest_hazard_m, walk_area_m)
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
            _check("hazard_margin", nearest_hazard_m, rules.uncertainty_m, "m", at_least=True),
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


class Hazards:
    """The hazards on a grid: cells steeper than the slope limit or with no slope data.

    Each hazard sits at its cell's centre. Distances to the cell centres and to the corners
    between cells come from one distance transform on a half-cell lattice; distances from
    exact points and stretches of route come from the hazard centres themselves.
    """

    def __init__(self, grid: CostGrid, max_slope_deg: float):
        hazard = ~(grid.slope_deg <= max_slope_deg)
        rows, cols = hazard.shape
        self.found = bool(hazard.any())
        if not self.found:
            self.cell_metres = np.full(hazard.shape, np.inf)
            self.corner_metres = np.full((rows - 1, cols - 1), np.inf)
            return
        lattice = np.zeros((2 * rows - 1, 2 * cols - 1), dtype=bool)
        lattice[::2, ::2] = hazard
        metres = distance_transform_edt(~lattice) * grid.cell_m / 2
        self.cell_metres, self.corner_metres = metres[::2, ::2], metres[1::2, 1::2]
        hazard_rows, hazard_cols = np.nonzero(hazard)
        self._centres = cKDTree(
            np.column_stack(
                [
                    grid.min_x + (hazard_cols + 0.5) * grid.cell_m,
                    grid.max_y - (hazard_rows + 0.5) * grid.cell_m,
                ]
            )
        )

    def metres_from(self, p: Point) -> float:
        """Ground metres from an exact point to the nearest hazard; infinite with none."""
        if not self.found:
            return math.inf
        return float(self._centres.query([p.x, p.y])[0])

    def metres_from_stretch(self, a: Point, b: Point) -> float:
        """Ground metres from the straight stretch a to b to the nearest hazard."""
        if not self.found:
            return math.inf
        if a == b:
            return self.metres_from(a)
        middle = np.array([(a.x + b.x) / 2, (a.y + b.y) / 2])
        # Any hazard nearer the stretch than the one nearest its middle lies within this
        # radius of the middle.
        reach = self._centres.query(middle)[0] + _metres(a, b) / 2
        near = self._centres.data[self._centres.query_ball_point(middle, reach)]
        start, step = np.array([a.x, a.y]), np.array([b.x - a.x, b.y - a.y])
        length_sq = float(step @ step)
        t = (near - start) @ step / length_sq
        closest = start + np.clip(t, 0.0, 1.0)[:, None] * step
        return float(np.min(np.hypot(*(near - closest).T)))


def blocked_cells(grid: CostGrid, habitat: Point, limits: Limits) -> np.ndarray:
    """Cells no route may enter: too steep, no slope data, or too far from the habitat."""
    blocked = ~(grid.slope_deg <= limits.max_slope_deg)
    return blocked | (grid.distance_from(habitat) > limits.max_distance_from_habitat_m)


# Half the 8 neighbour steps; the graph is undirected, so these cover all 8.
_STEPS = ((0, 1), (1, 0), (1, 1), (1, -1))


def _walking_graph(walk_s: np.ndarray, blocked: np.ndarray, corners_blocked: np.ndarray):
    """Every step between two open cells, weighted by its walking time.

    A step costs the mean of its two cells' seconds times its length in cells. A diagonal
    step between two blocked cells that touch at a corner is left out, so no path slips
    through a diagonal wall, while both open cells stay walkable. So is a diagonal step
    across a blocked corner (one too close to a hazard).
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
            # Both diagonals of a 2 x 2 block cross the same corner, (r + 0.5, c + 0.5) for a
            # step down-right from (r, c) and (r + 0.5, c - 0.5) for one down-left.
            open_step &= ~corners_blocked
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
