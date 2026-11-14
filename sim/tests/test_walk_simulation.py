"""The walk simulation through the service's interface: simulate(request) -> response."""

import json

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from contracts.paths import REPO_ROOT
from sim.engine import simulate

RESULTS = REPO_ROOT / "results"


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
    run = simulate(walk([(0, 0), (2000, 0)]))

    circles = [s["uncertainty_m"] for s in run["steps"]]
    assert all(b >= a for a, b in zip(circles, circles[1:], strict=False))
    assert circles[-1] > 2 * circles[0]


def test_the_same_seed_replays_the_same_walk_and_another_seed_does_not():
    path = [(0, 0), (600, 500), (1200, 900)]

    first, again = simulate(walk(path, seed=7)), simulate(walk(path, seed=7))
    other = simulate(walk(path, seed=8))

    assert first == again
    assert first["steps"][-1]["estimated_position"] != other["steps"][-1]["estimated_position"]


def step_at(run: dict, t_s: float) -> tuple[dict, dict]:
    """The step at t_s and the one before it."""
    i = next(i for i, s in enumerate(run["steps"]) if s["t_s"] == pytest.approx(t_s))
    return run["steps"][i], run["steps"][i - 1]


def test_the_circle_shrinks_at_a_fix():
    run = simulate(walk([(0, 0), (2000, 0)], fixes=[(1805, "horizon")]))

    fix, before = step_at(run, 1805)
    assert {"kind": "fix", "method": "horizon"} in fix["events"]
    assert "horizon" in fix["sources"]
    assert fix["uncertainty_m"] < before["uncertainty_m"]
    after = run["steps"][run["steps"].index(fix) + 1]
    assert "horizon" not in after["sources"] and after["events"] == []


def test_fix_error_sizes_come_from_the_test_summary_it_is_given(tmp_path):
    summary = json.loads((RESULTS / "horizon" / "horizon-gale.json").read_text())
    summary["overall"]["median_error_m"] = 0.1
    (tmp_path / "horizon").mkdir()
    (tmp_path / "horizon" / "horizon-gale.json").write_text(json.dumps(summary))

    run = simulate(walk([(0, 0), (2000, 0)], fixes=[(1800, "horizon")]), results_root=tmp_path)

    # A 0.1 m median radial error is sigma = 0.1 / sqrt(2 ln 2) = 0.0849 m per axis, whose
    # 95% circle is 0.0849 * sqrt(-2 ln 0.05) = 0.208 m; the walked circle barely widens it.
    fix, _ = step_at(run, 1800)
    assert fix["uncertainty_m"] == pytest.approx(0.208, rel=0.02)


def test_a_fix_is_requested_once_when_the_circle_passes_ten_metres_on_open_ground():
    run = simulate(walk([(0, 0), (6000, 0)]))

    requested = [s for s in run["steps"] if {"kind": "fix_requested"} in s["events"]]
    assert len(requested) == 1
    at = run["steps"].index(requested[0])
    assert run["steps"][at]["uncertainty_m"] > 10 >= run["steps"][at - 1]["uncertainty_m"]


@pytest.mark.parametrize("flag", ["camera_off", "radio_off", "drone_grounded"])
def test_break_it_scenarios_are_refused_until_they_are_built(flag):
    with pytest.raises(NotImplementedError, match="P4-06"):
        simulate(walk([(0, 0), (100, 0)], **{flag: True}))


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
    summary = json.loads((RESULTS / "horizon" / "horizon-gale.json").read_text())
    summary["overall"]["median_error_m"] = 0
    (tmp_path / "horizon").mkdir()
    (tmp_path / "horizon" / "horizon-gale.json").write_text(json.dumps(summary))

    run = simulate(walk([(0, 0), (500, 0)], fixes=[(300, "horizon")]), results_root=tmp_path)

    fix, _ = step_at(run, 300)
    assert 0 < fix["uncertainty_m"] < 0.1
