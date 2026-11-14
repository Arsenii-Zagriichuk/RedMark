"""Each tested stop's terrain type and whether it is a hollow, from the 1 m terrain.

Both come from the heights round the stop, so they are reproducible and
need no one to judge photos by eye:

- **Hollow:** the stop sits more than HOLLOW_DEPTH_M below the mean height of
  the ground within HOLLOW_RADIUS_M, low ground where nearby ridges can hide
  the skyline. Anything else is ridge top or open ground. A steady slope is
  never a hollow, since a plane's mean over a circle is its centre height.
- **Terrain type:** textured (ridges, rock) when the ground within
  ROUGH_RADIUS_M departs from its best-fit plane by more than ROUGH_TEXTURED_M
  (root mean square); plain (sand) otherwise.
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from contracts.models.common import Bounds, TerrainType
from locate.horizon.sources import read_heights

HOLLOW_RADIUS_M = 50.0
HOLLOW_DEPTH_M = 1.0
STOP_RADIUS_M = 2.0
"""The stop's own height is the mean within this, so one noisy pixel can't decide."""
ROUGH_RADIUS_M = 10.0
ROUGH_TEXTURED_M = 0.15


@dataclass(frozen=True)
class StopTerrain:
    terrain_type: TerrainType
    hollow: bool


def classify_stop(dem: Path, x: float, y: float) -> StopTerrain:
    """The terrain type and hollow flag of the stop at map (x, y), from the 1 m terrain file."""
    reach = HOLLOW_RADIUS_M + 1
    raster = read_heights(
        dem, Bounds(min_x=x - reach, min_y=y - reach, max_x=x + reach, max_y=y + reach)
    )
    return StopTerrain(
        terrain_type(raster.heights, raster.res), is_hollow(raster.heights, raster.res)
    )


def is_hollow(heights: np.ndarray, res_m: float) -> bool:
    """Whether the window's centre is a hollow; heights is a square window round it."""
    r = _radius_m(heights, res_m)
    stop = np.nanmean(heights[r <= STOP_RADIUS_M])
    around = np.nanmean(heights[r <= HOLLOW_RADIUS_M])
    return bool(around - stop > HOLLOW_DEPTH_M)


def terrain_type(heights: np.ndarray, res_m: float) -> TerrainType:
    """Textured or plain, by the roughness round the window's centre."""
    r = _radius_m(heights, res_m)
    rows, cols = np.nonzero((r <= ROUGH_RADIUS_M) & np.isfinite(heights))
    z = heights[rows, cols].astype(np.float64)
    design = np.column_stack([cols * res_m, rows * res_m, np.ones_like(z)])
    plane, *_ = np.linalg.lstsq(design, z, rcond=None)
    roughness = np.sqrt(np.mean((z - design @ plane) ** 2))
    return TerrainType.textured if roughness > ROUGH_TEXTURED_M else TerrainType.plain


def _radius_m(heights: np.ndarray, res_m: float) -> np.ndarray:
    rows, cols = np.indices(heights.shape)
    centre_row, centre_col = (heights.shape[0] - 1) / 2, (heights.shape[1] - 1) / 2
    return np.hypot(rows - centre_row, cols - centre_col) * res_m
