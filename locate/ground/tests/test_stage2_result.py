"""Stage 2's result (P3-08): a simulated error model from JPL's published numbers."""

import json
import math

import pytest

from contracts.models.fix_result import FixResult
from contracts.models.test_summary import TestSummary as Summary
from locate.ground.stage2_result import error_model, write_stage2_result
from sim.engine import simulate


def test_the_error_model_reproduces_jpls_published_errors():
    model = error_model()

    # A 2D normal error with the published 0.36 m average radial error:
    # sigma = 0.36 / sqrt(pi / 2) = 0.2872 m per axis, median radius
    # sigma * sqrt(2 ln 2) = 0.3382 m, 95% radius sigma * sqrt(-2 ln 0.05) = 0.7031 m.
    assert model.sigma_m == pytest.approx(0.2872, abs=1e-4)
    assert model.median_m == pytest.approx(0.3382, abs=1e-4)
    assert model.circle_95_m == pytest.approx(0.7031, abs=1e-4)
    # It isn't fitted to the 99th percentile, yet lands within 10% of the published 0.93 m.
    assert model.radius_at_m(0.99) == pytest.approx(0.93, rel=0.10)


def _measured_fix(photo_id: str, terrain: str, x: float, y: float) -> FixResult:
    """A held-out stop's measured ground fix, 50 m off its true position."""
    return FixResult.model_validate(
        {
            "photo_id": photo_id,
            "site": "gale",
            "method": "ground",
            "position": {"x": x + 50.0, "y": y},
            "heading_deg": 115.0,
            "uncertainty_m": 60.0,
            "confidence_pct": 0.0,
            "time_per_fix_s": 0.02,
            "terrain_type": terrain,
            "simulated": False,
            "overlay": f"results/ground/overlays/p3-07-{photo_id}.png",
            "truth": {
                "position": {"x": x, "y": y},
                "heading_deg": 115.0,
                "position_error_m": 50.0,
                "heading_error_deg": 0.0,
            },
            "provenance": {"script": "locate/ground/hidden_test.py", "commit": "", "inputs": []},
        }
    )


def test_the_stage_2_summary_is_the_model_at_the_held_out_stops_and_says_simulated(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("REDMARK_DATA", str(tmp_path))
    fixes = tmp_path / "fixes"
    fixes.mkdir()
    for fix in (
        _measured_fix("stop-a", "textured", 8144683.172, -283189.57),
        _measured_fix("stop-b", "textured", 8144400.0, -283500.0),
        _measured_fix("stop-c", "plain", 8143900.0, -284100.0),
    ):
        (fixes / f"{fix.photo_id}.json").write_text(fix.model_dump_json())

    path = write_stage2_result(fixes, results_dir=tmp_path / "results")

    summary = Summary.model_validate(json.loads(path.read_text()))
    assert path == tmp_path / "results" / "ground" / "ground-gale.json"
    assert summary.simulated is True
    assert summary.provenance.script == "locate/ground/stage2_result.py"
    assert [i.path for i in summary.provenance.inputs] == [
        "fixes/stop-a.json",
        "fixes/stop-b.json",
        "fixes/stop-c.json",
    ]
    # Each terrain group gets the model's spread, not the attempt's 50 m misses: two textured
    # stops sit at its quartiles, sigma * sqrt(-2 ln 0.75) = 0.218 m and
    # sigma * sqrt(-2 ln 0.25) = 0.478 m (median 0.348 m); one plain stop at its median, 0.338 m.
    assert summary.groups.textured.median_error_m == pytest.approx(0.348, abs=0.001)
    assert summary.groups.plain.median_error_m == pytest.approx(0.338, abs=0.001)
    assert summary.overall.n == 3
    assert summary.overall.within_1m_pct == 100.0
    # A ground fix carries the heading it was given; it doesn't measure one.
    assert summary.overall.median_heading_error_deg == 0.0
    assert summary.overall.median_time_per_fix_s is None


def test_the_walk_simulation_takes_its_ground_fix_size_from_the_written_result(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("REDMARK_DATA", str(tmp_path))
    fixes = tmp_path / "fixes"
    fixes.mkdir()
    for fix in (
        _measured_fix("stop-a", "textured", 8144683.172, -283189.57),
        _measured_fix("stop-c", "plain", 8143900.0, -284100.0),
    ):
        (fixes / f"{fix.photo_id}.json").write_text(fix.model_dump_json())
    results = tmp_path / "results"
    write_stage2_result(fixes, results_dir=results)

    run = simulate(
        {
            "site": "gale",
            "path": [{"x": 0.0, "y": 0.0}, {"x": 2000.0, "y": 0.0}],
            "fix_schedule": [{"time_s": 1800.0, "method": "ground"}],
            "break_it": {"camera_off": False, "radio_off": True, "drone_grounded": False},
            "seed": 1,
        },
        results_root=results,
        hazard_distance_m=lambda x, y: math.inf,
    )

    # 1 km walked in 180 ticks of 5.56 m, each drifting 2.5%: sigma 0.139 m * sqrt(180) = 1.86 m,
    # a 4.56 m circle. The ground fix brings it under the model's own 95% circle, 0.70 m.
    before, after = [s for s in run["steps"] if s["t_s"] == 1800.0]
    assert before["uncertainty_m"] == pytest.approx(4.56, rel=0.02)
    assert after["uncertainty_m"] < 0.71
