"""Demo fixes (P3-04): which tested stops the demo shows, and their demo cache entries."""

import json
from pathlib import Path

import pytest

from contracts.models.common import Method, Point, Provenance, SiteId, TerrainType
from contracts.models.demo_cache import DemoCacheEntry
from contracts.models.fix_result import FixResult
from contracts.scoring import score_fix
from locate.horizon.demo_fixes import ScoredStop, demo_steps, write_demo_cache

ESTIMATE = Point(x=8144000.0, y=-283000.0)


def _stop(
    photo_id: str, east_m: float, north_m: float, circle_m: float, terrain: str, hollow: bool
) -> ScoredStop:
    """A tested stop whose true position is east_m, north_m from its estimate."""
    fix = FixResult(
        photo_id=photo_id,
        site=SiteId.gale,
        method=Method.horizon,
        position=ESTIMATE,
        heading_deg=90.0,
        uncertainty_m=circle_m,
        confidence_pct=0.0,
        time_per_fix_s=4.0,
        terrain_type=TerrainType(terrain),
        simulated=False,
        overlay=f"results/horizon/overlays/p3-03-{photo_id}.png",
        truth=None,
        provenance=Provenance(script="locate/horizon/hidden_test.py", commit="abc", inputs=[]),
    )
    truth = Point(x=ESTIMATE.x + east_m, y=ESTIMATE.y + north_m)
    return ScoredStop(fix=score_fix(fix, truth, 90.0), hollow=hollow)


def test_the_demo_shows_a_strong_and_a_weak_checkpoint_and_the_best_of_each_terrain():
    stops = [
        # 30 m off (18, 24), inside its 100 m circle: the strong checkpoint.
        _stop("STRONG", 18.0, 24.0, circle_m=100.0, terrain="plain", hollow=False),
        # Smallest circle, but 50 m off (30, 40) is outside its 40 m circle.
        _stop("OUTSIDE", 30.0, 40.0, circle_m=40.0, terrain="textured", hollow=False),
        # A hollow 900 m off: the weak case.
        _stop("WEAK", 540.0, 720.0, circle_m=3000.0, terrain="plain", hollow=True),
        # A hollow with a tight, honest circle: neither strong (hollow) nor weak (small error).
        _stop("GOOD_HOLLOW", 9.0, 12.0, circle_m=20.0, terrain="textured", hollow=True),
        # 25 m off (7, 24): the best textured stop on open ground.
        _stop("TEXTURED", 7.0, 24.0, circle_m=2000.0, terrain="textured", hollow=False),
        # 10 m off (6, 8): the best plain stop on open ground.
        _stop("PLAIN", 6.0, 8.0, circle_m=4000.0, terrain="plain", hollow=False),
    ]

    steps = {step: fix.photo_id for step, fix in demo_steps(stops).items()}

    assert steps == {
        "checkpoint.fix.horizon": "STRONG",
        "checkpoint.fix.horizon.weak": "WEAK",
        "testlab.fix.horizon.STRONG": "STRONG",
        "testlab.fix.horizon.WEAK": "WEAK",
        "testlab.fix.horizon.TEXTURED": "TEXTURED",
        "testlab.fix.horizon.PLAIN": "PLAIN",
    }


def test_without_a_hollow_there_is_no_weak_case_and_no_demo():
    stops = [
        _stop("STRONG", 18.0, 24.0, circle_m=100.0, terrain="plain", hollow=False),
        _stop("TEXTURED", 7.0, 24.0, circle_m=2000.0, terrain="textured", hollow=False),
    ]

    with pytest.raises(ValueError, match="hollow"):
        demo_steps(stops)


def _fix_file(root: Path, photo_id: str, with_overlay: bool = True) -> FixResult:
    """A tested stop's fix result where the service looks it up, and its overlay image."""
    fix = _stop(photo_id, 18.0, 24.0, circle_m=100.0, terrain="plain", hollow=False).fix
    path = root / "results/horizon/fixes" / f"{photo_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(fix.model_dump(mode="json"), indent=2) + "\n")
    if with_overlay:
        (root / fix.overlay).parent.mkdir(parents=True, exist_ok=True)
        (root / fix.overlay).write_bytes(b"\x89PNG")
    return fix


def test_a_demo_step_replays_the_fix_result_the_service_serves(tmp_path):
    fix = _fix_file(tmp_path, "NLB_759345596ILT_S1052222NCAM00275M1")

    (path,) = write_demo_cache({"checkpoint.fix.horizon": fix}, tmp_path)

    assert path == tmp_path / "cache/demo/fixes/checkpoint-fix-horizon.json"
    entry = DemoCacheEntry.model_validate_json(path.read_text())
    assert entry.step == "checkpoint.fix.horizon"
    assert entry.request.method == "GET"
    assert entry.request.path == "/fixes/horizon/NLB_759345596ILT_S1052222NCAM00275M1"
    assert entry.request.body is None
    assert (entry.status, entry.contract) == (200, "fix_result")
    served = tmp_path / "results/horizon/fixes/NLB_759345596ILT_S1052222NCAM00275M1.json"
    assert entry.response == json.loads(served.read_text())


def test_a_demo_fix_without_its_overlay_is_refused(tmp_path):
    fix = _fix_file(tmp_path, "NLB_759345596ILT_S1052222NCAM00275M1", with_overlay=False)

    with pytest.raises(FileNotFoundError, match="overlay"):
        write_demo_cache({"checkpoint.fix.horizon": fix}, tmp_path)


def test_a_rerun_drops_the_demo_fixes_it_no_longer_picks(tmp_path):
    old = _fix_file(tmp_path, "OLD")
    new = _fix_file(tmp_path, "NEW")
    write_demo_cache({"testlab.fix.horizon.OLD": old}, tmp_path)
    drone = tmp_path / "cache/demo/fixes/testlab-fix-drone-D1.json"
    drone.write_text("{}")

    write_demo_cache({"testlab.fix.horizon.NEW": new}, tmp_path)

    assert sorted(path.name for path in (tmp_path / "cache/demo/fixes").iterdir()) == [
        "testlab-fix-drone-D1.json",
        "testlab-fix-horizon-NEW.json",
    ]
