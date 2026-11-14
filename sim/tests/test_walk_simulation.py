"""The walk simulation through the service's interface: simulate(request) -> response."""

import json
import math

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from contracts.paths import REPO_ROOT
from sim.engine import simulate

RESULTS = REPO_ROOT / "results"


def write_horizon_summary(results_root, median_error_m: float) -> None:
    summary = json.loads((RESULTS / "horizon" / "horizon-gale.json").read_text())
    summary["overall"]["median_error_m"] = median_error_m
    folder = results_root / "horizon"
    folder.mkdir()
    (folder / "horizon-gale.json").write_text(json.dumps(summary))


def walk(path, fixes=(), seed=1, **break_it) -> dict:
    return {
        "site": "gale",
        "path": [{"x": x, "y": y} for x, y in path],
        "fix_schedule": [{"time_s": t, "method": m} for t, m in fixes],
        "break_it": {"camera_off": False, "radio_off": False, "drone_grounded": False} | break_it,
        "seed": seed,
    }


def test_a_kilometre_walked_at_two_kmh_ends_at_the_path_end_after_half_an_hour():
    run = simulate(walk([(0, 0), (1000, 0)]))

    first, last = run["steps"][0], run["steps"][-1]
    assert first["t_s"] == 0 and first["true_position"] == {"x": 0, "y": 0}
    assert last["t_s"] == pytest.approx(1800)
    assert last["true_position"]["x"] == pytest.approx(1000)
    assert last["true_position"]["y"] == pytest.approx(0)
    assert all(s["true_position"]["y"] == pytest.approx(0) for s in run["steps"])


def test_the_circle_grows_while_no_fix_is_taken():
    run = simulate(walk([(0, 0), (2000, 0)], radio_off=True))

    circles = [s["uncertainty_m"] for s in run["steps"]]
    assert all(b >= a for a, b in zip(circles, circles[1:], strict=False))
    assert circles[-1] > 2 * circles[0]


def test_the_circle_grows_for_distance_walked_out_and_back_within_one_tick():
    run = simulate(walk([(0, 0), (2, 0), (0, 0)]))

    first, last = run["steps"][0], run["steps"][-1]
    assert last["t_s"] == pytest.approx(7.2)
    assert last["true_position"] == first["true_position"]
    # Walking 4 m adds 0.1 m drift sigma per axis; the initial 0.5 m circle becomes 0.5567 m.
    assert last["uncertainty_m"] == pytest.approx(0.5567, abs=0.0001)


def test_the_same_seed_replays_the_same_walk_and_another_seed_does_not():
    path = [(0, 0), (600, 500), (1200, 900)]

    first, again = simulate(walk(path, seed=7)), simulate(walk(path, seed=7))
    other = simulate(walk(path, seed=8))

    assert first == again
    assert first["steps"][-1]["estimated_position"] != other["steps"][-1]["estimated_position"]


def step_at(run: dict, t_s: float) -> dict:
    """The last step at t_s."""
    return [s for s in run["steps"] if s["t_s"] == pytest.approx(t_s)][-1]


def fix_at(run: dict, t_s: float) -> tuple[dict, dict]:
    """The correction at t_s and its preceding prediction."""
    i = next(
        i
        for i, s in enumerate(run["steps"])
        if s["t_s"] == pytest.approx(t_s) and any(e["kind"] == "fix" for e in s["events"])
    )
    return run["steps"][i], run["steps"][i - 1]


def test_the_circle_shrinks_at_a_fix():
    run = simulate(walk([(0, 0), (2000, 0)], fixes=[(1805, "horizon")]))

    fix, before = fix_at(run, 1805)
    assert {"kind": "fix", "method": "horizon"} in fix["events"]
    assert "horizon" in fix["sources"]
    assert fix["uncertainty_m"] < before["uncertainty_m"]
    after = run["steps"][run["steps"].index(fix) + 1]
    assert "horizon" not in after["sources"] and after["events"] == []


