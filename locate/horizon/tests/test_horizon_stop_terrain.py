"""Each tested stop's terrain type and hollow flag, from made-up 1 m terrain."""

import numpy as np

from contracts.models.common import TerrainType
from locate.horizon.stop_terrain import is_hollow, terrain_type

RES_M = 1.0
HALF = 60  # a 121 m window round the stop
y, x = np.mgrid[-HALF : HALF + 1, -HALF : HALF + 1].astype(np.float32)


def test_the_bottom_of_a_bowl_is_a_hollow():
    # z = 0.002 r²: the ground within 50 m averages 0.002 × 50² / 2 = 2.5 m above the centre.
    bowl = 0.002 * (x**2 + y**2)

    assert is_hollow(bowl, RES_M)


def test_a_ridge_top_is_not_a_hollow():
    ridge_top = -0.002 * (x**2 + y**2)

    assert not is_hollow(ridge_top, RES_M)


def test_a_steady_slope_is_plain_open_ground():
    slope = 0.2 * x + 0.1 * y

    assert not is_hollow(slope, RES_M)
    assert terrain_type(slope, RES_M) == TerrainType.plain


def test_metre_scale_rock_on_a_slope_is_textured():
    # Blocks 2 m across, 0.5 m up and down: half a metre of roughness.
    rocks = 0.5 * np.where((x // 2 + y // 2) % 2 == 0, 1.0, -1.0)

    assert terrain_type(0.2 * x + rocks, RES_M) == TerrainType.textured
