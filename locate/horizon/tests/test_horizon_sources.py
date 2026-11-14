"""Reading terrain files into map metres. Expected values are worked by hand."""

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from contracts.models.common import Bounds
from locate.horizon.sources import FAR_DEM, GALE_DEM, load_gale_terrain, read_heights

EQC = "+proj=eqc +lat_ts=0 +lat_0=0 +lon_0=0 +R=3396190 +units=m +no_defs"


def write_flat(path, height_m, *, left, top, res, size):
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=size,
        height=size,
        count=1,
        dtype="float32",
        crs=EQC,
        transform=from_origin(left, top, res, res),
        nodata=-32767,
    ) as dst:
        dst.write(np.full((size, size), height_m, np.float32), 1)


def test_replacing_a_terrain_file_under_the_same_name_refreshes_every_tier(tmp_path):
    # Gale file: 400 m square at 1 m. Far file: 10 km square at 50 m round it.
    data, cache = tmp_path / "data", tmp_path / "cache"
    walk_area = Bounds(min_x=190.0, min_y=190.0, max_x=210.0, max_y=210.0)
    near_spot, mid_spot, far_spot = (
        (200.0, 200.0, 0.0),
        (300.0, 300.0, 2_000.0),
        (3_000.0, 3_000.0, 4_000.0),
    )

    def heights_now():
        terrain = load_gale_terrain(data, walk_area, cache).terrain
        x, y, d = (np.array(v) for v in zip(near_spot, mid_spot, far_spot, strict=True))
        return terrain.height(x, y, d).tolist()

    for height in (10.0, 70.0):
        write_flat(data / GALE_DEM, height, left=0.0, top=400.0, res=1.0, size=400)
        write_flat(data / FAR_DEM, height, left=-5_000.0, top=5_400.0, res=50.0, size=200)
        assert heights_now() == pytest.approx([height] * 3)


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
