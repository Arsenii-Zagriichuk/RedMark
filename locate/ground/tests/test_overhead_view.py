"""A top-down Navcam mosaic becomes a north-up overhead view at the photo map's 25 cm."""

import numpy as np

from locate.ground.mosaic import overhead_view

# A VRT mosaic: 4800 x 4800 pixels of 5 mm, 24 m across, the rover at its centre.
SIZE = 4800


def _mosaic() -> np.ndarray:
    pixels = np.full((SIZE, SIZE), 100, np.uint16)
    # A bright 1 m square centred 6 m north and 3 m east of the rover:
    # north is up (line 0 is 12 m north), east is right.
    pixels[1100:1300, 2900:3100] = 1000
    # Nothing was seen more than 6 m west of the rover.
    pixels[:, :1200] = 0
    return pixels


def test_the_view_is_north_up_at_25_cm():
    view = overhead_view(_mosaic())

    assert view.image.shape == (96, 96)
    # 6 m north is 24 cells above the centre (row 48), 3 m east 12 cells right.
    bright = np.argwhere(view.image > 500)
    assert bright.min(axis=0).tolist() == [22, 58]
    assert bright.max(axis=0).tolist() == [25, 61]


def test_blank_pixels_and_the_rover_are_masked():
    view = overhead_view(_mosaic())

    # More than 6 m west of the rover: 24 columns of 25 cm never seen.
    assert not view.mask[:, :24].any()
    # The rover and its shadow: within 3 m (12 cells) of the centre.
    assert not view.mask[48, 40:56].any()
    assert not view.mask[44:52, 48].any()
    # Seen ground 4 m south of the rover counts.
    assert view.mask[64, 48]
    assert view.mask[22, 58]
