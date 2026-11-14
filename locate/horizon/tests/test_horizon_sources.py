"""Reading terrain files into map metres. Expected values are worked by hand."""

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from contracts.models.common import Bounds
from locate.horizon.sources import read_heights


def test_a_terrain_file_in_degrees_comes_back_in_map_metres(tmp_path):
    # 4 x 4 cells of 0.5°, north-west corner at 137°E, 4°S, on the Mars 2000 sphere.
    # One degree is 2π × 3,396,190 m / 360 = 59,274.70 m, so the corner is at
    # (8,120,633.6, -237,098.8) map metres and a cell is 29,637.35 m.
    path = tmp_path / "lonlat.tif"
    heights = np.arange(16, dtype=np.int16).reshape(4, 4)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=4,
        height=4,
        count=1,
        dtype="int16",
        crs="+proj=longlat +R=3396190 +no_defs",
        transform=from_origin(137.0, -4.0, 0.5, 0.5),
        nodata=-32768,
    ) as dst:
        dst.write(heights, 1)
    everything = Bounds(min_x=8.0e6, min_y=-400_000.0, max_x=8.3e6, max_y=-200_000.0)

    raster = read_heights(path, everything)

    assert raster.left == pytest.approx(8_120_633.6, abs=0.1)
    assert raster.top == pytest.approx(-237_098.8, abs=0.1)
    assert raster.res == pytest.approx(29_637.35, abs=0.01)
    assert raster.heights.tolist() == heights.tolist()
