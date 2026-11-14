"""The route engine on tiny made-up grids: the best path and every hard limit."""

import numpy as np
import pytest
from fastapi import HTTPException

from contracts.models.common import Point
from contracts.models.route_request import Limits, Mode
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


def test_the_route_runs_from_the_exact_start_to_the_exact_goal():
    g, _, _ = flat_kilometre()
    start, goal = Point(x=2, y=15), Point(x=1008, y=15)

    route = plan_on_grid(g, start, goal, start, DEFAULT_LIMITS)

    assert (route.path[0], route.path[-1]) == (start, goal)
    # 3 m to the first cell centre, 1000 m between centres, 3 m on to the goal, at 1.8 s/m.
    assert route.total_distance_m == pytest.approx(1006)
    assert route.total_time_s == pytest.approx(1810.8)
    assert sum(leg.time_s for leg in route.legs) == pytest.approx(1810.8)


def test_a_goal_just_beyond_the_distance_limit_is_refused_though_its_cell_centre_is_inside():
    g = grid(np.zeros((3, 30)), cell_m=10.0)
    habitat = centre(g, 1, 0)
    limits = DEFAULT_LIMITS.model_copy(update={"max_distance_from_habitat_m": 200})

    with pytest.raises(NoSafeRoute):
        plan_on_grid(g, habitat, Point(x=habitat.x + 200.4, y=habitat.y), habitat, limits)


def test_the_walk_back_counts_the_walk_to_and_from_the_exact_endpoints():
    g, _, _ = flat_kilometre()
    start, goal = Point(x=2, y=15), Point(x=1008, y=15)
    # 1810.8 s out and 1810.8 s home is 3621.6 s, over a 3615 s walk-time limit; between
    # cell centres alone it would be 3600 s and pass.
    limits = DEFAULT_LIMITS.model_copy(update={"max_walk_h": 3615 / 3600})

    with pytest.raises(NoSafeRoute):
        plan_on_grid(g, start, goal, start, limits)


def test_a_walk_can_finish_at_an_off_centre_habitat_within_its_time_limit():
    g, _, _ = flat_kilometre()
    start, habitat = Point(x=2, y=15), Point(x=1008, y=15)
    limits = DEFAULT_LIMITS.model_copy(update={"max_walk_h": 1815 / 3600})

    route = plan_on_grid(g, start, habitat, habitat, limits)

    assert route.path[-1] == habitat
    # 3 + 1000 + 3 m at 1.8 s/m is 1810.8 s; arrival at the habitat leaves no walk home.
    assert route.total_time_s == pytest.approx(1810.8)
    assert route.walk_back_margin_s == pytest.approx(4.2)


@pytest.mark.parametrize("budget_s, expected_margin_s", [(1815, 0.6), (1814, None)])
def test_a_goal_in_the_habitat_cell_keeps_its_direct_walk_home(budget_s, expected_margin_s):
    g, _, _ = flat_kilometre()
    start, goal, habitat = Point(x=2, y=15), Point(x=1009, y=15), Point(x=1008, y=15)
    limits = DEFAULT_LIMITS.model_copy(update={"max_walk_h": budget_s / 3600})
    # 3 + 1000 + 4 m out takes 1812.6 s; the final 1 m home takes 1.8 s, not zero.
    # The full journey takes 1814.4 s, so 1815 s leaves 0.6 s and 1814 s must be refused.
    if expected_margin_s is None:
        with pytest.raises(NoSafeRoute):
            plan_on_grid(g, start, goal, habitat, limits)
    else:
        route = plan_on_grid(g, start, goal, habitat, limits)

        assert route.total_time_s == pytest.approx(1812.6)
        assert route.walk_back_margin_s == pytest.approx(expected_margin_s)


def test_walk_back_and_daylight_show_as_limit_checks_with_their_spare_time():
    g, start, goal = flat_kilometre()

    route = plan_on_grid(g, start, goal, start, DEFAULT_LIMITS, daylight_s=10000)

    walk_back = check(route, "walk_back")
    assert (walk_back.passed, walk_back.threshold, walk_back.units) == (True, 0, "s")
    assert walk_back.value == pytest.approx(18000)
    # Back at the habitat 1800 s out + 1800 s home = 3600 s into 10000 s of daylight.
    daylight = check(route, "daylight")
    assert (daylight.passed, daylight.threshold, daylight.units) == (True, 0, "s")
    assert daylight.value == pytest.approx(6400)


def test_no_route_when_the_crew_could_not_be_home_before_sunset():
    g, start, goal = flat_kilometre()

    with pytest.raises(NoSafeRoute, match="sunset"):
        plan_on_grid(g, start, goal, start, DEFAULT_LIMITS, daylight_s=3000)


