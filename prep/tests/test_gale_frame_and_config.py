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
    best_move,
    best_shift,
    compare_heights,
    fit_pixel_grid,
    grow,
    offset_in_pixels,
    photo_move_on_terrain,
    rover_positions,
    shading,
    site_config,
    slope_degrees,
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
        "z": -3632.81,
    }


def test_the_walk_area_is_the_square_holding_the_walk_radius():
    assert walk_area((8142700.0, -285150.0), 2000.0) == (8140700.0, -287150.0, 8144700.0, -283150.0)
    assert grow((0.0, 0.0, 10.0, 10.0), 5.0) == (-5.0, -5.0, 15.0, 15.0)


def test_site_config_validates_and_keeps_what_later_tickets_added():
    # On disk: Person 4's sol, P2-03's targets, a checkpoint and someone else's file.
    current = {
        "replayed_sol": 4600,
        "science_targets": [{"id": "ridge-1", "name": "Ridge", "position": {"x": 1, "y": 2}}],
        "checkpoints": [{"id": "cp-1", "position": {"x": 3, "y": 4}}],
        "files": {"base_map": "gale/layers/base", "photo_map": "old/photo.tif"},
    }

    config = site_config(
        name="Gale crater boxwork",
        projection="+proj=eqc +lat_ts=0 +lon_0=0 +R=3396190 +units=m +no_defs",
        habitat=(8142700.0, -285150.0),
        base_camp=(8142600.0, -285250.0),
        walk_radius_m=2000.0,
        files={"photo_map": "gale/crops/photo-map-25cm.tif"},
        current=current,
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
    assert config["science_targets"] == current["science_targets"]
    assert config["checkpoints"] == current["checkpoints"]
    # The pack's own files are rewritten; everyone else's stay.
    assert config["files"] == {
        "base_map": "gale/layers/base",
        "photo_map": "gale/crops/photo-map-25cm.tif",
    }


def test_a_first_site_config_starts_with_no_targets_or_checkpoints():
    config = site_config(
        name="Gale",
        projection="+proj=eqc +lat_ts=0 +lon_0=0 +R=3396190 +units=m +no_defs",
        habitat=(0.0, 0.0),
        base_camp=(10.0, 0.0),
        walk_radius_m=2000.0,
        files={},
        current={},
    )

    assert config["science_targets"] == [] and config["checkpoints"] == []
    assert config["replayed_sol"] is None


def test_the_shift_that_best_lines_a_coarse_layer_up_with_a_fine_one_is_found():
    # A 25 m image, and a 100 m layer made by averaging it in 4 x 4 blocks
    # that start 3 rows down and 2 columns left of where the 100 m grid says.
    rng = np.random.default_rng(0)
    fine = rng.normal(size=(120, 120))
    origin = (20, 20)  # the coarse grid's top-left corner on the fine grid (col, row)
    start_row, start_col = origin[1] + 3, origin[0] - 2
    coarse = np.array(
        [
            [
                fine[
                    start_row + 4 * i : start_row + 4 * i + 4,
                    start_col + 4 * j : start_col + 4 * j + 4,
                ].mean()
                for j in range(20)
            ]
            for i in range(20)
        ]
    )

    found = best_shift(coarse, fine, factor=4, origin_px=origin, search_px=6)

    assert found["shift_px"] == (-2, 3)
    assert found["r"] == pytest.approx(1.0)
    assert found["r_unshifted"] < 0.5


def test_the_move_that_lines_a_coarse_layer_up_is_found_in_metres():
    # A 6 m image with its top-left corner at (0, 0), and an 18 m layer made by
    # averaging it in 3 x 3 blocks from fine column 18, row 23: its true corner
    # is at (108, -138). The layer's own grid claims (122.4, -120), off the
    # fine grid by 0.4 of a pixel, so it must move 14.4 m west and 18 m south.
    rng = np.random.default_rng(1)
    fine = rng.normal(size=(150, 150))
    coarse = fine[23 : 23 + 3 * 30, 18 : 18 + 3 * 30].reshape(30, 3, 30, 3).mean(axis=(1, 3))

    found = best_move(
        coarse,
        PixelGrid(left=122.4, top=-120.0, res=18.0),
        fine,
        PixelGrid(left=0.0, top=0.0, res=6.0),
        search_m=30.0,
    )

    assert found["move_m"] == pytest.approx([-14.4, -18.0])
    assert found["r"] == pytest.approx(1.0)
    assert found["r_unmoved"] < 0.5


def test_terrain_heights_at_curiosity_agree_with_places_elevations():
    # PLACES elevations of five stops, and the terrain read at the same spots:
    # off by -0.1, 0.0, +0.2, +0.1 and +3.0 m (the last on a steep edge).
    places = [-3632.8, -3630.0, -3628.5, -3627.0, -3620.0]
    terrain = [-3632.9, -3630.0, -3628.3, -3626.9, -3617.0]

    result = compare_heights(places, terrain, within_m=0.5)

    assert result["median_m"] == pytest.approx(0.1)
    assert result["share_within"] == pytest.approx(0.8)
    assert result["count"] == 5


def test_heights_without_terrain_under_them_are_left_out():
    result = compare_heights([-3630.0, -3631.0], [float("nan"), -3631.2], within_m=0.5)

    assert result["count"] == 1
    assert result["median_m"] == pytest.approx(-0.2)


def test_shading_is_bright_on_slopes_facing_the_light():
    # A plane rising 0.1 m per metre eastward faces west.
    x = np.arange(20, dtype=float) * 2.0
    heights = np.tile(0.1 * x, (20, 1))

    assert shading(heights, 2.0, azimuth_deg=270.0)[10, 10] == pytest.approx(0.1)
    assert shading(heights, 2.0, azimuth_deg=90.0)[10, 10] == pytest.approx(-0.1)
    # Light from the north sees no tilt north-south.
    assert shading(heights, 2.0, azimuth_deg=0.0)[10, 10] == pytest.approx(0.0)


def test_slope_of_a_plane_rising_one_in_ten_is_its_arctangent():
    rows = np.arange(30, dtype=float) * 1.0
    heights = np.tile(0.1 * rows, (30, 1)).T  # rising southward (down the rows)

    # atan(0.1) = 5.7106 degrees.
    assert slope_degrees(heights, 1.0)[15, 15] == pytest.approx(5.7106, abs=1e-3)


def _hills(n: int, res: float) -> np.ndarray:
    """Irregular ground: 40 waves of random direction and length, so no shift repeats it."""
    rng = np.random.default_rng(2)
    y, x = np.mgrid[0:n, 0:n] * res
    heights = np.zeros((n, n))
    for _ in range(40):
        angle, length, phase = rng.uniform(0, np.pi), rng.uniform(15, 120), rng.uniform(0, 6.3)
        heights += np.sin((x * np.cos(angle) + y * np.sin(angle)) / length * 2 * np.pi + phase)
    return heights


def test_a_photo_map_placed_off_its_terrain_is_found_off():
    # Terrain on a 2 m grid from (0, 0). The photo shows its shading lit from
    # the west-north-west, but starting at terrain column 20 and row 5 while its
    # grid claims (0, 0): the terrain must move 40 m west and 10 m north to
    # line up with it.
    res = 2.0
    heights = _hills(400, res)
    photo = shading(heights, res, azimuth_deg=300.0)[5 : 5 + 300, 20 : 20 + 300]

    found = photo_move_on_terrain(
        photo, PixelGrid(0.0, 0.0, res), heights, PixelGrid(0.0, 0.0, res), search_m=80.0
    )

    assert found["move_m"] == pytest.approx([-40.0, 10.0])
    assert found["r"] == pytest.approx(1.0)


def test_a_photo_map_on_its_terrain_needs_no_move():
    res = 2.0
    heights = _hills(300, res)
    photo = shading(heights, res, azimuth_deg=300.0)

    found = photo_move_on_terrain(
        photo, PixelGrid(0.0, 0.0, res), heights, PixelGrid(0.0, 0.0, res), search_m=80.0
    )

    assert found["move_m"] == pytest.approx([0.0, 0.0])
    assert found["azimuth_deg"] == 300
