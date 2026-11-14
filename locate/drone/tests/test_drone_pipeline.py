"""Seam: the drone pipeline on one fixture frame, from raw pixels to a scored fix.

A raw Navcam frame is rendered through the committed flight 10 label's own
camera and pose, looking down on a synthetic photo map from a known position.
Straightening, cutting the search window, matching and fitting must put the
fix back on that position through the shared scorer. The stand-in matcher
finds the view in each map tile by normalised cross-correlation, so it only
succeeds if the straightened view really is the map, north up, at 25 cm.
"""

from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from contracts.models.common import Point, Provenance, TerrainType
from contracts.scoring import score_fix
from locate.drone.fix import Matches, build_fix_result
from locate.drone.label import read_drone_frame
from locate.drone.pipeline import PreviousPhoto, fix_frame, search_centre

LABEL = (
    Path(__file__).parents[3]
    / "prep"
    / "tests"
    / "fixtures"
    / "HNM_0152_0680432615_348FDR_N0100001HELI03026_0000LUJ05.xml"
)
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


def _smooth_noise(size: int, sigma_px: float, seed: int) -> np.ndarray:
    radius = int(3 * sigma_px)
    kernel = np.exp(-0.5 * (np.arange(-radius, radius + 1) / sigma_px) ** 2)
    kernel /= kernel.sum()
    field = np.random.default_rng(seed).normal(size=(size, size))
    field = np.apply_along_axis(np.convolve, 0, field, kernel, mode="same")
    return np.apply_along_axis(np.convolve, 1, field, kernel, mode="same")


@pytest.fixture
def photo_map(tmp_path: Path) -> tuple[Path, np.ndarray]:
    noise = _smooth_noise(MAP_PX, sigma_px=2.0, seed=11)
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
    return crop, values.astype(np.float64)


def _map_value(values: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Bilinear map value at map metres (x, y); pixel centres at whole pixels + 0.5."""
    col = (x - MIN_X) / RES - 0.5
    row = (MAX_Y - y) / RES - 0.5
    c0, r0 = np.floor(col).astype(int), np.floor(row).astype(int)
    fc, fr = col - c0, row - r0
    return (
        values[r0, c0] * (1 - fc) * (1 - fr)
        + values[r0, c0 + 1] * fc * (1 - fr)
        + values[r0 + 1, c0] * (1 - fc) * fr
        + values[r0 + 1, c0 + 1] * fc * fr
    )


def _render_raw(frame, values: np.ndarray) -> np.ndarray:
    """What the Navcam sees from TRUE_X, TRUE_Y: ground points 5 cm apart,
    each projected through the camera, averaged per raw pixel."""
    offsets = np.arange(-34.0, 34.0, 0.05)
    east, north = (a.ravel() for a in np.meshgrid(offsets, offsets))
    height = -frame.camera_ned[2]
    # The ground point's offset from the camera in north, east, down, into the body.
    in_body = np.column_stack([north, east, np.full(east.size, height)]) @ frame.body_to_ned
    x, y = frame.camera.project(in_body + frame.camera.c)
    lines, samples = 480, 640
    seen = np.isfinite(x) & (x > -0.5) & (x < samples - 0.5) & (y > -0.5) & (y < lines - 0.5)
    cols, rows = np.round(x[seen]).astype(int), np.round(y[seen]).astype(int)
    brightness = _map_value(values, TRUE_X + east[seen], TRUE_Y + north[seen])
    total = np.zeros((lines, samples))
    count = np.zeros((lines, samples))
    np.add.at(total, (rows, cols), brightness)
    np.add.at(count, (rows, cols), 1)
    raw = np.where(count > 0, total / np.maximum(count, 1), np.nan)
    for _ in range(3):  # fill the few pixels no ground point landed in
        padded = np.pad(raw, 1, constant_values=np.nan)
        neighbours = np.stack(
            [
                padded[1 + dr : 1 + dr + lines, 1 + dc : 1 + dc + samples]
                for dr in (-1, 0, 1)
                for dc in (-1, 0, 1)
            ]
        )
        known = np.isfinite(neighbours)
        mean = np.where(known, neighbours, 0).sum(axis=0) / np.maximum(known.sum(axis=0), 1)
        raw = np.where(np.isnan(raw) & known.any(axis=0), mean, raw)
    return np.nan_to_num(raw, nan=2000.0).astype(np.uint16)


def _correlate(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """c[k] = sum_p a[p] * b[p + k - (a.shape - 1)], for every overlap."""
    shape = (a.shape[0] + b.shape[0] - 1, a.shape[1] + b.shape[1] - 1)
    spectrum = np.fft.rfft2(a[::-1, ::-1], shape) * np.fft.rfft2(b, shape)
    return np.fft.irfft2(spectrum, shape)


def ncc_matcher(query: np.ndarray, reference: np.ndarray) -> Matches:
    """Finds the shift that best lines up the view's seen pixels (non-zero)
    with the tile, by normalised cross-correlation, and returns a grid of
    matches at that shift if the correlation is strong."""
    seen = (query > 0).astype(np.float64)
    q = query.astype(np.float64) * seen
    t = reference.astype(np.float64)
    ones = np.ones_like(t)
    n = _correlate(seen, ones)
    sum_q, sum_q2 = _correlate(q, ones), _correlate(q * q, ones)
    sum_t, sum_t2 = _correlate(seen, t), _correlate(seen, t * t)
    sum_qt = _correlate(q, t)
    with np.errstate(invalid="ignore", divide="ignore"):
        cov = sum_qt - sum_q * sum_t / n
        ncc = cov / np.sqrt((sum_q2 - sum_q**2 / n) * (sum_t2 - sum_t**2 / n))
    ncc[n < 0.6 * seen.sum()] = -1
    k = np.unravel_index(np.nanargmax(ncc), ncc.shape)
    if ncc[k] < 0.8:
        return Matches(query_xy=np.empty((0, 2)), reference_xy=np.empty((0, 2)))
    shift = np.array([k[1] - (query.shape[1] - 1), k[0] - (query.shape[0] - 1)], dtype=float)
    rows, cols = np.mgrid[4 : query.shape[0] : 8, 4 : query.shape[1] : 8]
    grid = np.column_stack([cols.ravel(), rows.ravel()]).astype(float)
    grid = grid[seen[grid[:, 1].astype(int), grid[:, 0].astype(int)] > 0]
    moved = grid + shift
    inside = np.all((moved >= 0) & (moved <= np.array(reference.shape[::-1]) - 1), axis=1)
    return Matches(query_xy=grid[inside], reference_xy=moved[inside])


def test_fixture_frame_is_fixed_where_it_was_rendered(photo_map):
    crop, values = photo_map
    frame = read_drone_frame(LABEL.read_text())
    raw = _render_raw(frame, values)

    # The search starts 7.9 m off, as from a drifted onboard position.
    _, _, drone_fix = fix_frame(raw, frame, crop, (TRUE_X + 6.3, TRUE_Y - 4.7), ncc_matcher)
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