def ridge_wall_with_gap() -> CostGrid:
    ridge = np.zeros((7, 7), dtype=bool)
    ridge[:6, 3] = True
    return grid(np.zeros((7, 7)), ridge=ridge)


def test_the_crew_climbs_a_ridge_the_cart_drives_round():
    g = ridge_wall_with_gap()
    start, goal, habitat = centre(g, 1, 0), centre(g, 1, 6), centre(g, 6, 0)

    crew_route = plan_on_grid(g, start, goal, habitat, DEFAULT_LIMITS)
    cart_route = plan_on_grid(g, start, goal, habitat, DEFAULT_LIMITS, mode=Mode.cart)

    assert any(g.ridge[c] for c in cells(g, crew_route.path))
    assert (6, 3) in cells(g, cart_route.path)
    assert not any(g.ridge[c] for c in cells(g, cart_route.path))


def test_the_cart_never_slips_through_a_diagonal_ridge():
    ridge = np.zeros((7, 7), dtype=bool)
    for row in range(7):
        ridge[row, 6 - row] = True
    g = grid(np.zeros((7, 7)), ridge=ridge)

    with pytest.raises(NoSafeRoute):
        plan_on_grid(
            g, centre(g, 0, 0), centre(g, 6, 6), centre(g, 0, 0), DEFAULT_LIMITS, mode=Mode.cart
        )


def test_the_cart_route_has_no_crew_only_limit_checks():
    g = ridge_wall_with_gap()

    cart_route = plan_on_grid(
        g,
        centre(g, 1, 0),
        centre(g, 1, 6),
        centre(g, 6, 0),
        DEFAULT_LIMITS,
        mode=Mode.cart,
        daylight_s=1e6,
    )

    assert [c.limit for c in cart_route.limit_checks] == [
        "slope",
        "distance_from_habitat",
        "planning_speed",
        "walk_time",
        "hazard_margin",
    ]


def test_the_science_route_passes_a_target_and_reports_its_extra_time():
    g = grid(np.zeros((35, 101)), cell_m=10.0)
    start, goal, target = centre(g, 31, 0), centre(g, 31, 100), centre(g, 1, 50)

    route = plan_on_grid(g, start, goal, start, DEFAULT_LIMITS, mode=Mode.science, targets=[target])

    assert route.mode == "science"
    assert target in route.path
    # 300 m north and 500 m east of the start on an 8-neighbour grid: 30 diagonal steps and
    # 20 straight ones, 300 sqrt(2) + 200 = 624.26 m each way, so 1248.53 m at 1.8 s/m,
    # against 1000 m (1800 s) for the fastest route.
    assert route.total_time_s == pytest.approx(2247.35, abs=0.05)
    assert route.extra_time_vs_fastest_s == pytest.approx(447.35, abs=0.05)


def test_the_science_route_drops_a_target_the_walk_has_no_time_for():
    g = grid(np.zeros((35, 121)), cell_m=10.0)
    start, goal = centre(g, 31, 20), centre(g, 31, 120)
    near, far = centre(g, 1, 70), centre(g, 31, 0)
    # Near only: 624.26 m out to it and 624.26 m on, 2247.35 s, plus 1800 s home from the
    # goal fits 4400 s. Far first as well: 200 + 824.26 + 624.26 m, 2967.35 s, plus 1800 s
    # does not; dropping far (2247 s left) saves more than dropping near (2520 s left).
    limits = DEFAULT_LIMITS.model_copy(update={"max_walk_h": 4400 / 3600})

    route = plan_on_grid(g, start, goal, start, limits, mode=Mode.science, targets=[near, far])

    assert near in route.path and far not in route.path
    assert route.extra_time_vs_fastest_s == pytest.approx(447.35, abs=0.05)
    assert all(c.passed for c in route.limit_checks)


def test_the_cart_cannot_start_on_a_ridge():
    g = ridge_wall_with_gap()

    with pytest.raises(NoSafeRoute):
        plan_on_grid(
            g, centre(g, 1, 3), centre(g, 1, 6), centre(g, 6, 0), DEFAULT_LIMITS, mode=Mode.cart
        )


def test_the_science_route_skips_a_target_on_ground_too_steep_to_walk():
    slope = np.zeros((35, 101))
    slope[1, 50] = 30
    g = grid(slope, cell_m=10.0)
    start, goal, steep = centre(g, 31, 0), centre(g, 31, 100), centre(g, 1, 50)

    route = plan_on_grid(g, start, goal, start, DEFAULT_LIMITS, mode=Mode.science, targets=[steep])

    assert steep not in route.path
    assert route.extra_time_vs_fastest_s == pytest.approx(0)