def test_a_noisy_fix_emits_its_prediction_before_the_correction(tmp_path):
    write_horizon_summary(tmp_path, 5)
    run = simulate(walk([(0, 0), (1000, 0)], fixes=[(10, "horizon")]), results_root=tmp_path)

    correction, prediction = fix_at(run, 10)
    assert prediction["t_s"] == correction["t_s"] == 10
    assert prediction["true_position"] == correction["true_position"]
    assert prediction["uncertainty_m"] > run["steps"][0]["uncertainty_m"]
    assert correction["uncertainty_m"] < prediction["uncertainty_m"]
    assert correction["uncertainty_m"] > run["steps"][0]["uncertainty_m"]
    assert prediction["events"] == [] and "horizon" not in prediction["sources"]
    assert "horizon" in correction["sources"]


def test_fix_error_sizes_come_from_the_test_summary_it_is_given(tmp_path):
    write_horizon_summary(tmp_path, 0.1)

    run = simulate(walk([(0, 0), (2000, 0)], fixes=[(1800, "horizon")]), results_root=tmp_path)

    # A 0.1 m median radial error is sigma = 0.1 / sqrt(2 ln 2) = 0.0849 m per axis, whose
    # 95% circle is 0.0849 * sqrt(-2 ln 0.05) = 0.208 m; the walked circle barely widens it.
    fix, _ = fix_at(run, 1800)
    assert fix["uncertainty_m"] == pytest.approx(0.208, rel=0.02)


def test_a_fix_is_requested_once_when_the_circle_passes_ten_metres_on_open_ground():
    run = simulate(walk([(0, 0), (6000, 0)], radio_off=True))

    requested = [s for s in run["steps"] if {"kind": "fix_requested"} in s["events"]]
    assert len(requested) == 1
    at = run["steps"].index(requested[0])
    assert run["steps"][at]["uncertainty_m"] > 10 >= run["steps"][at - 1]["uncertainty_m"]


def test_the_stub_request_gives_a_simulated_run_that_matches_the_contract():
    schemas = REPO_ROOT / "contracts" / "schemas"
    common = json.loads((schemas / "common.json").read_text())
    registry = Registry().with_resource(
        "common.json", Resource.from_contents(common, default_specification=DRAFT202012)
    )
    schema = json.loads((schemas / "simulate_response.json").read_text())
    request = json.loads(
        (REPO_ROOT / "contracts" / "stubs" / "simulate" / "request.json").read_text()
    )

    run = simulate(request)

    Draft202012Validator(schema, registry=registry).validate(run)
    assert run["simulated"] is True and run["seed"] == request["seed"]
    assert any({"kind": "fix", "method": "horizon"} in s["events"] for s in run["steps"])


def test_a_test_summary_with_no_error_still_leaves_a_circle(tmp_path):
    write_horizon_summary(tmp_path, 0)

    run = simulate(walk([(0, 0), (500, 0)], fixes=[(300, "horizon")]), results_root=tmp_path)

    fix, _ = fix_at(run, 300)
    assert 0 < fix["uncertainty_m"] < 0.1


def test_radio_off_is_offline_mode_from_start_to_end():
    run = simulate(walk([(0, 0), (1000, 0)], radio_off=True))

    assert {s["mode"] for s in run["steps"]} == {"offline"}
    assert not any("radio" in s["sources"] for s in run["steps"])
    assert {"kind": "radio_off"} in run["steps"][0]["events"]
    # 180 ticks of 5.556 m, each drifting 2.5%: sigma^2 = (0.5 / 2.4477)^2 + 180 (0.1389)^2
    # = 3.514 m^2, so a 95% circle of 2.4477 x 1.8746 = 4.59 m.
    assert run["steps"][-1]["uncertainty_m"] == pytest.approx(4.59, abs=0.01)


def test_radio_ranging_keeps_the_circle_small_while_the_radio_is_up():
    path = [(0, 0), (6000, 0)]

    ranged = simulate(walk(path))
    offline = simulate(walk(path, radio_off=True))

    assert "radio" in step_at(ranged, 60)["sources"]
    labelled = [s for s in ranged["steps"] if {"kind": "radio_ranging_simulated"} in s["events"]]
    assert [s["t_s"] for s in labelled] == [60]
    assert "radio" not in step_at(ranged, 50)["sources"]
    assert max(s["uncertainty_m"] for s in ranged["steps"]) < 5
    assert offline["steps"][-1]["uncertainty_m"] > 10


