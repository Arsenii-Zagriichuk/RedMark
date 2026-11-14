"""Seams of the drone test at Jezero (P2-06): the run plan, the test end to end
on the fixture frame, the answer key and the matcher sharing a frame, and a
frame the matcher cannot lock on.

The fixture frame was rendered by NASA VICAR from a flight 10 label onto a
synthetic map (see test_drone_pipeline.py). Its photo ids and flights are made
up here: the test's code does not read them from the label.
"""

import json
import math
from pathlib import Path

import numpy as np
import pytest
import rasterio
from drone_stand_ins import ncc_matcher, smooth_noise
from PIL import Image
from rasterio.transform import from_origin

from contracts.models.common import Point, Provenance, TerrainType
from contracts.models.fix_result import FixResult
from contracts.models.test_summary import TestSummary
from contracts.scoring import score_fix
from locate.drone.fix import Matches, build_fix_result
from locate.drone.label import read_drone_frame
from locate.drone.pipeline import fix_frame
from locate.drone.score_jezero import (
    TUNING_FLIGHTS,
    Footprint,
    FrameInputs,
    PackFrame,
    plan_runs,
    run_test,
)
from route.tie_points import fit_tie_points

FIXTURES = Path(__file__).with_name("fixtures")
LABEL = (
    Path(__file__).parents[3]
    / "prep"
    / "tests"
    / "fixtures"
    / "HNM_0152_0680432615_348FDR_N0100001HELI03026_0000LUJ05.xml"
)
RES = 0.25
MIN_X, MAX_Y = 4354000.0, 1092400.0
MAP_PX = 900
# Where the fixture frame was rendered, and its heading (test_drone_pipeline.py).
TRUE_X, TRUE_Y = 4354112.5, 1092287.5
TRUE_HEADING_DEG = 89.7234
# A drifted onboard position, 6.3 m east and 4.7 m south of the truth:
# hypot(6.3, 4.7) = sqrt(39.69 + 22.09) = sqrt(61.78) = 7.860 m off.
ONBOARD = (TRUE_X + 6.3, TRUE_Y - 4.7)
ONBOARD_OFF_M = 7.86

PROVENANCE = Provenance(script="locate/drone/score_jezero.py", commit="abc", inputs=[])


def key(photo_id, flight=11, terrain="textured", hard_mode=False, simulated=False, x=TRUE_X):
    """An answer-key record in P4-01's format (route/answer_key.py), the fields read here."""
    return {
        "photo_id": photo_id,
        "site": "jezero",
        "flight": flight,
        "true_position": {"x": x, "y": TRUE_Y},
        "true_heading_deg": TRUE_HEADING_DEG,
        "terrain_type": terrain,
        "hard_mode": hard_mode,
        "simulated": simulated,
    }


# --- Run plan -------------------------------------------------------------


def test_keys_run_flight_by_flight_in_time_order():
    keys = [key("c", flight=11), key("a", flight=15), key("b", flight=11)]
    pack = {
        "a": PackFrame(flight=15, sclk=50.0, reach_m=10.0),
        "b": PackFrame(flight=11, sclk=10.0, reach_m=10.0),
        "c": PackFrame(flight=11, sclk=20.0, reach_m=10.0),
    }

    plan = plan_runs(keys, pack, tuning=[])

    assert [[k.photo_id for k in run] for run in plan.runs] == [["b", "c"], ["a"]]
    assert plan.overlapping == []
    first = plan.runs[0][0]
    assert first.true_position == (TRUE_X, TRUE_Y)
    assert first.terrain_type == TerrainType.textured


def test_flight_10_is_the_tuning_flight():
    # P2-05 chose the tiling and match limits on flight 10's frame 0606.
    assert TUNING_FLIGHTS == frozenset({10})


