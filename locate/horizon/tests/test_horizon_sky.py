"""Skyline extraction on a made-up photo whose skyline is planted."""

import numpy as np

from locate.horizon.sky import skyline_rows


def made_up_photo():
    """Smooth sky brightening downward over rough darker ground, below a wavy
    line at row 100 + 30 sin(col / 40); plus the defects real frames have: a
    saturated top row and one dead column."""
    rng = np.random.default_rng(3)
    rows, cols = np.indices((240, 320), dtype=np.float64)
    line = 100 + 30 * np.sin(np.arange(320) / 40)
    sky = 1500 + 2 * rows + rng.normal(0, 15, rows.shape)
    ground = 1100 + rng.normal(0, 150, rows.shape)
    image = np.where(rows < line, sky, ground)
    image[0] = 3900
    image[:, 150] = 0
    return image.astype(np.float32), line


def test_the_skyline_is_found_where_it_was_planted():
    # Within 4 px: on Navcam (0.047° a pixel) that is under one 0.25° step of
    # the horizon grid.
    image, line = made_up_photo()
    rows = skyline_rows(image)
    inside = slice(20, 300)
    assert np.isfinite(rows[inside]).all()
    assert np.abs(rows[inside] - line[inside]).max() <= 4.0


def test_where_the_skyline_rises_out_of_the_top_of_the_frame_there_is_none():
    # A ridge climbing out of the frame: the planted line is above row 0 for
    # columns 0 to 99. A lower edge there (a band on the slope at row 60)
    # must not be taken for the skyline.
    rng = np.random.default_rng(5)
    rows, cols = np.indices((240, 320), dtype=np.float64)
    line = -50 + 0.5 * np.arange(320)
    image = np.where(rows < line, 1500 + rng.normal(0, 15, rows.shape), 1100.0)
    image = image + rng.normal(0, 150, rows.shape) * (rows >= line)
    image[60:, :100] -= 300
    found = skyline_rows(image.astype(np.float32))
    assert np.isnan(found[20:90]).all()
    assert np.abs(found[130:300] - line[130:300]).max() <= 4.0


def test_a_photo_with_no_skyline_gives_none():
    rng = np.random.default_rng(4)
    ground = (1100 + rng.normal(0, 150, (240, 320))).astype(np.float32)
    assert np.isnan(skyline_rows(ground)).all()
