"""Cut the walk area out of a Gale source that is already in the site projection.

The Gale photo map, terrain and THEMIS mosaic all share the site projection,
so a crop is a window on the source's own pixel grid: no resampling, every
value as published. The window is snapped outward to whole source pixels, so
the crop covers the asked bounds and overshoots by less than a pixel a side.
"""

import math
import uuid
from pathlib import Path

import rasterio
from rasterio.crs import CRS
from rasterio.windows import Window

Bounds = tuple[float, float, float, float]  # min_x, min_y, max_x, max_y
# GeoTIFF tag naming the source a crop was cut from, so a rerun can skip it.
SOURCE_TAG = "REDMARK_SOURCE"
# A source edge counts as a pixel edge if it is this close (in pixels).
_SNAP = 1e-6


def crop_on_source_grid(
    source: Path, bounds: Bounds, out: Path, projection: str, source_id: str = ""
) -> Bounds:
    """Write the source pixels covering `bounds` to `out`; return the crop's bounds.

    Raises ValueError if the source is not in `projection` or does not cover
    `bounds`. The crop appears at `out` only once it is complete.
    """
    with rasterio.open(source) as src:
        if src.crs != CRS.from_proj4(projection):
            raise ValueError(f"{source} is not in the site projection {projection}")
        window = _window_covering(src, bounds)
        if window.intersection(Window(0, 0, src.width, src.height)) != window:
            raise ValueError(f"{bounds} reaches outside {source}")
        data = src.read(1, window=window)
        transform = src.window_transform(window)
        profile = {
            "driver": "GTiff",
            "width": window.width,
            "height": window.height,
            "count": 1,
            "dtype": src.dtypes[0],
            "crs": src.crs,
            "transform": transform,
            "nodata": src.nodata,
            "tiled": True,
            "blockxsize": 512,
            "blockysize": 512,
            "compress": "deflate",
            "predictor": 3 if data.dtype.kind == "f" else 2,
            "BIGTIFF": "IF_SAFER",
        }
    out.parent.mkdir(parents=True, exist_ok=True)
    partial = out.with_name(f"{out.name}.{uuid.uuid4().hex}.part")
    with rasterio.open(partial, "w", **profile) as dst:
        dst.write(data, 1)
        dst.update_tags(**{SOURCE_TAG: source_id})
    partial.replace(out)
    with rasterio.open(out) as written:
        return tuple(written.bounds)


def crop_is_current(crop: Path, source_id: str) -> bool:
    """`crop` exists and was cut from the source version `source_id`."""
    if not crop.exists():
        return False
    with rasterio.open(crop) as src:
        return src.tags().get(SOURCE_TAG) == source_id


def _window_covering(src: rasterio.DatasetReader, bounds: Bounds) -> Window:
    min_x, min_y, max_x, max_y = bounds
    inverse = ~src.transform
    col0, row0 = inverse @ (min_x, max_y)
    col1, row1 = inverse @ (max_x, min_y)
    col0, row0 = math.floor(col0 + _SNAP), math.floor(row0 + _SNAP)
    col1, row1 = math.ceil(col1 - _SNAP), math.ceil(row1 - _SNAP)
    return Window(col0, row0, col1 - col0, row1 - row0)