def test_a_key_on_the_tuning_flight_is_refused():
    pack = {"a": PackFrame(flight=10, sclk=1.0, reach_m=10.0)}
    with pytest.raises(ValueError, match="tuning"):
        plan_runs([key("a", flight=10)], pack, tuning=[])


def test_a_simulated_key_is_refused():
    pack = {"a": PackFrame(flight=11, sclk=1.0, reach_m=10.0)}
    with pytest.raises(ValueError, match="simulated"):
        plan_runs([key("a", simulated=True)], pack, tuning=[])


def test_a_key_must_be_a_pack_frame_of_its_flight():
    with pytest.raises(ValueError, match="pack"):
        plan_runs([key("a")], {}, tuning=[])
    with pytest.raises(ValueError, match="flight"):
        plan_runs([key("a", flight=11)], {"a": PackFrame(15, 1.0, 10.0)}, tuning=[])


def test_a_key_whose_ground_a_tuning_frame_may_have_seen_is_left_out():
    # Reaches 10 m + 10 m, plus 20 m for the tuning frame's onboard position
    # drifting: centres 39 m apart may overlap, 41 m apart cannot.
    tuning = [Footprint(centre=(TRUE_X - 39.0, TRUE_Y), reach_m=10.0)]
    pack = {
        "near": PackFrame(flight=11, sclk=1.0, reach_m=10.0),
        "far": PackFrame(flight=11, sclk=2.0, reach_m=10.0),
    }
    keys = [key("near"), key("far", x=TRUE_X + 2.0)]

    plan = plan_runs(keys, pack, tuning=tuning)

    assert [[k.photo_id for k in run] for run in plan.runs] == [["far"]]
    assert plan.overlapping == ["near"]


# --- End to end on the fixture frame -----------------------------------------


@pytest.fixture
def photo_map(tmp_path: Path) -> Path:
    noise = smooth_noise(MAP_PX, sigma_px=2.0, seed=11)
    values = np.clip(2000 + 600 * noise / noise.std(), 0, 4095).astype(np.uint16)
    crop = tmp_path / "crop.tif"
    with rasterio.open(
        crop,
        "w",
        driver="GTiff",
        width=MAP_PX,
        height=MAP_PX,
        count=1,
        dtype="uint16",
        transform=from_origin(MIN_X, MAX_Y, RES, RES),
    ) as dst:
        dst.write(values, 1)
    return crop


@pytest.fixture
def frame_inputs(photo_map):
    camera = read_drone_frame(LABEL.read_text())
    with Image.open(FIXTURES / "vicar-navcam.png") as image:
        raw = np.array(image)
    return FrameInputs(raw=raw, camera=camera, crop=photo_map, onboard=ONBOARD)


@pytest.fixture
def results_dir(tmp_path, monkeypatch) -> Path:
    # Overlay paths are recorded relative to REDMARK_DATA or the repo.
    monkeypatch.setenv("REDMARK_DATA", str(tmp_path))
    return tmp_path / "results"


def two_frame_plan():
    """The fixture frame keyed twice on one flight: once textured, once plain
    over sand ripples (hard mode)."""
    pack = {
        "frame-a": PackFrame(flight=11, sclk=1.0, reach_m=10.0),
        "frame-b": PackFrame(flight=11, sclk=2.0, reach_m=10.0),
    }
    keys = [key("frame-a"), key("frame-b", terrain="plain", hard_mode=True)]
    return plan_runs(keys, pack, tuning=[])


