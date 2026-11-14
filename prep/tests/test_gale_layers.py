"""Seams: layer 1, the base map tiles and the slope layer (P2-02).

Tile geometry: a pixel with known map coordinates lands in the tile and pixel
the layer contract says it should. Slope: a plane of known tilt comes back as
that tilt, and a hole in the terrain stays unknown. Layer writer: every
layer.json validates, and the route's own reader reads the slope raster. Legend:
the colour on a tile is the legend colour for that slope.

Expected tiles and pixels are worked by hand from layer.json's rule: at
max_zoom one pixel is resolution_m, each lower zoom halves the resolution, and
tile (x, y) counts from the north-west corner of the bounds.
"""

import json
import math
from pathlib import Path

import numpy as np
import pytest
import rasterio
from PIL import Image
from rasterio.crs import CRS
from rasterio.transform import from_origin

from contracts.models.layer import LayerMeta
from contracts.models.site import SiteConfig
from prep.gale.layers import build_base_layer, build_slope_layer, slope_raster
from route.layers import load_grid

SITE_PROJ = "+proj=eqc +lat_ts=0 +lon_0=0 +R=3396190 +units=m +no_defs"
SOURCE = {"name": "test source", "url": "https://example.org/source"}


def _geotiff(path: Path, data: np.ndarray, west: float, north: float, res: float, nodata) -> Path:
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=data.shape[1],
        height=data.shape[0],
        count=1,
        dtype=data.dtype,
        crs=CRS.from_proj4(SITE_PROJ),
        transform=from_origin(west, north, res, res),
        nodata=nodata,
    ) as dst:
        dst.write(data, 1)
    return path


def _tile(folder: Path, z: int, x: int, y: int, ext: str) -> np.ndarray:
    return np.asarray(Image.open(folder / "tiles" / str(z) / str(x) / f"{y}.{ext}"))


# ---- tile geometry ------------------------------------------------------------------


@pytest.fixture
def photo(tmp_path: Path) -> Path:
    """A 25 cm photo map 1200 x 1200 px from (1000, 2000), grey 100, with a bright
    4 x 4 px block whose top-left pixel centre is at x 1115.125, y 1799.875."""
    image = np.full((1200, 1200), 100, dtype=np.uint8)
    # Source col (1115.125 - 1000) / 0.25 = 460.5 -> 460; row (2000 - 1799.875) / 0.25 -> 800.
    image[800:804, 460:464] = 255
    return _geotiff(tmp_path / "photo.tif", image, 1000.0, 2000.0, 0.25, 0)


def test_a_known_point_lands_in_its_tile_and_pixel(photo: Path, tmp_path: Path):
    out = tmp_path / "base"
    # 250 m x 250 m at 25 cm is 1000 x 1000 px: 4 x 4 tiles of 250 px at max zoom 2.
    build_base_layer(photo, (1050.0, 1700.0, 1300.0, 1950.0), out, SOURCE)

    meta = json.loads((out / "layer.json").read_text())
    assert meta["tiles"] == {
        "path": "tiles/{z}/{x}/{y}.jpg",
        "tile_size": 250,
        "min_zoom": 0,
        "max_zoom": 2,
    }
    # In the layer the block's top-left pixel is col (1115.125 - 1050) / 0.25 = 260.5 -> 260,
    # row (1950 - 1799.875) / 0.25 -> 600: tile x 1, y 2 at zoom 2, pixel row 100, col 10.
    detail = _tile(out, 2, 1, 2, "jpg")
    assert detail.shape == (250, 250)
    assert detail[101, 11] > 230
    assert abs(int(detail[100, 30]) - 100) < 10
    # At zoom 0 one pixel is 1 m: the block is pixel row 150, col 65 of the only tile.
    overview = _tile(out, 0, 0, 0, "jpg")
    assert overview[150, 65] > 230
    assert abs(int(overview[150, 70]) - 100) < 10


def test_tiles_past_the_edge_of_the_bounds_are_transparent(tmp_path: Path):
    terrain = _geotiff(
        tmp_path / "terrain.tif", np.zeros((400, 400), np.float32), 999.5, 2000.5, 1.0, -32767.0
    )
    slope = slope_raster(terrain, tmp_path / "slope.tif")
    out = tmp_path / "slope"
    # 300 m wide at 1 m: two 250 px tiles at max zoom 1; the second holds 50 px of ground.
    build_slope_layer(slope, (1050.0, 1750.0, 1350.0, 1950.0), out, SOURCE)

    edge = _tile(out, 1, 1, 0, "png")
    assert edge.shape == (250, 250, 4)
    assert edge[10, 49, 3] == 255
    assert edge[10, 50, 3] == 0
    assert not (out / "tiles" / "1" / "0" / "1.png").exists()  # 200 m tall: one tile row


# ---- slope --------------------------------------------------------------------------

TILT_DEG = 17.0
FACING_DEG = 60.0  # the plane rises towards 060°, so slope needs both the east and north parts


