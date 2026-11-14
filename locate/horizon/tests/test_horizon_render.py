"""Horizon renderer on made-up terrain. Expected values are worked by hand."""

import numpy as np
import pytest

from locate.horizon.render import Raster, Terrain, Tier, skyline


def flat(size_px: int, res_m: float, height_m: float = 0.0) -> Raster:
    """Flat ground centred on (0, 0)."""
    half = size_px * res_m / 2
    return Raster(
        np.full((size_px, size_px), height_m, np.float32), left=-half, top=half, res=res_m
    )


def test_flat_ground_60_km_away_sits_half_a_degree_below_the_flat_horizon():
    # 60 km on a 3396.19 km sphere: the surface drops about 530 m, so the
    # ground there is seen at atan(530 / 60000), about -0.506°.
    terrain = Terrain([Tier(flat(130, 1000.0))])
    elevation = skyline(
        terrain,
        0.0,
        0.0,
        observer_height_m=0.0,
        azimuths_deg=np.array([0.0, 90.0]),
        distances_m=np.array([60_000.0]),
    )
    assert elevation == pytest.approx([-0.506, -0.506], abs=0.005)


def test_a_wall_of_known_height_and_distance_gives_its_elevation_angle():
    # Flat ground at 0 m on a 1 m grid, eye at ground level at (0, 0).
    # East: a wall 100 m tall from 1000 m out -> atan(100 / 1000) = 5.71°.
    # North: a wall 50 m tall from 2000 m out -> atan(50 / 2000) = 1.43°.
    # South and west stay flat -> 0°.
    ground = flat(5000, 1.0)
    centre = 2500  # column/row index of the pixel whose west/north edge is at 0 m
    ground.heights[:, centre + 1000 : centre + 1030] = 100.0
    ground.heights[centre - 2030 : centre - 2000, :] = 50.0
    elevation = skyline(
        Terrain([Tier(ground)]),
        0.0,
        0.0,
        observer_height_m=0.0,
        azimuths_deg=np.array([0.0, 90.0, 180.0, 270.0]),
        distances_m=np.arange(5.0, 2400.0, 1.0),
    )
    assert elevation == pytest.approx([1.43, 5.71, 0.0, 0.0], abs=0.02)


def test_terrain_falls_back_to_the_coarser_tier_where_the_finer_has_no_data_or_no_reach():
    # Fine tier: 10 m everywhere except a gap with no data, used out to 500 m.
    # Coarse tier: 70 m everywhere.
    fine = flat(2000, 1.0, height_m=10.0)
    fine.heights[:100, :] = np.nan  # the northmost 100 m: y from 900 to 1000
    coarse = flat(100, 100.0, height_m=70.0)
    terrain = Terrain([Tier(fine, max_distance_m=500.0), Tier(coarse)])
    heights = terrain.height(
        x=np.array([0.0, 0.0, 0.0]),
        y=np.array([100.0, 950.0, 700.0]),
        distance_m=np.array([100.0, 400.0, 700.0]),
    )
    # fine data in reach; no fine data there; fine data but out of its reach
    assert heights == pytest.approx([10.0, 70.0, 70.0])