def test_a_target_beyond_the_distance_limit_does_not_cost_the_science_route_its_safe_target():
    g = grid(np.zeros((35, 101)), cell_m=10.0)
    start, goal, near = centre(g, 31, 0), centre(g, 31, 100), centre(g, 1, 50)
    # 1004.9 m from the habitat: past a 1001 m limit, though its cell centre (the goal's,
    # 1000 m out) is inside, and cheaper to visit than the near target.
    beyond = Point(x=goal.x + 4.9, y=goal.y)
    limits = DEFAULT_LIMITS.model_copy(update={"max_distance_from_habitat_m": 1001})

    route = plan_on_grid(g, start, goal, start, limits, mode=Mode.science, targets=[near, beyond])

    assert near in route.path and beyond not in route.path
    assert route.extra_time_vs_fastest_s == pytest.approx(447.35, abs=0.05)


def test_a_science_route_with_no_targets_is_still_the_science_route():
    g, start, goal = flat_kilometre()

    route = plan_on_grid(g, start, goal, start, DEFAULT_LIMITS, mode=Mode.science, targets=[])

    assert route.mode == "science"
    assert route.extra_time_vs_fastest_s == 0


@pytest.mark.parametrize(
    "outside",
    [
        Point(x=-5, y=35),
        Point(x=1015, y=35),
        Point(x=505, y=-5),
        Point(x=505, y=355),
    ],
    ids=["west", "east", "south", "north"],
)
def test_an_unmapped_target_does_not_cost_the_science_route_its_safe_target(outside):
    g = grid(np.zeros((35, 101)), cell_m=10.0)
    start, goal, near = centre(g, 31, 0), centre(g, 31, 100), centre(g, 1, 50)

    route = plan_on_grid(
        g, start, goal, start, DEFAULT_LIMITS, mode=Mode.science, targets=[outside, near]
    )

    assert near in route.path and outside not in route.path
    # The safe target adds 248.53 m over the 1 km fastest route, at 1.8 s/m.
    assert route.extra_time_vs_fastest_s == pytest.approx(447.35, abs=0.05)
    assert all(c.passed for c in route.limit_checks)


def test_a_science_route_with_only_unmapped_targets_keeps_its_mode_and_zero_extra_time():
    g, start, goal = flat_kilometre()
    outside = [Point(x=-5, y=15), Point(x=505, y=35)]

    route = plan_on_grid(g, start, goal, start, DEFAULT_LIMITS, mode=Mode.science, targets=outside)

    assert route.mode == "science"
    assert route.path[0] == start and route.path[-1] == goal
    assert route.total_distance_m == pytest.approx(1000)
    assert route.total_time_s == pytest.approx(1800)
    assert route.extra_time_vs_fastest_s == 0


def steep_drop_12_m_south_of_the_line() -> tuple[CostGrid, Point, Point]:
    slope = np.zeros((41, 101))
    slope[26, 50] = 30
    g = grid(slope, cell_m=2.0)
    return g, centre(g, 20, 0), centre(g, 20, 100)


def test_the_route_moves_away_from_a_hazard_as_the_circle_grows():
    g, start, goal = steep_drop_12_m_south_of_the_line()

    small = plan_on_grid(g, start, goal, start, DEFAULT_LIMITS, uncertainty_m=5)
    large = plan_on_grid(g, start, goal, start, DEFAULT_LIMITS, uncertainty_m=25)

    small_margin, large_margin = check(small, "hazard_margin"), check(large, "hazard_margin")
    # The straight line passes 6 cells of 2 m, 12 m, north of the steep cell.
    assert (small_margin.value, small_margin.threshold, small_margin.units) == (12, 5, "m")
    assert max(p.y for p in small.path) == start.y
    assert large_margin.threshold == 25 and large_margin.value > 25
    assert max(p.y for p in large.path) > start.y + 10
    assert small_margin.passed and large_margin.passed


def test_no_route_when_the_start_is_already_inside_the_hazard_margin():
    g, _, goal = steep_drop_12_m_south_of_the_line()
    start = centre(g, 20, 50)  # 12 m from the steep cell, inside a 15 m circle

    with pytest.raises(NoSafeRoute, match="start is within the 15 m circle of a hazard"):
        plan_on_grid(g, start, goal, start, DEFAULT_LIMITS, uncertainty_m=15)


def test_a_goal_inside_the_circle_of_a_hazard_is_refused_though_its_cell_centre_is_outside():
    g, start, _ = steep_drop_12_m_south_of_the_line()
    # The goal cell's centre is 12 m north of the steep cell, outside an 11.5 m circle, but
    # the exact goal 0.9 m south of that centre is 11.1 m away, inside it.
    centre_above = centre(g, 20, 50)
    goal = Point(x=centre_above.x, y=centre_above.y - 0.9)

    with pytest.raises(NoSafeRoute, match="hazard"):
        plan_on_grid(g, start, goal, start, DEFAULT_LIMITS, uncertainty_m=11.5)
