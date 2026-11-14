"""Skyline matcher on made-up skylines. Expected values are the ones planted."""

import numpy as np
import pytest

from locate.horizon.match import match_skyline

STEP_DEG = 0.25
AZIMUTHS = np.arange(0.0, 360.0, STEP_DEG)


def made_up_grid() -> np.ndarray:
    """A 3 x 4 grid of spots, each with its own lumpy 360° skyline."""
    rng = np.random.default_rng(7)
    grid = np.empty((3, 4, AZIMUTHS.size), np.float32)
    for iy in range(3):
        for ix in range(4):
            phases = rng.uniform(0, 2 * np.pi, 3)
            grid[iy, ix] = (
                2.0 * np.sin(np.radians(AZIMUTHS) + phases[0])
                + 1.0 * np.sin(np.radians(3 * AZIMUTHS) + phases[1])
                + 0.5 * np.sin(np.radians(7 * AZIMUTHS) + phases[2])
            )
    return grid


def photo_from(grid, iy, ix, heading_deg, from_deg, to_deg):
    """What a camera at spot (iy, ix) facing heading_deg sees, from_deg to to_deg
    either side of its heading: azimuth relative to the heading, and elevation."""
    relative = np.arange(from_deg, to_deg, 0.1)
    absolute = (heading_deg + relative) % 360.0
    return relative, np.interp(absolute, AZIMUTHS, grid[iy, ix], period=360.0)


@pytest.mark.parametrize("heading_deg", [123.5, 350.0, 4.25])
def test_a_calculated_skyline_turned_by_a_known_heading_comes_back_with_that_heading(heading_deg):
    grid = made_up_grid()
    relative, elevation = photo_from(grid, 2, 1, heading_deg, -22.5, 22.5)
    match = match_skyline(grid, STEP_DEG, relative, elevation)
    assert (match.iy, match.ix) == (2, 1)
    assert match.heading_deg == pytest.approx(heading_deg, abs=STEP_DEG / 2)
    assert match.cost_deg[2, 1] < 0.05


def test_frames_turned_on_the_spot_combine_into_one_wider_skyline():
    # Two frames from the same spot, the second 90° to the right of the first;
    # their samples are given relative to the first frame's heading.
    grid = made_up_grid()
    first = photo_from(grid, 0, 3, 200.0, -22.5, 22.5)
    second = photo_from(grid, 0, 3, 200.0, 67.5, 112.5)
    match = match_skyline(
        grid,
        STEP_DEG,
        np.concatenate([first[0], second[0]]),
        np.concatenate([first[1], second[1]]),
    )
    assert (match.iy, match.ix, match.heading_deg) == (0, 3, pytest.approx(200.0))


def test_a_few_wild_samples_do_not_pull_the_match_away():
    # A misread stretch of skyline (haze taken for a ridge) 10° higher than
    # the truth over a sixth of the photo.
    grid = made_up_grid()
    relative, elevation = photo_from(grid, 1, 2, 75.0, -22.5, 22.5)
    elevation[:75] += 10.0
    match = match_skyline(grid, STEP_DEG, relative, elevation)
    assert (match.iy, match.ix, match.heading_deg) == (1, 2, pytest.approx(75.0))
