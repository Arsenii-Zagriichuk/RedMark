"""Seams: Curiosity's positions share the crops' frame, and the site config validates.

PLACES gives each rover position both in map metres and as a pixel of the
orthophoto and terrain it was localised on. Fitting that pixel grid and
finding it a whole number of pixels from our maps' grids shows the two were
made on the same grid, so the rover positions and the crops share a frame.
"""

from pathlib import Path

import numpy as np
import pytest

from contracts.models.site import SiteConfig
from prep.gale.pack import (
    PixelGrid,
    best_shift,
    fit_pixel_grid,
    grow,
    offset_in_pixels,
    rover_positions,
    site_config,
    walk_area,
)

FIXTURES = Path(__file__).parent / "fixtures"
PLACES = FIXTURES / "places_localized_pos_excerpt.csv"


def test_a_pixel_grid_is_recovered_from_positions_and_their_pixels():
    grid = PixelGrid(left=8141038.0, top=-271514.0, res=0.25)
    pixels = [(23092.89, 2101.07), (100.0, 40000.5), (9000.25, 13.75)]
    eastings = [grid.left + s * grid.res for s, _ in pixels]
    northings = [grid.top - line * grid.res for _, line in pixels]

    fitted = fit_pixel_grid(eastings, northings, [s for s, _ in pixels], [ln for _, ln in pixels])

    assert fitted.left == pytest.approx(8141038.0, abs=1e-3)
    assert fitted.top == pytest.approx(-271514.0, abs=1e-3)
    assert fitted.res == pytest.approx(0.25, abs=1e-9)


def test_offset_between_two_grids_is_counted_in_pixels():
    # The Gale photo map's published grid, and a map starting 3,697.5 m east
    # and 7,587.5 m south of its corner: 14,790 columns and 30,350 rows in.
    gale = PixelGrid(left=8126248.0, top=-241164.0, res=0.25)
    other = PixelGrid(left=8129945.5, top=-248751.5, res=0.25)

    assert offset_in_pixels(other, on=gale) == pytest.approx((14790.0, 30350.0))
    shifted = PixelGrid(left=other.left + 0.05, top=other.top, res=0.25)
    assert offset_in_pixels(shifted, on=gale)[0] == pytest.approx(14790.2)


def test_grids_of_different_resolution_are_not_compared():
    with pytest.raises(ValueError, match="resolution"):
        offset_in_pixels(PixelGrid(0.0, 0.0, 1.0), on=PixelGrid(0.0, 0.0, 0.25))


def test_rover_positions_inside_the_bounds_come_from_rover_rows_only():
    # The boxwork rows of the excerpt sit near x 8143130, y -284800 to -284970;
    # the SITE row at sol 4614 is a site origin, not a rover position.
    bounds = (8142000.0, -285500.0, 8144000.0, -284000.0)

    positions = rover_positions(PLACES, bounds)

    assert [p["sol"] for p in positions] == [4600, 4616, 4629, 4643, 4662]
    assert positions[0] == {
        "sol": 4600,
        "site": 117,
        "drive": 2370,
        "x": 8143139.321,
        "y": -284766.85,
    }


def test_the_walk_area_is_the_square_holding_the_walk_radius():
    assert walk_area((8142700.0, -285150.0), 2000.0) == (8140700.0, -287150.0, 8144700.0, -283150.0)
    assert grow((0.0, 0.0, 10.0, 10.0), 5.0) == (-5.0, -5.0, 15.0, 15.0)


def test_site_config_validates_and_keeps_person_4s_sol():
    files = {"photo_map": "gale/crops/photo-map-25cm.tif"}

    config = site_config(
        name="Gale crater boxwork",
        projection="+proj=eqc +lat_ts=0 +lon_0=0 +R=3396190 +units=m +no_defs",
        habitat=(8142700.0, -285150.0),
        base_camp=(8142600.0, -285250.0),
        walk_radius_m=2000.0,
        files=files,
        replayed_sol=4600,
    )

    SiteConfig.model_validate(config)
    assert config["site"] == "gale"
    assert config["bounds"] == {
        "min_x": 8140700.0,
        "min_y": -287150.0,
        "max_x": 8144700.0,
        "max_y": -283150.0,
    }
    assert config["habitat"] == {"x": 8142700.0, "y": -285150.0}
    assert config["base_camp"] == {"x": 8142600.0, "y": -285250.0}
    assert config["replayed_sol"] == 4600
    assert config["files"] == files
    # Science targets come in P2-03.
    assert config["science_targets"] == [] and config["checkpoints"] == []


def test_the_shift_that_best_lines_a_coarse_layer_up_with_a_fine_one_is_found():
    # A 25 m image, and a 100 m layer made by averaging it in 4 x 4 blocks
    # that start 3 rows down and 2 columns left of where the 100 m grid says.
    rng = np.random.default_rng(0)
    fine = rng.normal(size=(120, 120))
    origin = (20, 20)  # the coarse grid's top-left corner on the fine grid (col, row)
    start_row, start_col = origin[1] + 3, origin[0] - 2
    coarse = fine[start_row : start_row + 80, start_col : start_col + 80]
    coarse = coarse.reshape(20, 4, 20, 4).mean(axis=(1, 3))

    found = best_shift(coarse, fine, factor=4, origin_px=origin, search_px=6)

    assert found["shift_px"] == (-2, 3)
    assert found["r"] == pytest.approx(1.0)
    assert found["r_unshifted"] < 0.5