def test_every_keyed_frame_gets_a_scored_fix_an_overlay_and_a_summary(frame_inputs, results_dir):
    summary_path = run_test(
        two_frame_plan(),
        lambda _: frame_inputs,
        ncc_matcher,
        matcher_name="ncc",
        provenance=PROVENANCE,
        results_dir=results_dir,
    )

    summary = TestSummary.model_validate_json(summary_path.read_text())
    assert summary_path == results_dir / "drone" / "drone-jezero.json"
    assert (summary.test, summary.site.value, summary.simulated) == (
        "drone-jezero",
        "jezero",
        False,
    )
    assert summary.overall.n == 2
    assert summary.overall.median_error_m < 0.1
    assert summary.overall.within_1m_pct == 100.0
    groups = json.loads(summary_path.read_text())["groups"]
    assert {name: group["n"] for name, group in groups.items()} == {
        "textured": 1,
        "plain": 1,
        "hard_mode": 1,
    }
    for photo_id in ("frame-a", "frame-b"):
        fix = FixResult.model_validate_json(
            (results_dir / "drone" / "fixes" / f"{photo_id}.json").read_text()
        )
        assert fix.truth.position == Point(x=TRUE_X, y=TRUE_Y)
        assert fix.truth.position_error_m < 0.1
        assert fix.truth.heading_error_deg < 0.5
        assert fix.provenance == PROVENANCE
        overlay = results_dir.parent / fix.overlay
        with Image.open(overlay) as image:
            embedded = FixResult.model_validate_json(image.text["fix_result"])
        assert embedded == fix
    assert fix.terrain_type == TerrainType.plain


# --- Same frame as the key --------------------------------------------------


def test_a_key_fitted_to_the_matchers_own_points_scores_zero(frame_inputs):
    """Person 4's tie-point fit, given points the matcher's fit carried from
    the straightened photo onto the map, finds the same nadir and heading:
    the key and the drone fix share one position and heading convention."""
    ground, window, drone_fix = fix_frame(
        frame_inputs.raw, frame_inputs.camera, frame_inputs.crop, ONBOARD, ncc_matcher
    )
    a, b = drone_fix.to_window
    rows, cols = np.nonzero(ground.valid)
    pick = np.linspace(0, len(rows) - 1, 12).astype(int)
    photo_px = np.column_stack([cols[pick], rows[pick]]).astype(float)
    carried = a * (photo_px[:, 0] + 1j * photo_px[:, 1]) + b
    map_xy = window.to_map(np.column_stack([carried.real, carried.imag]))

    answer = fit_tie_points(photo_px, map_xy, tuple(ground.nadir_px), ground.heading_deg)
    fix = build_fix_result(
        photo_id="frame-a",
        estimate=drone_fix,
        time_per_fix_s=0.0,
        terrain_type=TerrainType.textured,
        overlay="results/drone/overlays/frame-a.png",
        provenance=PROVENANCE,
    )
    scored = score_fix(fix, Point(x=answer.position[0], y=answer.position[1]), answer.heading_deg)

    assert scored.truth.position_error_m == 0.0
    assert scored.truth.heading_error_deg == pytest.approx(0.0, abs=1e-6)


# --- A frame the matcher cannot lock on --------------------------------------


def no_matches(query: np.ndarray, reference: np.ndarray) -> Matches:
    return Matches(query_xy=np.empty((0, 2)), reference_xy=np.empty((0, 2)))


def test_a_frame_with_no_lock_is_scored_at_its_search_centre(frame_inputs, results_dir):
    summary_path = run_test(
        two_frame_plan(),
        lambda _: frame_inputs,
        no_matches,
        matcher_name="none",
        provenance=PROVENANCE,
        results_dir=results_dir,
    )

    fix = FixResult.model_validate_json(
        (results_dir / "drone" / "fixes" / "frame-a.json").read_text()
    )
    # A flight's first frame is searched around the onboard position.
    assert (fix.position.x, fix.position.y) == ONBOARD
    assert fix.truth.position_error_m == ONBOARD_OFF_M
    with Image.open(results_dir.parent / fix.overlay) as image:
        assert image.text["inliers"] == "0"
    summary = json.loads(summary_path.read_text())
    # Both misses count: none is dropped from the numbers.
    assert summary["overall"]["n"] == 2
    assert summary["overall"]["within_5m_pct"] == 0.0
    assert math.isclose(summary["overall"]["median_error_m"], ONBOARD_OFF_M)
