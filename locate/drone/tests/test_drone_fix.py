"""Seam: the drone pipeline from matches to a scored fix result.

A frame scored against its own answer key must give zero error, which proves
the matcher and the key share a frame. Here the "answer key" is a position and
heading we choose; a stand-in matcher returns the exact correspondences a
perfect matcher would, plus outliers, and the fix must come back exactly there
through the shared scorer.

Pixel convention (the matchers' own): pixel centres sit at whole numbers, so
the centre of a window's top-left pixel is (min_x + res/2, max_y - res/2).
"""

import math

import numpy as np
import pytest

from contracts.models.common import Point, Provenance, TerrainType
from contracts.models.fix_result import FixResult
from contracts.scoring import score_fix
from locate.drone.fix import GroundView, MapWindow, Matches, build_fix_result, locate_on_map

RES = 0.25
MIN_X, MAX_Y = 4354000.0, 1092400.0  # the map window's west and north edges
TRUE_X, TRUE_Y = 4354037.6, 1092347.3  # where the drone really was
# Worked by hand: 37.6 m east of the west edge is 150.4 pixel widths, so the
# pixel centre is at x = 149.9; 52.7 m south of the north edge gives y = 210.3.
TRUE_PX = np.array([149.9, 210.3])
NADIR = np.array([95.0, 70.0])  # the nadir's pixel in the ground view
GRID_COLS, GRID_ROWS = np.meshgrid(np.arange(10, 180, 12.0), np.arange(10, 130, 12.0))
GRID = np.column_stack([GRID_COLS.ravel(), GRID_ROWS.ravel()])  # ground-view pixels a matcher finds


# The map window is noise, so every tile of it is unique and a stand-in
# matcher can tell which part of the window it was given.
WINDOW_IMAGE = np.random.default_rng(3).integers(0, 256, size=(400, 400), dtype=np.uint8)


class ExactMatcher:
    """A perfect matcher with a share of wrong matches mixed in: for a grid of
    ground-view pixels it returns where they truly are, if that is inside the
    map tile it was given, in that tile's own pixels."""

    def __init__(self, rotation_deg: float, scale: float, outlier_share: float):
        angle = math.radians(rotation_deg)
        self.linear = scale * np.array(
            [[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]]
        )
        self.outlier_share = outlier_share
        self.seen_shapes: list[tuple] = []
        self.rng = np.random.default_rng(7)

    def _tile_offset(self, tile: np.ndarray) -> np.ndarray:
        rows = np.lib.stride_tricks.sliding_window_view(WINDOW_IMAGE, (1, 16))[:, :, 0, :]
        (row, col), *_ = np.argwhere(np.all(rows == tile[0, :16], axis=-1))
        assert np.array_equal(
            WINDOW_IMAGE[row : row + tile.shape[0], col : col + tile.shape[1]], tile
        )
        return np.array([col, row])

    def __call__(self, query: np.ndarray, reference: np.ndarray) -> Matches:
        self.seen_shapes.append((query.shape, reference.shape))
        query_xy = GRID.copy()
        in_window = (query_xy - NADIR) @ self.linear.T + TRUE_PX
        ref_xy = in_window - self._tile_offset(reference)
        height, width = reference.shape
        seen = (ref_xy[:, 0] >= 0) & (ref_xy[:, 0] <= width - 1)
        seen &= (ref_xy[:, 1] >= 0) & (ref_xy[:, 1] <= height - 1)
        query_xy, ref_xy = query_xy[seen], ref_xy[seen]
        wrong = self.rng.random(len(query_xy)) < self.outlier_share
        ref_xy[wrong] = self.rng.uniform(0, min(width, height) - 1, size=(wrong.sum(), 2))
        return Matches(query_xy=query_xy, reference_xy=ref_xy)


def _views() -> tuple[GroundView, MapWindow]:
    ground = GroundView(
        image=np.zeros((140, 190), dtype=np.uint8),
        valid=np.ones((140, 190), dtype=bool),
        resolution=RES,
        nadir_px=NADIR,
        heading_deg=200.0,  # the onboard heading the view was drawn with
    )
    window = MapWindow(image=WINDOW_IMAGE, min_x=MIN_X, max_y=MAX_Y, resolution=RES)
    return ground, window


@pytest.mark.parametrize(
    ("rotation_deg", "scale", "true_heading_deg"),
    [(0.0, 1.0, 200.0), (7.0, 1.03, 207.0), (-170.0, 0.98, 30.0)],
)
def test_fix_scored_against_its_own_key_has_zero_error(rotation_deg, scale, true_heading_deg):
    # Rotating the ground view clockwise on the map (a positive angle with
    # rows pointing down) turns the onboard heading clockwise by that angle.
    ground, window = _views()
    matcher = ExactMatcher(rotation_deg, scale, outlier_share=0.3)

    estimate = locate_on_map(ground, window, matcher)
    fix = build_fix_result(
        photo_id="frame-under-test",
        estimate=estimate,
        time_per_fix_s=1.5,
        terrain_type=TerrainType.textured,
        overlay="results/drone/overlays/frame-under-test.png",
        provenance=Provenance(script="locate/drone/tests/test_drone_fix.py", commit="", inputs=[]),
    )
    scored = score_fix(fix, Point(x=TRUE_X, y=TRUE_Y), true_heading_deg)

    # The window is searched in tiles the size of the ground view.
    assert len(matcher.seen_shapes) > 1
    assert set(matcher.seen_shapes) == {((140, 190), (140, 190))}
    assert scored.truth.position_error_m == pytest.approx(0, abs=0.001)
    assert scored.truth.heading_error_deg == pytest.approx(0, abs=0.01)
    # Overlapping tiles see each true match more than once; most of the grid
    # survives RANSAC, each match counted once.
    assert 0.8 * len(GRID) <= estimate.inliers <= len(GRID)


def test_fix_result_is_a_real_drone_fix_at_jezero():
    ground, window = _views()
    estimate = locate_on_map(ground, window, ExactMatcher(0, 1, outlier_share=0))
    fix = build_fix_result(
        photo_id="frame-under-test",
        estimate=estimate,
        time_per_fix_s=1.5,
        terrain_type=TerrainType.plain,
        overlay="results/drone/overlays/frame-under-test.png",
        provenance=Provenance(script="locate/drone/first_fix.py", commit="abc", inputs=[]),
    )
    FixResult.model_validate(fix.model_dump(mode="json"))
    assert (fix.site.value, fix.method.value, fix.simulated) == ("jezero", "drone", False)
    assert fix.truth is None
    assert fix.terrain_type == TerrainType.plain


def test_too_few_matches_is_no_fix():
    ground, window = _views()
    with pytest.raises(ValueError, match="no fix"):
        locate_on_map(ground, window, ExactMatcher(0, 1, outlier_share=0.97))
