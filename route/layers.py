"""Read the layers a route needs onto one planning grid over the site's walk area.

The rasters are GeoTIFFs named in sites/<site>.yaml `files`, relative to REDMARK_DATA:
`slope` (degrees), `sand` (non-zero on loose sand) and `ridges` (non-zero on a boxwork
ridge). Each planning cell keeps the worst value of the pixels inside it, so a steep
metre is never averaged away. A site config with no `slope` file plans on flat stub
ground; a missing sand or ridge file means none.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.warp import reproject

from contracts.models.site import SiteConfig
from route.engine import CostGrid

# Planning cell size: coarse enough that a route over the 4 km walk area comes back in seconds.
PLANNING_CELL_M = 4.0


def load_grid(site: SiteConfig, data_root: Path, cell_m: float = PLANNING_CELL_M) -> CostGrid:
    b = site.bounds
    shape = (math.ceil((b.max_y - b.min_y) / cell_m), math.ceil((b.max_x - b.min_x) / cell_m))

    def read(key: str) -> np.ndarray | None:
        if key not in site.files:
            return None
        path = data_root / site.files[key]
        if not path.is_file():
            raise FileNotFoundError(f"{key} layer {path} named in the {site.site} site config")
        out = np.full(shape, np.nan, dtype=np.float32)
        with rasterio.open(path) as src:
            reproject(
                source=rasterio.band(src, 1),
                destination=out,
                src_crs=src.crs or site.projection,
                dst_transform=from_origin(b.min_x, b.max_y, cell_m, cell_m),
                dst_crs=site.projection,
                dst_nodata=np.nan,
                resampling=Resampling.max,
            )
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
