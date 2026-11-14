"""Seams: layers 2 and 3 at Gale (P2-03).

Sand and ridge rasters: thermal inertia below the sand cutoff marks loose sand and a
hole stays unknown; the ridge finder finds a grid of bright 1 m lines on flat ground,
not the hollows between them nor a lone bright speck; the route's own reader reads
both files as masks. Layer writer: each layer.json validates with its group,
resolution and source. Science targets: a target on a drill site, on Curiosity's
track or past the walk radius is refused; a ridge target must sit on a ridge pixel,
not beside one, and a hollow target off any; a target with any other kind is refused;
a target walled off from base camp by ground over the slope limit is refused, and the
build checks reachability under the app's own default limits. The sand layer's tiles
show firm ground in its own legend colour and leave only unknown ground transparent.

Expected values are worked by hand from the fixtures, not from the code.
"""

import re
from pathlib import Path

import numpy as np
import pytest
import rasterio
from PIL import Image
from rasterio.crs import CRS
from rasterio.transform import from_origin

from contracts.models.common import Point
from contracts.models.layer import LayerMeta
from contracts.models.route_request import Limits
from contracts.models.site import SiteConfig
from contracts.paths import REPO_ROOT
from prep.gale.build_layers_2_3 import APP_LIMITS
from prep.gale.layers import (
    build_chemistry_layer,
    build_minerals_layer,
    build_ridges_layer,
    build_sand_layer,
)
from prep.gale.science import check_reachable, check_targets, drill_sites
from prep.gale.walkability import SAND_MAX_TI, find_ridges, ridge_raster, sand_raster
from route.layers import load_grid
from route.planner import CostGrid

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


# ---- sand ---------------------------------------------------------------------------


def test_thermal_inertia_below_the_cutoff_is_loose_sand_and_a_hole_stays_unknown(tmp_path):
    assert SAND_MAX_TI == 350
    nodata = -3.4028226550889045e38
    ti = np.array([[300.0, 349.9, 350.0], [420.0, nodata, 200.0]], dtype=np.float32)
    source = _geotiff(tmp_path / "ti.tif", ti, 1000.0, 2000.0, 100.0, nodata)

    out = sand_raster(source, tmp_path / "sand.tif")

    with rasterio.open(out) as src:
        assert src.nodata == 255
        assert src.res == (100.0, 100.0)
        assert src.transform.c == 1000.0 and src.transform.f == 2000.0
        assert src.read(1).tolist() == [[1, 1, 0], [0, 255, 1]]


def test_the_sand_tiles_colour_sand_and_firm_ground_and_leave_unknown_transparent(tmp_path):
    # 2 x 2 pixels at 100 m covering the walk area exactly: sand, firm, unknown, firm.
    nodata = -1.0
    ti = np.array([[300.0, 400.0], [nodata, 380.0]], dtype=np.float32)
    sand = sand_raster(
        _geotiff(tmp_path / "ti.tif", ti, 1000.0, 2200.0, 100.0, nodata), tmp_path / "sand.tif"
    )

    build_sand_layer(sand, (1000.0, 2000.0, 1200.0, 2200.0), tmp_path / "sand", SOURCE)

    tile = np.asarray(Image.open(tmp_path / "sand" / "tiles" / "0" / "0" / "0.png").convert("RGBA"))
    colour = {
        (r, c): "#{:02x}{:02x}{:02x}".format(*tile[r, c, :3]) if tile[r, c, 3] else None
        for r in range(2)
        for c in range(2)
    }
    # The legend's own swatches, written out so two equal colours can't pass.
    assert colour == {
        (0, 0): "#e0a43a",
        (0, 1): "#7a8c99",
        (1, 0): None,
        (1, 1): "#7a8c99",
    }


# ---- ridges -------------------------------------------------------------------------

RIDGE_RES = 0.5
# Ridge lines every 15 m, 1 m wide, both ways: 14 m square hollows between them.
SPACING_PX, WIDTH_PX = 30, 2


