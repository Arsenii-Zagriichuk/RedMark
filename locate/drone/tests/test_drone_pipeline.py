"""Seam: the drone pipeline on one fixture frame, from raw pixels to a scored fix.

A frozen raw Navcam frame was rendered with NASA VICAR using the committed
flight 10 label, looking down on a synthetic map from a known position.
Straightening, cutting the search window, matching and fitting must put the
fix back on that position through the shared scorer. The stand-in matcher
finds the view in each map tile by normalised cross-correlation, so it only
succeeds if the straightened view really is the map, north up, at 25 cm.
"""

from pathlib import Path

import numpy as np
import pytest
import rasterio
from drone_stand_ins import ncc_matcher, smooth_noise
from PIL import Image
from rasterio.transform import from_origin

from contracts.models.common import Point, Provenance, TerrainType
from contracts.scoring import score_fix
from locate.drone.fix import build_fix_result
from locate.drone.label import read_drone_frame
from locate.drone.pipeline import PreviousPhoto, fix_frame, search_centre

LABEL = (
    Path(__file__).parents[3]
    / "prep"
    / "tests"
    / "fixtures"
    / "HNM_0152_0680432615_348FDR_N0100001HELI03026_0000LUJ05.xml"
)
RAW_FRAME = Path(__file__).with_name("fixtures") / "vicar-navcam.png"
RES = 0.25
MIN_X, MAX_Y = 4354000.0, 1092400.0
MAP_PX = 900  # 225 m square
# On whole map pixels from the west and north edges (112.5 m each), so the
# view's pixels line up with the map's and the stand-in matcher's whole-pixel
# shifts are exact.
TRUE_X, TRUE_Y = 4354112.5, 1092287.5
# Worked from the label's raw quaternions. HELI_G_FRAME rotates 113.2496°
# clockwise from north. The HELI_M_FRAME forward axis projects to about
# (0.89821, -0.39104) in that frame, a bearing of -23.5262° from its x-axis.
TRUE_HEADING_DEG = 89.7234


def test_first_fix_searches_around_the_onboard_position():
    assert search_centre((4354124.0, 1092270.0), previous=None) == (4354124.0, 1092270.0)


def test_later_fix_searches_around_the_previous_fix_moved_as_the_drone_moved():
    # The previous photo was fixed at (100, 200) while the drone thought it was
    # at (90, 195); since then the drone thinks it moved 40 m east and 15 m north.
    previous = PreviousPhoto(fix=(100.0, 200.0), onboard=(90.0, 195.0))
    assert search_centre((130.0, 210.0), previous=previous) == pytest.approx((140.0, 215.0))


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


def test_fixture_frame_is_fixed_where_it_was_rendered(photo_map):
    frame = read_drone_frame(LABEL.read_text())
    with Image.open(RAW_FRAME) as image:
        raw = np.array(image)

    # The search starts 7.9 m off, as from a drifted onboard position.
    _, _, drone_fix = fix_frame(raw, frame, photo_map, (TRUE_X + 6.3, TRUE_Y - 4.7), ncc_matcher)
    result = build_fix_result(
        photo_id=frame.file_stem,
        estimate=drone_fix,
        time_per_fix_s=0.0,
        terrain_type=TerrainType.textured,
        overlay="results/drone/overlays/fixture.png",
        provenance=Provenance(
            script="locate/drone/tests/test_drone_pipeline.py", commit="", inputs=[]
        ),
    )
    scored = score_fix(result, Point(x=TRUE_X, y=TRUE_Y), TRUE_HEADING_DEG)

    assert scored.truth.position_error_m < 0.1
    assert scored.truth.heading_error_deg < 0.5
