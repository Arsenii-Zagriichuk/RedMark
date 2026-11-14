"""The terrain behind the Gale skylines, read from REDMARK_DATA.

Three tiers, finest first:

- the 1 m Gale terrain, in a window round the walk area, for the near skyline;
- a 10 m copy of the whole Gale file (averaged), for the middle distance;
- MOLA at 463 m for everything beyond the Gale file: the top of Mount Sharp
  and most of the crater rim.

Both files are equirectangular on the 3,396,190 m sphere with true scale at
the equator, the same frame as the site map, so no reprojection is needed.
MOLA is shifted by the median height difference where the two overlap, so
the two sources join without a step. The 10 m copy and the MOLA crop are
cached next to the grid, since reading the whole 1 m file takes minutes.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.windows import Window, from_bounds

from contracts.models.common import Bounds
from locate.horizon.render import Raster, Terrain, Tier

GALE_DEM = "MSL_Gale_DEM_Mosaic_1m_v3.tif"
MOLA_DEM = "Mars_MGS_MOLA_DEM_mosaic_global_463m.tif"
MID_RES_M = 10.0
NEAR_REACH_M = 1_000.0
FAR_REACH_M = 120_000.0


@dataclass(frozen=True)
class GaleTerrain:
    terrain: Terrain
    mola_offset_m: float
    """Added to MOLA heights to join them to the Gale terrain."""
    tier_res_m: tuple[float, ...]


def load_gale_terrain(data_root: Path, walk_area: Bounds, cache_dir: Path) -> GaleTerrain:
    near = _read_window(data_root / GALE_DEM, _grow(walk_area, NEAR_REACH_M))
    mid = _cached(
        cache_dir / f"gale-{MID_RES_M:.0f}m.npz", lambda: _read_decimated(data_root / GALE_DEM)
    )
    far = _grow(walk_area, FAR_REACH_M)
    mola = _cached(
        cache_dir / f"mola-{far.min_x:.0f}_{far.min_y:.0f}_{far.max_x:.0f}_{far.max_y:.0f}.npz",
        lambda: _read_window(data_root / MOLA_DEM, far),
    )
    offset = mola_offset(mid, mola)
    mola = Raster(mola.heights + np.float32(offset), mola.left, mola.top, mola.res)
    terrain = Terrain([Tier(near, NEAR_REACH_M), Tier(mid), Tier(mola)])
    return GaleTerrain(terrain, offset, (near.res, mid.res, mola.res))


def mola_offset(gale: Raster, mola: Raster) -> float:
    """Median of Gale minus MOLA height at the MOLA cells the Gale file covers."""
    rows, cols = np.indices(mola.heights.shape)
    x = mola.left + (cols.ravel() + 0.5) * mola.res
    y = mola.top - (rows.ravel() + 0.5) * mola.res
    diff = gale.sample(x, y) - mola.heights.ravel()
    return float(np.nanmedian(diff))


def _grow(bounds: Bounds, margin_m: float) -> Bounds:
    return Bounds(
        min_x=bounds.min_x - margin_m,
        min_y=bounds.min_y - margin_m,
        max_x=bounds.max_x + margin_m,
        max_y=bounds.max_y + margin_m,
    )


def _read_window(path: Path, bounds: Bounds) -> Raster:
    with rasterio.open(path) as src:
        window = from_bounds(bounds.min_x, bounds.min_y, bounds.max_x, bounds.max_y, src.transform)
        window = window.round_offsets().round_lengths()
        window = window.intersection(Window(0, 0, src.width, src.height))
        heights = src.read(1, window=window, masked=True).astype(np.float32).filled(np.nan)
        transform = src.window_transform(window)
    return Raster(heights, left=transform.c, top=transform.f, res=transform.a)


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