def _boxwork(size_px: int = 240, speck: tuple[int, int] | None = None) -> np.ndarray:
    """Grey-100 ground at 50 cm with faint noise, bright (160) 1 m ridge lines every
    15 m, and optionally a lone bright 1 m speck at (row, col)."""
    rng = np.random.default_rng(7)
    image = 100 + rng.normal(0, 3, (size_px, size_px))
    for start in range(SPACING_PX // 2, size_px, SPACING_PX):
        image[start : start + WIDTH_PX, :] = 160
        image[:, start : start + WIDTH_PX] = 160
    if speck:
        image[speck[0] : speck[0] + 2, speck[1] : speck[1] + 2] = 160
    return np.clip(image, 1, 255).astype(np.uint8)


def _distance_to_line_px(size_px: int) -> np.ndarray:
    """Each pixel's distance from the nearest ridge line, in pixels (0 on a line)."""
    index = np.arange(size_px)
    offset = (index - SPACING_PX // 2) % SPACING_PX
    away = np.where(offset < WIDTH_PX, 0, np.minimum(offset - WIDTH_PX + 1, SPACING_PX - offset))
    return np.minimum(away[:, None], away[None, :])


def test_the_ridge_finder_finds_bright_lines_but_not_hollows_or_a_lone_speck():
    # Lines cover px 75-76 and 105-106, so a speck at px 89-90 sits mid-hollow.
    image = _boxwork(speck=(89, 89))
    distance = _distance_to_line_px(image.shape[0])
    inner = slice(20, -20)  # away from the image edge

    ridges = find_ridges(image, RIDGE_RES)

    on_line = ridges[inner, inner][distance[inner, inner] == 0]
    in_hollow = ridges[inner, inner][distance[inner, inner] >= 4]  # 2 m or more off a line
    assert on_line.mean() > 0.9
    assert in_hollow.mean() < 0.02
    assert not ridges[86:94, 86:94].any()


def test_the_route_reader_reads_sand_and_ridges_as_masks_with_ridges_only_in_zones(tmp_path):
    # A 120 m square from (1000, 2120) to (1120, 2000): the boxwork photo at 25 cm.
    photo = np.kron(_boxwork(240), np.ones((2, 2), dtype=np.uint8))
    photo_path = _geotiff(tmp_path / "photo.tif", photo, 1000.0, 2120.0, 0.25, 0)
    bounds = (1000.0, 2000.0, 1120.0, 2120.0)
    west_half = [(1000.0, 2000.0), (1060.0, 2000.0), (1060.0, 2120.0), (1000.0, 2120.0)]
    # Thermal inertia at 60 m: only the north-west quarter is sand.
    ti = np.array([[300.0, 400.0], [400.0, 400.0]], dtype=np.float32)
    ti_path = _geotiff(tmp_path / "ti.tif", ti, 1000.0, 2120.0, 60.0, -1.0)
    rasters = tmp_path / "gale" / "rasters"
    sand_raster(ti_path, rasters / "sand.tif")

    ridge_raster(photo_path, bounds, [west_half], rasters / "ridges.tif")

    with rasterio.open(rasters / "ridges.tif") as src:
        assert src.res == (RIDGE_RES, RIDGE_RES)
        assert (src.width, src.height) == (240, 240)
        assert src.transform.c == 1000.0 and src.transform.f == 2120.0
    site = SiteConfig.model_validate(
        {
            "site": "gale",
            "name": "test",
            "projection": SITE_PROJ,
            "bounds": {"min_x": 1000, "min_y": 2000, "max_x": 1120, "max_y": 2120},
            "habitat": {"x": 1060, "y": 2060},
            "base_camp": None,
            "science_targets": [],
            "checkpoints": [],
            "files": {"sand": "gale/rasters/sand.tif", "ridges": "gale/rasters/ridges.tif"},
            "replayed_sol": None,
        }
    )
    grid = load_grid(site, tmp_path, cell_m=4.0)

    # 30 x 30 planning cells; the zone is columns 0-14, sand rows and columns 0-14.
    assert grid.sand.shape == (30, 30)
    assert grid.sand[:15, :15].all() and not grid.sand[15:, :].any() and not grid.sand[:, 15:].any()
    # A line every 15 m crosses each 4 m row of cells at least every fourth cell.
    assert grid.ridge[5:-5, :15].mean() > 0.4
    assert not grid.ridge[:, 15:].any()


# ---- layer writer -------------------------------------------------------------------


def _crism(path: Path, west: float, north: float) -> Path:
    """A 3 x 3 CRISM summary stack at 18 m with the four bands the highlights use.
    Only the centre pixel stands out, in SINDEX2 (polyhydrated sulfate)."""
    names = ["BD1900R2", "D2300", "BD2100_2", "SINDEX2"]
    data = np.full((len(names), 3, 3), 0.001, dtype=np.float32)
    data[3, 1, 1] = 0.05
    with rasterio.open(
        path, "w", driver="GTiff", width=3, height=3, count=len(names), dtype="float32",
        crs=CRS.from_proj4(SITE_PROJ), transform=from_origin(west, north, 18.0, 18.0),
        nodata=65535.0,
    ) as dst:  # fmt: skip
        dst.write(data)
        dst.descriptions = tuple(names)
    return path


def _opaque_colours(folder: Path) -> set[str]:
    colours = set()
    for png in (folder / "tiles").rglob("*.png"):
        rgba = np.asarray(Image.open(png).convert("RGBA")).reshape(-1, 4)
        colours |= {"#{:02x}{:02x}{:02x}".format(*p[:3]) for p in rgba[rgba[:, 3] > 0]}
    return colours


def test_every_layer_2_and_3_file_validates_with_group_resolution_legend_and_source(tmp_path):
    walk = (1000.0, 2000.0, 1120.0, 2120.0)
    # Thermal inertia from (950, 2150) at 100 m: the walk area snaps out to its pixels,
    # x 950 to 1150 and y 1950 to 2150, 2 x 2 pixels.
    ti = np.array([[300.0, 400.0, 400.0], [400.0, 400.0, 400.0], [400.0, 400.0, 400.0]])
    ti_path = _geotiff(tmp_path / "ti.tif", ti.astype(np.float32), 950.0, 2150.0, 100.0, -1.0)
    sand = sand_raster(ti_path, tmp_path / "sand.tif")
    photo = np.kron(_boxwork(240), np.ones((2, 2), dtype=np.uint8))
    photo_path = _geotiff(tmp_path / "photo.tif", photo, 1000.0, 2120.0, 0.25, 0)
    zone = [(1000.0, 2000.0), (1060.0, 2000.0), (1060.0, 2120.0), (1000.0, 2120.0)]
    ridges = ridge_raster(photo_path, walk, [zone], tmp_path / "ridges.tif")
    # CRISM from (1003, 2129): snapped out, x 1003 to 1057 and y 2075 to 2129.
    crism = _crism(tmp_path / "crism.tif", 1003.0, 2129.0)
    small_walk = (1010.0, 2080.0, 1050.0, 2120.0)
    points = [
        {"x": 1020.0, "y": 2100.0, "so3": 8.0, "drill": False},
        {"x": 1080.0, "y": 2040.0, "so3": 25.0, "drill": True},
    ]

    build_sand_layer(sand, walk, tmp_path / "sand", SOURCE)
    build_ridges_layer(ridges, walk, tmp_path / "ridges", SOURCE)
    build_minerals_layer(crism, small_walk, tmp_path / "minerals", SOURCE)
    build_chemistry_layer(points, walk, tmp_path / "chemistry", SOURCE)

    expected = {
        "sand": (2, 100.0, {"min_x": 950.0, "min_y": 1950.0, "max_x": 1150.0, "max_y": 2150.0}),
        "ridges": (2, 0.5, {"min_x": 1000.0, "min_y": 2000.0, "max_x": 1120.0, "max_y": 2120.0}),
        "minerals": (3, 18.0, {"min_x": 1003.0, "min_y": 2075.0, "max_x": 1057.0, "max_y": 2129.0}),
        "chemistry": (3, 1.0, {"min_x": 1000.0, "min_y": 2000.0, "max_x": 1120.0, "max_y": 2120.0}),
    }
    for name, (group, res, bounds) in expected.items():
        folder = tmp_path / name
        meta = LayerMeta.model_validate_json((folder / "layer.json").read_text())
        assert (meta.name, meta.group, meta.resolution_m) == (name, group, res)
        assert meta.bounds.model_dump() == bounds
        assert [s.model_dump(mode="json") for s in meta.source] == [SOURCE]
        legend = {entry.color.lower() for entry in meta.legend}
        shown = _opaque_colours(folder)
        assert shown, f"{name} tiles are all transparent"
        assert shown <= legend, f"{name} tiles show colours outside the legend"


# ---- science targets ----------------------------------------------------------------

# In the 120 m boxwork square below, ridge lines run along x 1007.5-1008.5, 1022.5-1023.5,
# 1037.5-1038.5, ... and y 2111.5-2112.5, 2096.5-2097.5, ...; the hollow between
# x 1023.5 and 1037.5, y 2097.5 and 2111.5 has its centre at (1030.5, 2104.5).
RIDGE_TARGET = {"id": "ridge-1", "name": "A ridge", "kind": "ridge", "x": 1023.0, "y": 2030.0}
HOLLOW_TARGET = {"id": "hollow-1", "name": "A hollow", "kind": "hollow", "x": 1030.5, "y": 2104.5}


@pytest.fixture
def ridges(tmp_path) -> Path:
    photo = np.kron(_boxwork(240), np.ones((2, 2), dtype=np.uint8))
    photo_path = _geotiff(tmp_path / "photo.tif", photo, 1000.0, 2120.0, 0.25, 0)
    return ridge_raster(
        photo_path, (1000.0, 2000.0, 1120.0, 2120.0), [WEST_HALF], tmp_path / "r.tif"
    )


WEST_HALF = [(1000.0, 2000.0), (1060.0, 2000.0), (1060.0, 2120.0), (1000.0, 2120.0)]
# Curiosity drove up the east edge, x 1110, and drilled once there at y 2010.
TRACK = [(1110.0, 2000.0), (1110.0, 2120.0)]
CHEMISTRY_ROWS = [
    {"sol": "4700", "target": "Some_Rock_DRT", "x": "1110.0", "y": "2100.0"},
    {"sol": "4706", "target": "Deep_Hole_tailings", "x": "1110.0", "y": "2010.0"},
    {"sol": "4710", "target": "Deep_Hole_tailings2", "x": "1110.0", "y": "2010.0"},
]


def _check(targets, ridges, **changes):
    args = {
        "drill_sites": drill_sites(CHEMISTRY_ROWS),
        "track": TRACK,
        "habitat": (1040.0, 2060.0),
        "walk_radius_m": 100.0,
        "zones": [WEST_HALF],
        "ridges": ridges,
    } | changes
    check_targets(targets, **args)


def test_drill_sites_are_the_tailings_rows_one_per_rover_position():
    assert drill_sites(CHEMISTRY_ROWS) == [
        {"name": "Deep_Hole", "sol": 4706, "x": 1110.0, "y": 2010.0}
    ]


def test_a_ridge_centre_and_a_hollow_clear_of_curiosity_pass(ridges):
    _check([RIDGE_TARGET, HOLLOW_TARGET], ridges)


@pytest.mark.parametrize(
    ("target", "changes", "reason"),
    [
        (HOLLOW_TARGET | {"x": 1038.0}, {}, "sits on a ridge"),
        (RIDGE_TARGET | {"x": 1030.5, "y": 2104.5}, {}, "not on a ridge pixel"),
        # Ridge pixels run x 1022 to 1024 here: 1024.4 is beside the crest, 0.65 m
        # from the nearest ridge pixel's centre.
        (RIDGE_TARGET | {"x": 1024.4}, {}, "not on a ridge pixel"),
        (
            HOLLOW_TARGET,
            {"drill_sites": [{"name": "Near", "sol": 1, "x": 1030.5, "y": 2140.0}]},
            "from drill site Near",
        ),
        (HOLLOW_TARGET, {"track": [(1030.5, 2110.0), (1030.5, 2120.0)]}, "from Curiosity's track"),
        (
            HOLLOW_TARGET,
            {"habitat": (1023.0, 2030.0), "walk_radius_m": 40.0},
            "past the walk radius",
        ),
        (HOLLOW_TARGET | {"x": 1075.5}, {}, "outside every boxwork zone"),
        (HOLLOW_TARGET | {"kind": "crater"}, {}, "kind must be ridge or hollow"),
    ],
)
def test_a_target_that_breaks_a_rule_is_refused(ridges, target, changes, reason):
    other = HOLLOW_TARGET if target["kind"] == "ridge" else RIDGE_TARGET
    with pytest.raises(ValueError, match=f"{target['id']}: .*{reason}") as refused:
        _check([other, target], ridges, **changes)
    assert other["id"] not in str(refused.value)


# A 20 x 20 grid of flat 4 m cells from (0, 80) with a ring of 30 degree cells round
# the 3 x 3 cells of rows and columns 12 to 14; base camp is at cell (2, 2).
LIMITS = Limits(
    max_slope_deg=20, max_distance_from_habitat_m=2000, planning_speed_kmh=2, max_walk_h=6
)


def _walled_grid() -> CostGrid:
    slope = np.zeros((20, 20))
    slope[11:16, 11:16] = 30.0
    slope[12:15, 12:15] = 0.0
    no = np.zeros((20, 20), dtype=bool)
    return CostGrid(
        site="gale", min_x=0.0, max_y=80.0, cell_m=4.0, slope_deg=slope, sand=no, ridge=no
    )


def test_a_target_walled_off_from_base_camp_is_refused_and_an_open_one_passes():
    base_camp = Point(x=10.0, y=70.0)
    open_ground = {"id": "open", "x": 42.0, "y": 70.0}
    walled = {"id": "walled", "x": 54.0, "y": 26.0}  # cell (13, 13), inside the ring

    check_reachable(
        [open_ground], _walled_grid(), start=base_camp, habitat=base_camp, limits=LIMITS
    )
    with pytest.raises(ValueError, match="walled: no safe route from base camp") as refused:
        check_reachable(
            [open_ground, walled], _walled_grid(), start=base_camp, habitat=base_camp, limits=LIMITS
        )
    refused_ids = [line.split(":")[0] for line in str(refused.value).splitlines()[1:]]
    assert refused_ids == ["walled"]


def test_the_builds_route_limits_are_the_apps_defaults():
    # The app's own defaults, read from its source, so a change there fails here.
    app = (REPO_ROOT / "app" / "src" / "plan" / "routes.ts").read_text()

    def const(name: str) -> float:
        return float(re.search(rf"const {name} = ([0-9.]+);", app).group(1))

    # The slope limit the plan screen starts with, not the first option in the list.
    screen = (REPO_ROOT / "app" / "src" / "plan" / "PlanScreen.tsx").read_text()
    default_slope = float(re.search(r"useState<SlopeLimit>\(([0-9.]+)\)", screen).group(1))
    assert APP_LIMITS.model_dump() == {
        "max_slope_deg": default_slope,
        "max_distance_from_habitat_m": const("MAX_DISTANCE_FROM_HABITAT_M"),
        "planning_speed_kmh": const("PLANNING_SPEED_KMH"),
        "max_walk_h": const("MAX_WALK_H"),
    }
