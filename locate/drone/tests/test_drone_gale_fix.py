"""Seam: the simulated Gale drone fix as a fix result, and its demo cache entry."""

import json
from pathlib import Path

import pytest
from locate.drone.gale_fix import DEMO_STEP, build_simulated_fix_result, write_demo_cache

from contracts.models.common import Method, Provenance, SiteId, TerrainType
from contracts.models.demo_cache import DemoCacheEntry
from contracts.models.fix_result import FixResult
from locate.drone.gale_view import Astronaut

PHOTO_ID = "gale-sim-drone-0001"
OVERLAY = f"results/drone/overlays/{PHOTO_ID}-loftr-run.png"
PHOTO = f"results/drone/overlays/{PHOTO_ID}-photo-run.png"


def _fix() -> FixResult:
    # Walking side by side, one facing 350° and one 10°: the crew faces north.
    crew = [
        Astronaut(position=(8142400.0, -285300.0), heading_deg=350.0),
        Astronaut(position=(8142403.0, -285304.0), heading_deg=10.0),
    ]
    return build_simulated_fix_result(
        photo_id=PHOTO_ID,
        crew=crew,
        time_per_fix_s=1.5,
        terrain_type=TerrainType.textured,
        overlay=OVERLAY,
        provenance=Provenance(script="locate/drone/gale_fix.py", commit="abc", inputs=[]),
    )


def test_gale_drone_fix_is_the_crew_labelled_simulated_with_no_truth():
    fix = _fix()

    assert fix.simulated is True
    assert fix.truth is None
    assert (fix.site, fix.method) == (SiteId.gale, Method.drone)
    assert (fix.position.x, fix.position.y) == pytest.approx((8142401.5, -285302.0))
    assert min(fix.heading_deg, 360 - fix.heading_deg) == pytest.approx(0.0, abs=1e-9)


def _publish(root: Path, fix: FixResult) -> None:
    for image in (OVERLAY, PHOTO):
        (root / image).parent.mkdir(parents=True, exist_ok=True)
        (root / image).write_bytes(b"png")
    path = root / "results" / "drone" / "fixes" / f"{fix.photo_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(fix.model_dump_json(indent=2))


def test_demo_cache_entry_replays_the_served_fix_with_its_images(tmp_path):
    fix = _fix()
    _publish(tmp_path, fix)

    written = write_demo_cache(fix.photo_id, [OVERLAY, PHOTO], tmp_path)

    entry = DemoCacheEntry.model_validate_json(written.read_text())
    assert entry.step == DEMO_STEP
    assert entry.request.method.value == "GET"
    assert entry.request.path == f"/fixes/drone/{PHOTO_ID}"
    assert entry.contract == "fix_result"
    served = tmp_path / "results" / "drone" / "fixes" / f"{PHOTO_ID}.json"
    assert entry.response == json.loads(served.read_text())
    assert written.parent == tmp_path / "cache" / "demo" / "fixes"
    for image in (OVERLAY, PHOTO):
        assert (tmp_path / "cache" / "demo" / "drone" / "overlays" / Path(image).name).is_file()


def test_demo_cache_refuses_a_fix_whose_images_are_missing(tmp_path):
    fix = _fix()
    _publish(tmp_path, fix)
    (tmp_path / PHOTO).unlink()

    with pytest.raises(FileNotFoundError, match="photo-run.png"):
        write_demo_cache(fix.photo_id, [OVERLAY, PHOTO], tmp_path)
