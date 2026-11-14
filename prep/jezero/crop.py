"""Cut a piece of the Jezero photo map and reproject it into the site frame."""

from pathlib import Path

import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject, transform_bounds
from rasterio.windows import from_bounds

from prep.jezero.frame import SITE_PROJ

Bounds = tuple[float, float, float, float]  # min_x, min_y, max_x, max_y
RESOLUTION = 0.25  # metres, the photo map's own scale
# Source pixels read beyond the asked bounds, so resampling has neighbours.
_READ_PAD = 8


def crop_to_site_frame(source: str | Path, bounds: Bounds, out: Path) -> None:
    """Write `bounds` (site-frame metres) of `source` as a 25 cm GeoTIFF.

    `source` may be a local file or a GDAL remote path such as /vsicurl/...;
    only the rows the crop needs are read.
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
        out.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(out, "w", **profile) as dst:
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
