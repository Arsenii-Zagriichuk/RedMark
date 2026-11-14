"""Landmark visibility on made-up terrain. Expected values are worked by hand."""

import numpy as np
import pytest

from layers.location_quality.visibility import (
    Cells,
    Landmark,
    landmark_masks,
    location_quality,
    sees_point,
)
from locate.horizon.render import Raster, Terrain, Tier

EYE_M = 1.9


def ground(width_m: float, height_m: float, res_m: float, *, south_m: float) -> Raster:
    """Flat ground at 0 m from x = -width/2 to +width/2 and y = -south_m to height_m - south_m."""
    rows, cols = round(height_m / res_m), round(width_m / res_m)
    return Raster(
        np.zeros((rows, cols), np.float32), left=-width_m / 2, top=height_m - south_m, res=res_m
    )


def raise_block(raster: Raster, x0: float, x1: float, y0: float, y1: float, height_m: float):
    """Set every pixel whose centre lies in [x0, x1] x [y0, y1] to height_m."""
    rows, cols = raster.heights.shape
    xs = raster.left + (np.arange(cols) + 0.5) * raster.res
    ys = raster.top - (np.arange(rows) + 0.5) * raster.res
    inside_y = (ys >= y0) & (ys <= y1)
    inside_x = (xs >= x0) & (xs <= x1)
    raster.heights[np.ix_(inside_y, inside_x)] = height_m


# 20 x 20 cells of 10 m round the origin: x and y from -100 to 100 m.
CELLS = Cells(left=-100.0, top=100.0, res=10.0, shape=(20, 20))


def test_flat_ground_sees_a_tower_10_km_away():
    # A 200 m tower 10 km north on flat ground: seen from 1.9 m at
    # atan(198 / 10000) = +1.1°, with nothing in between.
    terrain = ground(4_000, 14_000, 10.0, south_m=2_000)
    raise_block(terrain, -50, 50, 9_950, 10_050, 200.0)
    visible = sees_point(
        Terrain([Tier(terrain)]),
        (0.0, 10_000.0),
        CELLS,
        body_radius_m=100.0,
        observer_height_m=EYE_M,
    )
    assert visible.shape == (20, 20)
    assert visible.all()


def test_a_wall_hides_the_tower_only_from_the_cells_behind_it():
    # The same tower, and a 50 m wall 1 km north from x = 10 m eastwards.
    # The wall's top is at atan(48.1 / 1000) = 2.75°, above the tower's 1.1°.
    # A cell at x looks at the tower (x = 0) across y = 1 km at about 0.9 x,
    # so cells with centre x >= 25 m look into the wall, and cells at
    # x <= -5 m look past its western end.
    terrain = ground(4_000, 14_000, 10.0, south_m=2_000)
    raise_block(terrain, -50, 50, 9_950, 10_050, 200.0)
    raise_block(terrain, 10, 2_000, 1_000, 1_020, 50.0)
    visible = sees_point(
        Terrain([Tier(terrain)]),
        (0.0, 10_000.0),
        CELLS,
        body_radius_m=100.0,
        observer_height_m=EYE_M,
    )
    xs = CELLS.left + (np.arange(20) + 0.5) * CELLS.res
    assert not visible[:, xs >= 25].any()
    assert visible[:, xs <= -5].all()


def test_curvature_hides_a_low_tower_60_km_away_but_not_a_tall_one():
    # On flat ground on the 3,396.19 km sphere, an eye 1.9 m up sees the
    # ground out to sqrt(2 R 1.9) = 3.6 km; beyond that a tower must rise above
    # (60 - 3.6)^2 / (2 R) = 468 m to show 60 km away. 100 m is hidden, 1000 m
    # shows.
    def tower(height_m: float) -> np.ndarray:
        terrain = ground(2_000, 64_000, 100.0, south_m=2_000)
        raise_block(terrain, -100, 100, 59_900, 60_100, height_m)
        return sees_point(
            Terrain([Tier(terrain)]),
            (0.0, 60_000.0),
            CELLS,
            body_radius_m=200.0,
            observer_height_m=EYE_M,
        )

    assert not tower(100.0).any()
    assert tower(1_000.0).all()


