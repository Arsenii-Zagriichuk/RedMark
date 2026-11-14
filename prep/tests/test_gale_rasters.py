"""Seam: a window read from a crop carries the extent of the pixels it holds."""

import numpy as np
import rasterio
from rasterio.transform import from_origin

from prep.gale.rasters import read_window


def _crop(path):
    # 10 x 10 pixels of 2 m from (100, 220): x 100..120, y 200..220.
    data = np.arange(100, dtype=np.float32).reshape(10, 10) + 1
    profile = {"driver": "GTiff", "width": 10, "height": 10, "count": 1, "dtype": "float32"}
    with rasterio.open(path, "w", **profile, transform=from_origin(100, 220, 2, 2)) as dst:
        dst.write(data, 1)
    return data


def test_a_window_inside_the_crop_is_read_as_asked(tmp_path):
    data = _crop(tmp_path / "crop.tif")

    pixels, extent = read_window(tmp_path / "crop.tif", (104, 206, 110, 214), float_data=True)

    assert extent == (104, 110, 206, 214)
    np.testing.assert_array_equal(pixels, data[3:7, 2:5])


def test_a_window_past_the_crop_edge_reports_only_the_pixels_read(tmp_path):
    data = _crop(tmp_path / "crop.tif")

    # Asked from y 210 to 240; the crop stops at 220, so 5 rows are read.
    pixels, extent = read_window(tmp_path / "crop.tif", (104, 210, 110, 240), float_data=True)

    assert extent == (104, 110, 210, 220)
    np.testing.assert_array_equal(pixels, data[0:5, 2:5])
