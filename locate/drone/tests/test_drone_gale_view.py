"""Seams: the simulated Gale drone photo, cut from a photo map and run through
the drone pipeline, comes back to where it was cut; the suit markers drawn in
it come back to the astronauts' map positions.

The photo map is synthetic, and the stand-in matcher only succeeds if the
straightened photo really is the map, north up, at 25 cm (drone_stand_ins).
"""

from pathlib import Path

import numpy as np
import pytest
import rasterio
from drone_stand_ins import ncc_matcher, smooth_noise
from rasterio.transform import from_origin

from locate.drone.fix import locate_on_map
from locate.drone.gale_view import Astronaut, take_photo
from locate.drone.ground import HALF_SIZE_M, read_map_window
from locate.drone.pipeline import SEARCH_RADIUS_M

RES = 0.25
MIN_X, MAX_Y = 8142000.0, -285000.0
MAP_PX = 900  # 225 m square
# On a map pixel corner 112.5 m from the west and north edges, so the
# straightened photo's pixels line up with the map's and the stand-in
# matcher's whole-pixel shifts are exact.
NADIR = (8142112.5, -285112.5)
DRONE_HEADING_DEG = 30.0


@pytest.fixture
def photo_map(tmp_path: Path) -> Path:
    noise = smooth_noise(MAP_PX, sigma_px=2.0, seed=7)
    values = np.clip(2000 + 600 * noise / noise.std(), 0, 4095).astype(np.uint16)
    crop = tmp_path / "photo-map.tif"
    with rasterio.open(
        crop,
        "w",
        driver="GTiff",
        width=MAP_PX,
        height=MAP_PX,
        count=1,
        dtype="uint16",
        transform=from_origin(MIN_X, MAX_Y, RES, RES),
    ) as dst:
        dst.write(values, 1)
    return crop


def test_photo_cut_from_the_map_is_fixed_where_it_was_cut(photo_map):
    photo = take_photo(photo_map, NADIR, DRONE_HEADING_DEG, crew=[])
    # The drone's own heading is right here: the stand-in matcher finds
    # shifts, not turns.
    ground = photo.straighten(onboard_heading_deg=DRONE_HEADING_DEG, resolution=RES)
    # The search starts 7.9 m off, as from a drifted onboard position.
    prior = (NADIR[0] + 6.3, NADIR[1] - 4.7)
    window = read_map_window(photo_map, prior, SEARCH_RADIUS_M + HALF_SIZE_M)

    fix = locate_on_map(ground, window, ncc_matcher)

    assert fix.position == pytest.approx(NADIR, abs=0.1)
    assert fix.heading_deg == pytest.approx(DRONE_HEADING_DEG, abs=0.5)


def test_suit_markers_come_back_to_the_astronauts_on_the_map(photo_map):
    # Two astronauts 3 m apart, walking north-east and east, both inside the
    # photo and off its nadir.
    crew = [
        Astronaut(position=(8142105.0, -285110.0), heading_deg=45.0),
        Astronaut(position=(8142108.0, -285110.0), heading_deg=90.0),
    ]
    photo = take_photo(photo_map, NADIR, DRONE_HEADING_DEG, crew=crew)
    ground = photo.straighten(onboard_heading_deg=DRONE_HEADING_DEG, resolution=RES)
    window = read_map_window(photo_map, NADIR, SEARCH_RADIUS_M + HALF_SIZE_M)
    fix = locate_on_map(ground, window, ncc_matcher)

    found = photo.astronauts_on_map(ground, fix, window)

    found = sorted(found, key=lambda astronaut: astronaut.position[0])
    assert len(found) == 2
    for astronaut, expected in zip(found, crew, strict=True):
        assert astronaut.position == pytest.approx(expected.position, abs=0.1)
        assert astronaut.heading_deg == pytest.approx(expected.heading_deg, abs=2.0)