def test_a_ridge_top_sees_the_landmark_behind_the_ridge_and_the_hollow_below_it_does_not():
    # Flat ground with an east-west ridge 30 m tall from y = 100 to 140 m.
    # Landmark "south": a 300 m tower 5 km south. Landmark "north": a 300 m
    # tower 5 km north, with nothing in the way.
    # A cell on the ridge top (y = 115 m) sees both. A cell in the hollow at
    # the ridge's foot (y = 165 m) looks south at the ridge's top 25 m away,
    # atan(28 / 25) = 48°, far above the south tower's atan(298 / 5165) = 3.3°.
    # So the ridge top scores 2 of 2 and the hollow 1 of 2.
    terrain = ground(4_000, 12_000, 5.0, south_m=6_000)
    raise_block(terrain, -2_000, 2_000, 100, 140, 30.0)
    raise_block(terrain, -50, 50, -5_050, -4_950, 300.0)
    raise_block(terrain, -50, 50, 4_950, 5_050, 300.0)
    landmarks = [
        Landmark("south", "South tower", ((0.0, -5_000.0),), body_radius_m=100.0),
        Landmark("north", "North tower", ((0.0, 5_000.0),), body_radius_m=100.0),
    ]
    cells = Cells(left=-10.0, top=170.0, res=5.0, shape=(12, 4))  # y from 110 to 170 m
    masks = landmark_masks(Terrain([Tier(terrain)]), landmarks, cells, observer_height_m=EYE_M)
    score = location_quality(masks)
    ys = cells.top - (np.arange(12) + 0.5) * cells.res
    ridge_top, hollow = ys == 112.5, ys == 162.5
    assert masks["south"][ridge_top].all() and masks["north"][ridge_top].all()
    assert not masks["south"][hollow].any() and masks["north"][hollow].all()
    assert score[ridge_top] == pytest.approx(1.0)
    assert score[hollow] == pytest.approx(0.5)


def test_a_landmark_of_several_points_is_seen_if_any_of_them_is():
    # A rim of two 300 m towers 5 km north, at x = -1 km and x = +1 km, and a
    # 100 m wall 1 km north from x = 50 m eastwards. A cell at x looks at the
    # eastern tower across y = 1 km at 0.8 x + 200 m (120 to 280 m), into the
    # wall, whose top at atan(98 / 1000) = 5.6° is above the tower's
    # atan(298 / 5000) = 3.4°. Towards the western tower it crosses at
    # 0.8 x - 200 m, west of the wall. So the rim counts as seen.
    terrain = ground(6_000, 8_000, 10.0, south_m=2_000)
    raise_block(terrain, -1_050, -950, 4_950, 5_050, 300.0)
    raise_block(terrain, 950, 1_050, 4_950, 5_050, 300.0)
    raise_block(terrain, 50, 3_000, 1_000, 1_020, 100.0)
    one = Landmark("east", "East tower", ((1_000.0, 5_000.0),), body_radius_m=100.0)
    rim = Landmark("rim", "Rim", ((-1_000.0, 5_000.0), (1_000.0, 5_000.0)), body_radius_m=100.0)
    masks = landmark_masks(Terrain([Tier(terrain)]), [one, rim], CELLS, observer_height_m=EYE_M)
    assert not masks["east"].any()
    assert masks["rim"].all()


def test_location_quality_is_the_share_of_landmarks_seen():
    yes, no = np.ones((1, 1), bool), np.zeros((1, 1), bool)
    assert location_quality({"a": yes, "b": no, "c": no, "d": no})[0, 0] == pytest.approx(0.25)
    assert location_quality({"a": yes, "b": yes, "c": yes, "d": no})[0, 0] == pytest.approx(0.75)
