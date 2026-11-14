"""Seam: crop and reproject the Jezero photo map.

A point with known coordinates lands where it should in the crop, and map
metres in the crop are ground metres at Jezero's latitude.
"""

import json
import math
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from prep.jezero.crop import crop_to_site_frame
from prep.jezero.site_frame import SITE_LAT_TS, SOURCE_PROJ, to_site_frame

FIXTURES = Path(__file__).parent / "fixtures"
MARS_RADIUS = 3396190.0  # metres, the sphere both projections use


def test_site_frame_reproduces_nasa_published_easting_and_northing():
    # NASA's Ingenuity waypoint file gives each waypoint's longitude, latitude
    # and its Easting and Northing in the Mars 2020 map frame. Our site frame
    # must give the same numbers, so the answer key lines up with NASA's.
    waypoints = json.loads((FIXTURES / "m20_heli_waypoints.json").read_text())["features"]
    assert waypoints
    for feature in waypoints:
        p = feature["properties"]
        x, y = to_site_frame(p["Lon"], p["Lat"])
        assert x == pytest.approx(p["Easting"], abs=0.01)
        assert y == pytest.approx(p["Northing"], abs=0.01)


def _source_x(lon: float) -> float:
    """Easting in the published map's frame (true scale at the equator)."""
    return MARS_RADIUS * math.radians(lon)


def _site_x(lon: float) -> float:
    """Easting with true scale at Jezero: the parallel's real length."""
    return MARS_RADIUS * math.cos(math.radians(SITE_LAT_TS)) * math.radians(lon)


def _north(lat: float) -> float:
    return MARS_RADIUS * math.radians(lat)


@pytest.fixture
def source_map(tmp_path: Path) -> Path:
    """A small fake photo map in the published frame with two bright marks.

    Both marks sit on the same parallel, 0.004° of longitude apart.
    """
    lon0, lat0 = 77.440, 18.452
    width, height = 2400, 1000  # 600 m by 250 m at 25 cm
    image = np.zeros((height, width), dtype=np.uint8)
    transform = from_origin(_source_x(lon0), _north(lat0), 0.25, 0.25)
    marks = [(77.4425, 18.4510), (77.4465, 18.4510)]
    for lon, lat in marks:
        col = int((_source_x(lon) - _source_x(lon0)) / 0.25)
        row = int((_north(lat0) - _north(lat)) / 0.25)
        assert 2 <= col < width - 3 and 2 <= row < height - 3
        image[row - 2 : row + 3, col - 2 : col + 3] = 255
    path = tmp_path / "source.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=width,
        height=height,
        count=1,
        dtype="uint8",
        crs=SOURCE_PROJ,
        transform=transform,
        nodata=0,
    ) as dst:
        dst.write(image, 1)
    return path


def _mark_centres(path: Path) -> list[tuple[float, float]]:
    """Site-frame centre of each bright blob, west to east."""
    with rasterio.open(path) as src:
        image = src.read(1)
        transform = src.transform
    rows, cols = np.nonzero(image > 128)
    west = cols < cols.mean()
    centres = []
    for side in (west, ~west):
        x, y = transform @ (cols[side].mean() + 0.5, rows[side].mean() + 0.5)
        centres.append((x, y))
    return sorted(centres)


def test_a_known_point_lands_at_its_site_frame_position(source_map: Path, tmp_path: Path):
    bounds = (_site_x(77.441), _north(18.4500), _site_x(77.448), _north(18.4518))
    out = tmp_path / "crop.tif"

    crop_to_site_frame(source_map, bounds, out)

    west, _ = _mark_centres(out)
    assert west[0] == pytest.approx(_site_x(77.4425), abs=0.5)
    assert west[1] == pytest.approx(_north(18.4510), abs=0.5)


def test_crop_covers_the_asked_bounds_at_25_cm_in_the_site_frame(source_map: Path, tmp_path: Path):
    bounds = (_site_x(77.441), _north(18.4500), _site_x(77.448), _north(18.4518))
    out = tmp_path / "crop.tif"

    crop_to_site_frame(source_map, bounds, out)

    with rasterio.open(out) as src:
        assert src.res == (0.25, 0.25)
        assert src.bounds.left == pytest.approx(bounds[0], abs=0.25)
        assert src.bounds.bottom == pytest.approx(bounds[1], abs=0.25)
        assert src.bounds.right == pytest.approx(bounds[2], abs=0.25)
        assert src.bounds.top == pytest.approx(bounds[3], abs=0.25)
        assert (
            src.crs.to_proj4()
            == rasterio.crs.CRS.from_proj4(
                "+proj=eqc +lat_ts=18.4663 +lon_0=0 +R=3396190 +units=m +no_defs"
            ).to_proj4()
        )


def test_map_metres_in_the_crop_are_ground_metres(source_map: Path, tmp_path: Path):
    # Ground distance along the 18.451° parallel between two points 0.004° of
    # longitude apart: R · cos(lat) · Δlon. About 225 m; the published map
    # calls it about 237 m.
    ground = MARS_RADIUS * math.cos(math.radians(18.451)) * math.radians(0.004)
    published = _source_x(77.4465) - _source_x(77.4425)
    assert published / ground == pytest.approx(1.054, abs=0.001)
    out = tmp_path / "crop.tif"
    bounds = (_site_x(77.441), _north(18.4500), _site_x(77.448), _north(18.4518))

    crop_to_site_frame(source_map, bounds, out)

    (west_x, _), (east_x, _) = _mark_centres(out)
    assert east_x - west_x == pytest.approx(ground, rel=0.002)
