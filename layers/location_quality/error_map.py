"""The error map (layer 5, P3-06): the horizon fix error each map cell can expect.

The horizon test on the hidden pile (results/horizon/horizon-gale.json) measured
the median error by terrain type (textured, plain) and for stops in a hollow.
Each cell gets the class a stop there would get, by the same rules as the test
(locate/horizon/stop_terrain.py), and the median error measured for that class:
a hollow's when the cell is a hollow, since nearby ridges hiding the skyline is
the larger effect, and otherwise its terrain type's.

The location-quality score multiplies the share of landmarks a cell sees by how
its expected error compares with the best class's: 1 for a cell that sees all
the landmarks from the class with the lowest median error.
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.signal import correlate

from contracts.models.test_summary import TestSummary
from locate.horizon.stop_terrain import (
    HOLLOW_DEPTH_M,
    HOLLOW_RADIUS_M,
    ROUGH_RADIUS_M,
    ROUGH_TEXTURED_M,
    STOP_RADIUS_M,
)


@dataclass(frozen=True)
class CellTerrain:
    """Per cell: textured or plain, hollow or not, and whether the terrain was there to say."""

    textured: np.ndarray
    hollow: np.ndarray
    known: np.ndarray
    """False where the ground within ROUGH_RADIUS_M has a cell with no height."""


def classify_cells(heights: np.ndarray, res_m: float) -> CellTerrain:
    """Each cell's terrain type and hollow flag, by the horizon test's stop rules.

    Textured: the ground within ROUGH_RADIUS_M departs from its best-fit plane by
    more than ROUGH_TEXTURED_M (root mean square). Hollow: the mean ground within
    HOLLOW_RADIUS_M stands more than HOLLOW_DEPTH_M above the mean within
    STOP_RADIUS_M. Cells closer to the edge than ROUGH_RADIUS_M are not known.
    """
    finite = np.isfinite(heights)
    z = np.where(finite, heights - np.nanmean(heights), 0.0).astype(np.float64)

    # Best-fit plane over a full disk round each cell. The disk is symmetric, so the
    # plane's slopes and offset separate: offset = mean z, slope along x = sum(dx z) / sum(dx^2).
    dy, dx, disk = _disk(ROUGH_RADIUS_M, res_m)
    n = disk.sum()
    s2 = (dx**2 * disk).sum()
    sum_z = _window_sum(z, disk)
    sum_zz = _window_sum(z**2, disk)
    sum_xz = _window_sum(z, dx * disk)
    sum_yz = _window_sum(z, dy * disk)
    residual = sum_zz - sum_z**2 / n - (sum_xz**2 + sum_yz**2) / s2
    roughness = np.sqrt(np.maximum(residual, 0.0) / n)
    known = _window_sum(finite.astype(np.float64), disk) > n - 0.5
    reach = int(ROUGH_RADIUS_M / res_m)
    known[:reach], known[-reach:], known[:, :reach], known[:, -reach:] = False, False, False, False

    stop = _window_mean(z, finite, _disk(STOP_RADIUS_M, res_m)[2])
    around = _window_mean(z, finite, _disk(HOLLOW_RADIUS_M, res_m)[2])
    return CellTerrain(
        textured=known & (roughness > ROUGH_TEXTURED_M),
        hollow=known & (around - stop > HOLLOW_DEPTH_M),
        known=known,
    )


HOLLOW_GROUP = "hollow"
"""The horizon test's group of stops in a hollow (locate/horizon/hidden_test.py)."""


@dataclass(frozen=True)
class ErrorMedians:
    """Median horizon fix error, ground metres, measured for each class of stop."""

    textured_m: float
    plain_m: float
    hollow_m: float

    @property
    def lowest_m(self) -> float:
        return min(self.textured_m, self.plain_m, self.hollow_m)


def read_medians(summary: Path) -> ErrorMedians:
    """The median errors from a test summary file (the test_summary contract)."""
    groups = TestSummary.model_validate_json(summary.read_text()).groups
    extra = groups.model_extra or {}
    if HOLLOW_GROUP not in extra:
        raise ValueError(f"{summary} has no {HOLLOW_GROUP!r} group to take a hollow's error from")
    return ErrorMedians(
        textured_m=groups.textured.median_error_m,
        plain_m=groups.plain.median_error_m,
        hollow_m=extra[HOLLOW_GROUP].median_error_m,
    )


def error_map(cells: CellTerrain, medians: ErrorMedians) -> np.ndarray:
    """Expected horizon fix error per cell, ground metres; NaN where the terrain isn't known."""
    by_type = np.where(cells.textured, medians.textured_m, medians.plain_m)
    errors = np.where(cells.hollow, medians.hollow_m, by_type).astype(np.float32)
    errors[~cells.known] = np.nan
    return errors


def location_quality_score(share: np.ndarray, errors: np.ndarray, *, lowest_m: float) -> np.ndarray:
    """The share of landmarks in view, times the best class's error over the cell's (0 to 1)."""
    return (share * (lowest_m / errors)).astype(np.float32)


def _disk(radius_m: float, res_m: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Offsets north (dy) and east (dx) in metres, and the disk of offsets within radius_m."""
    r = int(radius_m / res_m)
    rows, cols = np.mgrid[-r : r + 1, -r : r + 1]
    dy, dx = -rows * res_m, cols * res_m
    return dy, dx, (np.hypot(dx, dy) <= radius_m).astype(np.float64)


def _window_sum(values: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """For each cell, the sum of kernel x values over the window centred on it."""
    return correlate(values, kernel, mode="same", method="fft")


def _window_mean(values: np.ndarray, finite: np.ndarray, disk: np.ndarray) -> np.ndarray:
    """Mean of the finite values within the disk round each cell."""
    count = _window_sum(finite.astype(np.float64), disk)
    return _window_sum(values, disk) / np.maximum(count, 1.0)
