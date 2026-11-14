"""The route engine on tiny made-up grids: the best path and every hard limit."""

import numpy as np
import pytest
from fastapi import HTTPException

from contracts.models.common import Point
from contracts.models.route_request import Limits
from route.planner import CostGrid, NoSafeRoute, plan_on_grid

DEFAULT_LIMITS = Limits(
    max_slope_deg=20, max_distance_from_habitat_m=2000, planning_speed_kmh=2, max_walk_h=6
)


def grid(slope_deg, cell_m=1.0, sand=None, ridge=None) -> CostGrid:
    slope = np.asarray(slope_deg, dtype=float)
    blank = np.zeros(slope.shape, dtype=bool)
    return CostGrid(
        site="gale",
        min_x=0.0,
        max_y=slope.shape[0] * cell_m,
        cell_m=cell_m,
        slope_deg=slope,
        sand=blank if sand is None else np.asarray(sand, dtype=bool),
        ridge=blank if ridge is None else np.asarray(ridge, dtype=bool),
    )


def centre(g: CostGrid, row: int, col: int) -> Point:
    return Point(x=g.min_x + (col + 0.5) * g.cell_m, y=g.max_y - (row + 0.5) * g.cell_m)


def cells(g: CostGrid, path) -> list[tuple[int, int]]:
    return [
        (round((g.max_y - p.y) / g.cell_m - 0.5), round((p.x - g.min_x) / g.cell_m - 0.5))
        for p in path
    ]


def check(response, limit: str):
    return next(c for c in response.limit_checks if c.limit == limit)


def test_route_goes_through_the_only_gap_in_a_steep_wall():
    slope = np.zeros((7, 7))
    slope[:6, 3] = 30
    g = grid(slope)

    route = plan_on_grid(g, centre(g, 1, 0), centre(g, 1, 6), centre(g, 6, 0), DEFAULT_LIMITS)

    visited = cells(g, route.path)
    assert (6, 3) in visited
    assert not any(col == 3 and row < 6 for row, col in visited)
    assert visited[0] == (1, 0) and visited[-1] == (1, 6)


def eighteen_degree_band_with_flat_gap() -> CostGrid:
    slope = np.zeros((7, 7))
    slope[:6, 3] = 18
    return grid(slope)


def test_twenty_degree_limit_crosses_an_eighteen_degree_band():
    g = eighteen_degree_band_with_flat_gap()

    route = plan_on_grid(g, centre(g, 1, 0), centre(g, 1, 6), centre(g, 6, 0), DEFAULT_LIMITS)

    assert (6, 3) not in cells(g, route.path)
    slope = check(route, "slope")
    assert (slope.passed, slope.value, slope.threshold, slope.units) == (True, 18, 20, "deg")


def test_fifteen_degree_limit_detours_round_an_eighteen_degree_band():
    g = eighteen_degree_band_with_flat_gap()
    limits = DEFAULT_LIMITS.model_copy(update={"max_slope_deg": 15})

    route = plan_on_grid(g, centre(g, 1, 0), centre(g, 1, 6), centre(g, 6, 0), limits)

    assert (6, 3) in cells(g, route.path)
    slope = check(route, "slope")
    assert (slope.passed, slope.value, slope.threshold) == (True, 0, 15)


def test_no_route_when_every_path_is_too_steep():
    g = grid(np.full((7, 7), 25.0))

    with pytest.raises(NoSafeRoute):
        plan_on_grid(g, centre(g, 1, 0), centre(g, 1, 6), centre(g, 6, 0), DEFAULT_LIMITS)


def flat_kilometre() -> tuple[CostGrid, Point, Point]:
    g = grid(np.zeros((3, 101)), cell_m=10.0)
    return g, centre(g, 1, 0), centre(g, 1, 100)


def test_flat_kilometre_at_two_kmh_takes_half_an_hour():
    g, start, goal = flat_kilometre()

    route = plan_on_grid(g, start, goal, start, DEFAULT_LIMITS)

    assert route.total_distance_m == pytest.approx(1000)
    assert route.total_time_s == pytest.approx(1800)
    assert sum(leg.time_s for leg in route.legs) == pytest.approx(1800)
    walk = check(route, "walk_time")
    assert (walk.passed, walk.value, walk.threshold, walk.units) == (True, 0.5, 6, "h")
    speed = check(route, "planning_speed")
    assert (speed.passed, speed.threshold, speed.units) == (True, 2, "km/h")
    assert speed.value == pytest.approx(2)


def test_no_route_when_the_walk_takes_longer_than_the_walk_time_limit():
    g, start, goal = flat_kilometre()
    limits = DEFAULT_LIMITS.model_copy(update={"max_walk_h": 0.25})

    with pytest.raises(NoSafeRoute):
        plan_on_grid(g, start, goal, start, limits)


def wall_with_far_gap() -> CostGrid:
    slope = np.zeros((21, 21))
    slope[:20, 12] = 30
    return grid(slope, cell_m=100.0)


def test_route_uses_a_gap_inside_the_distance_limit():
    g = wall_with_far_gap()

    route = plan_on_grid(g, centre(g, 10, 8), centre(g, 10, 14), centre(g, 10, 10), DEFAULT_LIMITS)

    assert (20, 12) in cells(g, route.path)
    distance = check(route, "distance_from_habitat")
    assert distance.passed and distance.threshold == 2000 and distance.units == "m"
    assert distance.value <= 2000


