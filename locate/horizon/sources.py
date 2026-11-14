"""The terrain behind the Gale skylines, read from REDMARK_DATA.

Three tiers, finest first:

- the 1 m Gale terrain, in a window round the walk area, for the near skyline;
- a 10 m copy of the whole Gale file (averaged), for the middle distance;
- the HRSC and MOLA blended terrain at 200 m for everything beyond the Gale
  file: the top of Mount Sharp and most of the crater rim.

All are on the 3,396,190 m sphere. The Gale file is equirectangular with true
scale at the equator, the same frame as the site map; the blended crop is in
degrees of longitude and latitude, which on that sphere is the same frame
scaled by 59,274.7 m per degree, so no resampling is needed. The far tier is
shifted by the median height difference where it overlaps the Gale file, so
the two join without a step. The 10 m copy and the far crop are cached next
to the grid, since reading the whole 1 m file takes minutes.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.windows import Window, from_bounds

from contracts.models.common import Bounds
from locate.horizon.render import MARS_RADIUS_M, Raster, Terrain, Tier

GALE_DEM = "MSL_Gale_DEM_Mosaic_1m_v3.tif"
FAR_DEM = "terrain/Gale_HRSC_MOLA_BlendDEM_200mp_v2_crop.tif"
MID_RES_M = 10.0
NEAR_REACH_M = 1_000.0
FAR_REACH_M = 120_000.0
METRES_PER_DEGREE = MARS_RADIUS_M * np.pi / 180


@dataclass(frozen=True)
class GaleTerrain:
    terrain: Terrain
    far_offset_m: float
    """Added to the far tier's heights to join them to the Gale terrain."""
    tier_res_m: tuple[float, ...]


def load_gale_terrain(data_root: Path, walk_area: Bounds, cache_dir: Path) -> GaleTerrain:
    near = read_heights(data_root / GALE_DEM, _grow(walk_area, NEAR_REACH_M))
    mid = _cached(
        cache_dir / f"gale-{MID_RES_M:.0f}m.npz", lambda: _read_decimated(data_root / GALE_DEM)
    )
    reach = _grow(walk_area, FAR_REACH_M)
    far = _cached(
        cache_dir
        / f"far-200m-{reach.min_x:.0f}_{reach.min_y:.0f}_{reach.max_x:.0f}_{reach.max_y:.0f}.npz",
        lambda: read_heights(data_root / FAR_DEM, reach),
    )
    offset = height_offset(mid, far)
    far = Raster(far.heights + np.float32(offset), far.left, far.top, far.res)
    terrain = Terrain([Tier(near, NEAR_REACH_M), Tier(mid), Tier(far)])
    return GaleTerrain(terrain, offset, (near.res, mid.res, far.res))


def read_heights(path: Path, bounds: Bounds) -> Raster:
    """Heights inside bounds (map metres), as a raster in map metres.

    Works for files in the site's equirectangular metres and for files in
    degrees on the same sphere.
    """
    with rasterio.open(path) as src:
        scale = METRES_PER_DEGREE if src.crs.is_geographic else 1.0
        window = from_bounds(
            bounds.min_x / scale,
            bounds.min_y / scale,
            bounds.max_x / scale,
            bounds.max_y / scale,
            src.transform,
        )
        window = window.round_offsets().round_lengths()
        window = window.intersection(Window(0, 0, src.width, src.height))
        heights = src.read(1, window=window, masked=True).astype(np.float32).filled(np.nan)
        transform = src.window_transform(window)
    return Raster(
        heights, left=transform.c * scale, top=transform.f * scale, res=transform.a * scale
    )


def height_offset(gale: Raster, other: Raster) -> float:
    """Median of Gale minus the other height at the other's cells the Gale file covers."""
    rows, cols = np.indices(other.heights.shape)
    x = other.left + (cols.ravel() + 0.5) * other.res
    y = other.top - (rows.ravel() + 0.5) * other.res
    diff = gale.sample(x, y) - other.heights.ravel()
    return float(np.nanmedian(diff))


def _grow(bounds: Bounds, margin_m: float) -> Bounds:
    return Bounds(
        min_x=bounds.min_x - margin_m,
        min_y=bounds.min_y - margin_m,
        max_x=bounds.max_x + margin_m,
        max_y=bounds.max_y + margin_m,
    )


def _read_decimated(path: Path) -> Raster:
    with rasterio.open(path) as src:
        factor = MID_RES_M / src.res[0]
        shape = (round(src.height / factor), round(src.width / factor))
        heights = src.read(1, out_shape=shape, resampling=Resampling.average, masked=True)
        heights = heights.astype(np.float32).filled(np.nan)
        res = src.width * src.res[0] / shape[1]
    return Raster(heights, left=src.bounds.left, top=src.bounds.top, res=res)


def _cached(path: Path, read: Callable[[], Raster]) -> Raster:
    if path.exists():
        with np.load(path) as f:
            return Raster(f["heights"], float(f["left"]), float(f["top"]), float(f["res"]))
    raster = read()
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".partial.npz")
    np.savez(partial, heights=raster.heights, left=raster.left, top=raster.top, res=raster.res)
    partial.replace(path)  # never leave a half-written cache behind
    return raster
