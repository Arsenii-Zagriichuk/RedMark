"""The error map (layer 5, P3-06) on made-up terrain. Expected values are worked by hand."""

import json

import numpy as np
import pytest

from layers.location_quality.error_map import (
    CellTerrain,
    classify_cells,
    error_map,
    location_quality_score,
    read_medians,
)
from locate.horizon.stop_terrain import is_hollow, terrain_type

RES_M = 1.0
SIZE = 201  # 201 x 201 cells of 1 m; the centre cell is (100, 100)
CENTRE = (100, 100)


def grid() -> tuple[np.ndarray, np.ndarray]:
    """x east and y north of the centre cell, in metres, for every cell."""
    offsets = (np.arange(SIZE) - SIZE // 2) * RES_M
    return np.meshgrid(offsets, -offsets)


def test_a_tilted_plane_is_plain_and_never_a_hollow():
    x, y = grid()
    heights = 0.2 * x + 0.1 * y  # a steady 12° slope with no bumps
    cells = classify_cells(heights, RES_M)
    assert not cells.textured[CENTRE]
    assert not cells.hollow[CENTRE]
    assert cells.known[CENTRE]


def test_corrugations_half_a_metre_high_are_textured():
    # Ridges 0.5 m high every 4 m: root mean square 0.35 m about the plane, over the 0.15 m bar.
    x, _ = grid()
    heights = 0.5 * np.sin(2 * np.pi * x / 4.0)
    cells = classify_cells(heights, RES_M)
    assert cells.textured[CENTRE]


def test_a_bowl_centre_is_a_hollow_and_its_rim_is_not():
    # A bowl 3 m deep and 30 m across in flat ground: the mean ground within 50 m of the
    # centre stands well over 1 m above it. 80 m out on flat ground nothing is lower.
    x, y = grid()
    r = np.hypot(x, y)
    heights = np.where(r < 15, -3.0 * (1 - (r / 15) ** 2), 0.0)
    cells = classify_cells(heights, RES_M)
    assert cells.hollow[CENTRE]
    assert not cells.hollow[100, 180]


def test_the_cell_classes_agree_with_the_horizon_tests_stop_classes():
    # The error map lends each cell the error measured at stops of its class, so a cell
    # must fall in the class the horizon test would give a stop there.
    rng = np.random.default_rng(7)
    x, y = grid()
    bumps = np.where(x > 0, 0.4, 0.02) * rng.standard_normal((SIZE, SIZE))
    heights = 0.05 * x + bumps - 2.0 * np.exp(-(x**2 + y**2) / 30.0**2)
    cells = classify_cells(heights, RES_M)
    for row, col in [(100, 100), (100, 60), (100, 140), (60, 100), (140, 140)]:
        window = heights[row - 51 : row + 52, col - 51 : col + 52]
        assert cells.textured[row, col] == (terrain_type(window, RES_M).value == "textured")
        assert cells.hollow[row, col] == is_hollow(window, RES_M)


def metrics(median_error_m: float) -> dict:
    return {
        "n": 4,
        "median_error_m": median_error_m,
        "within_1m_pct": 0.0,
        "within_5m_pct": 0.0,
        "within_10m_pct": 0.0,
        "median_heading_error_deg": 1.0,
        "median_time_per_fix_s": 4.0,
    }


def summary_file(tmp_path, medians: dict[str, float]):
    """A test summary in the contract with the given median error per group."""
    path = tmp_path / "horizon-gale.json"
    summary = {
        "test": "horizon-gale",
        "site": "gale",
        "method": "horizon",
        "simulated": False,
        "overall": metrics(100.0),
        "groups": {name: metrics(m) for name, m in medians.items()},
        "provenance": {"script": "locate/horizon/hidden_test.py", "commit": "abc", "inputs": []},
    }
    path.write_text(json.dumps(summary))
    return path


def test_each_cell_gets_the_median_error_measured_for_its_class(tmp_path):
    summary = summary_file(
        tmp_path, {"textured": 50.0, "plain": 150.0, "hollow": 260.0, "ridge_top_or_open": 80.0}
    )
    # Four cells: textured open ground, plain open ground, a textured hollow, unknown.
    cells = CellTerrain(
        textured=np.array([[True, False, True, False]]),
        hollow=np.array([[False, False, True, False]]),
        known=np.array([[True, True, True, False]]),
    )
    medians = read_medians(summary)
    errors = error_map(cells, medians)
    np.testing.assert_array_equal(errors[0, :3], [50.0, 150.0, 260.0])
    assert np.isnan(errors[0, 3])
    assert medians.lowest_m == 50.0


def test_a_summary_without_a_hollow_group_says_so(tmp_path):
    summary = summary_file(tmp_path, {"textured": 50.0, "plain": 150.0})
    with pytest.raises(ValueError, match="hollow"):
        read_medians(summary)


def test_the_score_is_the_landmark_share_scaled_by_the_best_class_error_over_the_cells():
    # Half the landmarks from plain ground (150 m) when textured ground does 50 m: 0.5 x 50/150.
    share = np.array([[0.5, 1.0, 1.0, 0.75]])
    errors = np.array([[150.0, 50.0, 260.0, np.nan]])
    score = location_quality_score(share, errors, lowest_m=50.0)
    np.testing.assert_allclose(score[0, :3], [1 / 6, 1.0, 50 / 260])
    assert np.isnan(score[0, 3])