def test_no_route_when_the_only_gap_is_beyond_the_distance_limit():
    g = wall_with_far_gap()
    limits = DEFAULT_LIMITS.model_copy(update={"max_distance_from_habitat_m": 900})

    with pytest.raises(NoSafeRoute):
        plan_on_grid(g, centre(g, 10, 8), centre(g, 10, 14), centre(g, 10, 10), limits)


def test_distance_check_reports_the_furthest_point_from_the_habitat():
    g = grid(np.zeros((3, 11)), cell_m=50.0)

    route = plan_on_grid(g, centre(g, 1, 0), centre(g, 1, 10), centre(g, 1, 0), DEFAULT_LIMITS)

    assert check(route, "distance_from_habitat").value == pytest.approx(500)


def test_walk_back_margin_out_and_home_from_the_far_end():
    g, start, goal = flat_kilometre()

    route = plan_on_grid(g, start, goal, start, DEFAULT_LIMITS)

    # 6 h = 21600 s, minus 1800 s out and 1800 s home from the goal.
    assert route.walk_back_margin_s == pytest.approx(18000)


def test_walk_back_margin_when_the_route_ends_at_the_habitat():
    g, start, goal = flat_kilometre()

    route = plan_on_grid(g, start, goal, goal, DEFAULT_LIMITS)

    # Worst point is either end: 0 s walked + 1800 s home, or 1800 s walked + 0 s home.
    assert route.walk_back_margin_s == pytest.approx(19800)


def test_uniform_ten_degree_slope_is_walked_at_toblers_uphill_speed():
    g = grid(np.full((3, 101), 10.0), cell_m=10.0)

    route = plan_on_grid(g, centre(g, 1, 0), centre(g, 1, 100), centre(g, 1, 0), DEFAULT_LIMITS)

    # Tobler: speed falls by exp(-3.5 * tan 10°) = 1 / 1.8536 against flat ground.
    assert route.total_time_s == pytest.approx(3336.5, rel=1e-3)


@pytest.mark.parametrize("ground", ["sand", "ridge"])
def test_route_goes_round_a_patch_of_slow_ground_when_that_is_quicker(ground):
    patch = np.zeros((5, 9), dtype=bool)
    patch[0:3, 2:7] = True
    g = grid(np.zeros((5, 9)), **{ground: patch})

    route = plan_on_grid(g, centre(g, 1, 0), centre(g, 1, 8), centre(g, 4, 0), DEFAULT_LIMITS)

    assert not any(patch[c] for c in cells(g, route.path))


def test_a_straight_route_is_one_leg():
    g, start, goal = flat_kilometre()

    route = plan_on_grid(g, start, goal, start, DEFAULT_LIMITS)

    assert [(leg.start_index, leg.end_index) for leg in route.legs] == [(0, 100)]
    assert route.legs[0].distance_m == pytest.approx(1000)


def test_legs_split_the_path_at_each_turn_and_add_up_to_the_route():
    slope = np.zeros((7, 7))
    slope[:6, 3] = 30
    g = grid(slope)

    route = plan_on_grid(g, centre(g, 1, 0), centre(g, 1, 6), centre(g, 6, 0), DEFAULT_LIMITS)

    assert len(route.legs) >= 2
    assert route.legs[0].start_index == 0 and route.legs[-1].end_index == len(route.path) - 1
    legs = route.legs
    assert all(a.end_index == b.start_index for a, b in zip(legs, legs[1:], strict=False))
    assert sum(leg.time_s for leg in route.legs) == pytest.approx(route.total_time_s)
    assert sum(leg.distance_m for leg in route.legs) == pytest.approx(route.total_distance_m)


def test_ground_with_no_slope_data_is_never_walked():
    slope = np.zeros((7, 7))
    slope[:6, 3] = np.nan
    g = grid(slope)

    route = plan_on_grid(g, centre(g, 1, 0), centre(g, 1, 6), centre(g, 6, 0), DEFAULT_LIMITS)

    assert not any(np.isnan(g.slope_deg[c]) for c in cells(g, route.path))


def test_start_and_goal_in_the_same_planning_cell_is_refused():
    g, start, _ = flat_kilometre()

    with pytest.raises(HTTPException, match="same planning cell"):
        plan_on_grid(g, start, start, start, DEFAULT_LIMITS)


def test_a_diagonal_wall_of_steep_cells_cannot_be_slipped_through_at_a_corner():
    slope = np.zeros((7, 7))
    for row in range(7):
        slope[row, 6 - row] = 30
    g = grid(slope)

    with pytest.raises(NoSafeRoute):
        plan_on_grid(g, centre(g, 0, 0), centre(g, 6, 6), centre(g, 0, 0), DEFAULT_LIMITS)


def test_no_route_when_the_crew_could_not_walk_home_in_time():
    g, start, goal = flat_kilometre()
    # 0.5 h out keeps the 0.75 h walk-time limit, but 0.5 h more to walk home does not.
    limits = DEFAULT_LIMITS.model_copy(update={"max_walk_h": 0.75})

    with pytest.raises(NoSafeRoute):
        plan_on_grid(g, start, goal, start, limits)


def test_steep_cells_touching_at_a_corner_leave_their_neighbours_walkable():
    slope = np.zeros((5, 5))
    slope[1, 1] = slope[2, 2] = 30
    g = grid(slope)

    route = plan_on_grid(g, centre(g, 1, 2), centre(g, 0, 4), centre(g, 0, 4), DEFAULT_LIMITS)

    assert cells(g, route.path)[0] == (1, 2)
