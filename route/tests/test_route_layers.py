"""Reading the layers named in a site config onto the planning grid, and planning on them."""

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from contracts.models.site import SiteConfig
from route.layers import load_grid

NODATA = -9999.0
PROJECTION = "+proj=eqc +lat_ts=0 +lon_0=0 +R=3396190 +units=m +no_defs"


def site(files: dict[str, str]) -> SiteConfig:
    return SiteConfig(
        site="gale",
        name="Tiny test site",
        projection=PROJECTION,
        bounds={"min_x": 1000, "min_y": 2000, "max_x": 1008, "max_y": 2008},
        habitat={"x": 1004, "y": 2004},
        base_camp=None,
        science_targets=[],
        checkpoints=[],
        files=files,
        replayed_sol=None,
    )


def write_raster(path, values) -> None:
    values = np.asarray(values, dtype=np.float32)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=values.shape[1],
        height=values.shape[0],
        count=1,
        dtype="float32",
        crs=PROJECTION,
        transform=from_origin(1000, 2008, 1.0, 1.0),
        nodata=NODATA,
    ) as dst:
        dst.write(values, 1)


def test_slope_is_read_onto_the_planning_grid_keeping_the_steepest_metre(tmp_path):
    slope = np.full((8, 8), 5.0)
    slope[1, 6] = 25
    write_raster(tmp_path / "slope.tif", slope)

    g = load_grid(site({"slope": "slope.tif"}), tmp_path, cell_m=4.0)

    assert (g.min_x, g.max_y, g.cell_m) == (1000, 2008, 4.0)
    assert g.slope_deg.tolist() == [[5, 25], [5, 5]]


def test_a_planning_cell_with_any_unknown_metre_is_unknown(tmp_path):
    slope = np.full((8, 8), 5.0)
    slope[0:2, 0:2] = NODATA
    write_raster(tmp_path / "slope.tif", slope)

    g = load_grid(site({"slope": "slope.tif"}), tmp_path, cell_m=4.0)

    assert np.isnan(g.slope_deg[0, 0])
    assert g.slope_deg[0, 1] == 5 and g.slope_deg[1].tolist() == [5, 5]


def test_a_planning_cell_the_slope_file_only_half_covers_is_unknown(tmp_path):
    write_raster(tmp_path / "slope.tif", np.full((6, 8), 5.0))

    g = load_grid(site({"slope": "slope.tif"}), tmp_path, cell_m=4.0)

    assert g.slope_deg[0].tolist() == [5, 5]
    assert np.isnan(g.slope_deg[1]).all()


def test_sand_and_ridge_maps_are_read_as_masks(tmp_path):
    write_raster(tmp_path / "slope.tif", np.zeros((8, 8)))
    sand = np.zeros((8, 8))
    sand[6, 1] = 1
    ridge = np.zeros((8, 8))
    ridge[0, 0] = 1
    write_raster(tmp_path / "sand.tif", sand)
    write_raster(tmp_path / "ridges.tif", ridge)

    g = load_grid(
        site({"slope": "slope.tif", "sand": "sand.tif", "ridges": "ridges.tif"}), tmp_path, 4.0
    )

    assert g.sand.tolist() == [[False, False], [True, False]]
    assert g.ridge.tolist() == [[True, False], [False, False]]


def test_a_site_without_a_slope_file_plans_on_flat_stub_ground(tmp_path):
    g = load_grid(site({"base_map": "gale/layers/base"}), tmp_path, cell_m=4.0)

    assert g.slope_deg.tolist() == [[0, 0], [0, 0]]
    assert not g.sand.any() and not g.ridge.any()


def test_a_slope_file_named_in_the_site_config_must_exist(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_grid(site({"slope": "missing.tif"}), tmp_path, cell_m=4.0)
