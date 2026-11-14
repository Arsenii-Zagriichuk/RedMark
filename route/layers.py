"""Read the layers a route needs onto one planning grid over the site's walk area.

The rasters are GeoTIFFs named in sites/<site>.yaml `files`, relative to REDMARK_DATA:
`slope` (degrees), `sand` (non-zero on loose sand) and `ridges` (non-zero on a boxwork
ridge). Each planning cell keeps the worst value of the pixels inside it, so a steep
metre is never averaged away. A site config with no `slope` file plans on flat stub
ground; a missing sand or ridge file means none. A cell holding any pixel with no data,
or reaching past the edge of the file, has no data.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.warp import reproject, transform_bounds
from rasterio.windows import Window, from_bounds

from contracts.models.site import SiteConfig
from route.engine import CostGrid

# Planning cell size: coarse enough that a route over the 4 km walk area comes back in seconds.
PLANNING_CELL_M = 4.0
# Stands in for a pixel with no data while cells take their highest pixel, so any such
# pixel makes the whole cell unknown instead of being skipped.
_UNKNOWN = np.finfo(np.float32).max


def load_grid(site: SiteConfig, data_root: Path, cell_m: float = PLANNING_CELL_M) -> CostGrid:
    b = site.bounds
    shape = (math.ceil((b.max_y - b.min_y) / cell_m), math.ceil((b.max_x - b.min_x) / cell_m))
    b_box = (b.min_x, b.max_y - shape[0] * cell_m, b.min_x + shape[1] * cell_m, b.max_y)

    def read(key: str) -> np.ndarray | None:
        if key not in site.files:
            return None
        path = data_root / site.files[key]
        if not path.is_file():
            raise FileNotFoundError(f"{key} layer {path} named in the {site.site} site config")
        with rasterio.open(path) as src:
            src_crs = src.crs or site.projection
            window = _covering(
                from_bounds(*transform_bounds(site.projection, src_crs, *b_box), src.transform)
            )
            band = src.read(1, window=window, boundless=True, masked=True)
            src_transform = src.window_transform(window)
        unknown = np.ma.getmaskarray(band) | ~np.isfinite(band.filled(0))
        values = np.where(unknown, _UNKNOWN, band.filled(0)).astype(np.float32)
        out = np.full(shape, _UNKNOWN, dtype=np.float32)
        reproject(
            source=values,
            destination=out,
            src_transform=src_transform,
            src_crs=src_crs,
            dst_transform=from_origin(b.min_x, b.max_y, cell_m, cell_m),
            dst_crs=site.projection,
            resampling=Resampling.max,
            init_dest_nodata=False,
        )
        out[out >= _UNKNOWN] = np.nan
        return out

    slope, sand, ridge = read("slope"), read("sand"), read("ridges")
    return CostGrid(
        site=site.site,
        min_x=b.min_x,
        max_y=b.max_y,
        cell_m=cell_m,
        slope_deg=np.zeros(shape) if slope is None else slope,
        sand=np.zeros(shape, dtype=bool) if sand is None else sand > 0,
        ridge=np.zeros(shape, dtype=bool) if ridge is None else ridge > 0,
    )


def _covering(window: Window) -> Window:
    """The whole-pixel window that covers a fractional one."""
    col0, row0 = math.floor(round(window.col_off, 6)), math.floor(round(window.row_off, 6))
    col1 = math.ceil(round(window.col_off + window.width, 6))
    row1 = math.ceil(round(window.row_off + window.height, 6))
    return Window(col0, row0, col1 - col0, row1 - row0)