def test_with_the_camera_off_steps_and_the_sun_drift_twice_as_fast():
    run = simulate(walk([(0, 0), (1000, 0)], camera_off=True, radio_off=True))

    assert {"kind": "camera_off"} in run["steps"][0]["events"]
    assert not any("visual_odometry" in s["sources"] for s in run["steps"])
    assert {"motion_sensor", "step_count", "sun"} <= set(run["steps"][-1]["sources"])
    # As above, but 5% per step: sigma^2 = 0.0417 + 180 (0.2778)^2 = 13.93 m^2, 9.14 m.
    assert run["steps"][-1]["uncertainty_m"] == pytest.approx(9.14, abs=0.01)


def test_with_the_camera_off_the_buddys_camera_takes_the_fix():
    run = simulate(walk([(0, 0), (2000, 0)], fixes=[(1805, "horizon")], camera_off=True))

    fix, before = fix_at(run, 1805)
    assert {"kind": "buddy_camera"} in fix["events"]
    assert fix["uncertainty_m"] < before["uncertainty_m"]


def test_with_the_camera_and_radio_off_no_photo_fix_reaches_the_crew():
    run = simulate(
        walk([(0, 0), (2000, 0)], fixes=[(1805, "horizon")], camera_off=True, radio_off=True)
    )

    at = [s for s in run["steps"] if s["t_s"] == pytest.approx(1805)]
    assert {"kind": "fix_unavailable", "method": "horizon"} in at[-1]["events"]
    assert not any(e["kind"] == "fix" for s in run["steps"] for e in s["events"])
    assert "horizon" not in at[-1]["sources"]


def test_with_the_drone_grounded_drone_fixes_are_greyed_out():
    run = simulate(walk([(0, 0), (2000, 0)], fixes=[(1805, "drone")], drone_grounded=True))

    assert {"kind": "drone_grounded"} in run["steps"][0]["events"]
    assert {"kind": "fix_unavailable", "method": "drone"} in step_at(run, 1805)["events"]
    assert not any("drone" in s["sources"] for s in run["steps"])


def test_everything_at_once_starts_lost_mode_when_the_circle_passes_ten_metres():
    run = simulate(
        walk(
            [(0, 0), (4000, 0)],
            fixes=[(600, "horizon"), (900, "drone")],
            camera_off=True,
            radio_off=True,
            drone_grounded=True,
        )
    )

    steps = run["steps"]
    lost = [i for i, s in enumerate(steps) if {"kind": "lost_mode"} in s["events"]]
    assert len(lost) == 1
    at = lost[0]
    assert steps[at]["uncertainty_m"] > 10 >= steps[at - 1]["uncertainty_m"]
    assert {s["mode"] for s in steps[:at]} == {"offline"}
    assert {s["mode"] for s in steps[at:]} == {"lost"}
    assert not any({"kind": "fix_requested"} in s["events"] for s in steps)


def test_near_a_hazard_a_circle_over_three_metres_says_stop_and_take_a_fix():
    def steep_drop_at(x0, y0):
        return lambda x, y: math.hypot(x - x0, y - y0)

    path = [(0, 0), (1000, 0)]
    # 1 m off the path at x = 500, where the circle is about 3.3 m: the hazard comes inside
    # the circle, so the crew is told to stop once as they come up to it.
    near = simulate(walk(path, radio_off=True), hazard_distance_m=steep_drop_at(500, 1))
    far = simulate(walk(path, radio_off=True), hazard_distance_m=steep_drop_at(500, 100))

    stops = [s for s in near["steps"] if {"kind": "stop_for_fix"} in s["events"]]
    assert len(stops) == 1
    assert stops[0]["uncertainty_m"] > 3
    assert 490 < stops[0]["true_position"]["x"] < 505
    assert not any({"kind": "stop_for_fix"} in s["events"] for s in far["steps"])