@pytest.fixture
def terrain(tmp_path: Path) -> Path:
    """1 m heights 400 x 400 on a grid half a metre off the whole metre, like the real
    Gale terrain: a plane tilted 17° rising towards 060°, with one hole at row 200, col 200."""
    rise = math.tan(math.radians(TILT_DEG))
    east = rise * math.sin(math.radians(FACING_DEG))
    north = rise * math.cos(math.radians(FACING_DEG))
    cols, rows = np.meshgrid(np.arange(400), np.arange(400))
    heights = (east * cols - north * rows - 4000.0).astype(np.float32)
    heights[200, 200] = -32767.0
    return _geotiff(tmp_path / "terrain.tif", heights, 999.5, 2000.5, 1.0, -32767.0)


def test_a_plane_of_known_tilt_reads_as_that_slope(terrain: Path, tmp_path: Path):
    out = slope_raster(terrain, tmp_path / "slope.tif")

    with rasterio.open(out) as src:
        slope = src.read(1)
        assert src.crs == CRS.from_proj4(SITE_PROJ)
        assert src.transform == from_origin(999.5, 2000.5, 1.0, 1.0)
    assert slope[50, 50] == pytest.approx(TILT_DEG, abs=1e-3)
    assert slope[350, 120] == pytest.approx(TILT_DEG, abs=1e-3)


def test_a_hole_in_the_terrain_leaves_its_slope_unknown(terrain: Path, tmp_path: Path):
    out = slope_raster(terrain, tmp_path / "slope.tif")

    with rasterio.open(out) as src:
        slope = src.read(1, masked=True)
    unknown = np.ma.getmaskarray(slope) | np.isnan(slope.filled(np.nan))
    for row, col in [(200, 200), (199, 200), (201, 200), (200, 199), (200, 201)]:
        assert unknown[row, col], (row, col)
    assert not unknown[198, 198]


# ---- layer writer -------------------------------------------------------------------


def test_every_layer_file_validates_with_resolution_legend_and_source(
    photo: Path, terrain: Path, tmp_path: Path
):
    build_base_layer(photo, (1050.0, 1700.0, 1300.0, 1950.0), tmp_path / "base", SOURCE)
    slope = slope_raster(terrain, tmp_path / "slope.tif")
    build_slope_layer(slope, (1050.0, 1750.0, 1350.0, 1950.0), tmp_path / "slope", SOURCE)

    base = LayerMeta.model_validate_json((tmp_path / "base" / "layer.json").read_text())
    layer = LayerMeta.model_validate_json((tmp_path / "slope" / "layer.json").read_text())
    assert (base.name, base.group, base.resolution_m, base.units) == ("base", 1, 0.25, "")
    assert (layer.name, layer.group, layer.resolution_m, layer.units) == ("slope", 1, 1.0, "°")
    assert layer.bounds.model_dump() == {
        "min_x": 1050.0,
        "min_y": 1750.0,
        "max_x": 1350.0,
        "max_y": 1950.0,
    }
    for meta in (base, layer):
        assert [s.model_dump(mode="json") for s in meta.source] == [SOURCE]
        assert meta.legend


def test_the_route_reader_plans_on_the_slope_raster(terrain: Path, tmp_path: Path):
    slope_raster(terrain, tmp_path / "gale" / "rasters" / "slope.tif")
    site = SiteConfig.model_validate(
        {
            "site": "gale",
            "name": "test",
            "projection": SITE_PROJ,
            "bounds": {"min_x": 1050, "min_y": 1750, "max_x": 1150, "max_y": 1850},
            "habitat": {"x": 1100, "y": 1800},
            "base_camp": None,
            "science_targets": [],
            "checkpoints": [],
            "files": {"slope": "gale/rasters/slope.tif"},
            "replayed_sol": None,
        }
    )

    grid = load_grid(site, tmp_path, cell_m=4.0)

    assert grid.slope_deg.shape == (25, 25)
    # Each cell keeps its steepest pixel. Float32 heights near -4000 m resolve 0.24 mm,
    # about 0.01° across 2 m, so the steepest of 16 pixels sits a little above 17°.
    assert np.allclose(grid.slope_deg, TILT_DEG, atol=0.01)


# ---- legend -------------------------------------------------------------------------


def test_a_tile_shows_the_legend_colour_for_its_slope(terrain: Path, tmp_path: Path):
    slope = slope_raster(terrain, tmp_path / "slope.tif")
    out = tmp_path / "slope"
    build_slope_layer(slope, (1050.0, 1750.0, 1350.0, 1950.0), out, SOURCE)

    legend = json.loads((out / "layer.json").read_text())["legend"]
    assert [entry["label"] for entry in legend] == [
        "0–5°",
        "5–10°",
        "10–15°",
        "15–20°",
        "20–30°",
        "30° and steeper",
    ]
    colour = next(entry["color"] for entry in legend if entry["label"] == "15–20°")
    tile = _tile(out, 1, 0, 0, "png")
    assert "#{:02x}{:02x}{:02x}".format(*tile[20, 20, :3]) == colour
    assert tile[20, 20, 3] == 255
    # The hole is at terrain row 200, col 200: map x 1200, y 1800, so layer col 150, row 150.
    assert tile[150, 150, 3] == 0
