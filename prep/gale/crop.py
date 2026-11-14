"""Cut the walk area out of a Gale source that is already in the site projection.

The Gale photo map, terrain, THEMIS mosaic and CRISM cube all share the site
projection, so a crop is a window on the source's own pixel grid: no
resampling, every value and band as published. The window is snapped outward
to whole source pixels, so the crop covers the asked bounds and overshoots by
less than a pixel a side. A source found to sit off the base map can be moved
as it is cut; the move is the only change to its grid.
"""

import math
from pathlib import Path

import rasterio
from rasterio.crs import CRS
from rasterio.transform import Affine
from rasterio.windows import Window

from prep.common import SOURCE_TAG, Bounds, source_tag, written_atomically

# A source edge counts as a pixel edge if it is this close (in pixels).
_SNAP = 1e-6


def crop_on_source_grid(
    source: Path,
    bounds: Bounds,
    out: Path,
    projection: str,
    source_id: str,
    move_m: tuple[float, float] = (0.0, 0.0),
) -> Bounds:
    """Write the source pixels covering `bounds` to `out`; return the crop's bounds.

    `move_m` (east, north) moves the source before it is cut, for a source
    that sits off the base map. Raises ValueError if the source is not in
    `projection` or does not cover `bounds`. The crop appears at `out` only
    once it is complete.
    """
    east, north = move_m
    min_x, min_y, max_x, max_y = bounds
    with rasterio.open(source) as src:
        if src.crs != CRS.from_proj4(projection):
            raise ValueError(f"{source} is not in the site projection {projection}")
        window = _window_covering(src, (min_x - east, min_y - north, max_x - east, max_y - north))
        if window.intersection(Window(0, 0, src.width, src.height)) != window:
            raise ValueError(f"{bounds} reaches outside {source}")
        data = src.read(window=window)
        transform = Affine.translation(east, north) * src.window_transform(window)
        descriptions = src.descriptions
        profile = {
            "driver": "GTiff",
            "width": window.width,
            "height": window.height,
            "count": src.count,
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
    with written_atomically(out) as partial, rasterio.open(partial, "w", **profile) as dst:
        dst.write(data)
        dst.descriptions = descriptions
        dst.update_tags(**{SOURCE_TAG: source_id})
    with rasterio.open(out) as written:
        return tuple(written.bounds)


def crop_is_current(crop: Path, source_id: str) -> bool:
    """`crop` exists and was cut from the source version `source_id`."""
    return source_tag(crop) == source_id


def _window_covering(src: rasterio.DatasetReader, bounds: Bounds) -> Window:
    min_x, min_y, max_x, max_y = bounds
    inverse = ~src.transform
    col0, row0 = inverse @ (min_x, max_y)
    col1, row1 = inverse @ (max_x, min_y)
    col0, row0 = math.floor(col0 + _SNAP), math.floor(row0 + _SNAP)
    col1, row1 = math.ceil(col1 - _SNAP), math.ceil(row1 - _SNAP)
    return Window(col0, row0, col1 - col0, row1 - row0)
