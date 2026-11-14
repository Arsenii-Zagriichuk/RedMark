"""Cut a piece of the Jezero photo map and reproject it into the site frame."""

from pathlib import Path

import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject, transform_bounds
from rasterio.windows import from_bounds

from prep.common import SOURCE_TAG, Bounds, written_atomically
from prep.jezero.site_frame import SITE_PROJ

RESOLUTION = 0.25  # metres, the photo map's own scale
# Source pixels read beyond the asked bounds, so resampling has neighbours.
_READ_PAD = 8


def crop_to_site_frame(source: str | Path, bounds: Bounds, out: Path, source_id: str) -> None:
    """Write `bounds` (site-frame metres) of `source` as a 25 cm GeoTIFF.

    `source` may be a local file or a GDAL remote path such as /vsicurl/...;
    only the rows the crop needs are read. `source_id` names the map version
    and is stored in the crop. The crop appears at `out` only once complete.
    """
    site_crs = CRS.from_proj4(SITE_PROJ)
    min_x, min_y, max_x, max_y = bounds
    width = round((max_x - min_x) / RESOLUTION)
    height = round((max_y - min_y) / RESOLUTION)
    dst_transform = from_origin(min_x, max_y, RESOLUTION, RESOLUTION)

    with rasterio.open(source) as src:
        src_bounds = transform_bounds(site_crs, src.crs, *bounds)
        window = from_bounds(*src_bounds, transform=src.transform).round_offsets().round_lengths()
        window = rasterio.windows.Window(
            window.col_off - _READ_PAD,
            window.row_off - _READ_PAD,
            window.width + 2 * _READ_PAD,
            window.height + 2 * _READ_PAD,
        ).intersection(rasterio.windows.Window(0, 0, src.width, src.height))
        data = src.read(1, window=window)
        src_transform = src.window_transform(window)
        profile = {
            "driver": "GTiff",
            "width": width,
            "height": height,
            "count": 1,
            "dtype": src.dtypes[0],
            "crs": site_crs,
            "transform": dst_transform,
            "nodata": src.nodata,
            "tiled": True,
            "compress": "deflate",
        }
        with written_atomically(out) as partial, rasterio.open(partial, "w", **profile) as dst:
            reproject(
                source=data,
                destination=rasterio.band(dst, 1),
                src_transform=src_transform,
                src_crs=src.crs,
                src_nodata=src.nodata,
                dst_transform=dst_transform,
                dst_crs=site_crs,
                dst_nodata=src.nodata,
                resampling=Resampling.bilinear,
            )
            dst.update_tags(**{SOURCE_TAG: source_id})


def crop_is_current(crop: Path, bounds: Bounds, source_id: str) -> bool:
    """`crop` is a finished 25 cm site-frame cut of `bounds` from map version `source_id`."""
    if not crop.exists():
        return False
    with rasterio.open(crop) as src:
        # The far edges snap to the 25 cm grid, so allow half a pixel.
        same_bounds = all(
            abs(a - b) < RESOLUTION / 2 for a, b in zip(src.bounds, bounds, strict=True)
        )
        return (
            same_bounds
            and src.res == (RESOLUTION, RESOLUTION)
            and src.crs == CRS.from_proj4(SITE_PROJ)
            and src.tags().get(SOURCE_TAG) == source_id
        )
