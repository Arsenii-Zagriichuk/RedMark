"""An overhead view is found on the photo map at the rover's position, in map metres."""

import numpy as np
from scipy.ndimage import gaussian_filter

from locate.ground.match import MapWindow, ground_match
from locate.ground.mosaic import OverheadView

# A 120 m photo-map window of 25 cm cells whose north-west corner is at (8142000, -284000).
WINDOW = MapWindow(
    image=gaussian_filter(np.random.default_rng(7).normal(size=(480, 480)), 3) * 1000 + 120,
    left_x=8142000.0,
    top_y=-284000.0,
)


def _view_cut_at(row: int, col: int) -> OverheadView:
    image = WINDOW.image[row : row + 96, col : col + 96].copy()
    return OverheadView(image=image, mask=np.ones((96, 96), bool))


def test_the_view_is_found_at_the_rovers_position():
    # Cut 100 cells (25 m) down and 300 cells (75 m) across: the rover, at the
    # cut's centre, stands 25 + 12 = 37 m south and 75 + 12 = 87 m east of the corner.
    match = ground_match(WINDOW, _view_cut_at(100, 300))

    assert (match.x, match.y) == (8142087.0, -284037.0)


def test_masked_cells_are_left_out_of_the_match():
    view = _view_cut_at(300, 60)
    view.image[:48, :48] = 0.0  # a quarter never seen
    view.mask[:48, :48] = False

    match = ground_match(WINDOW, view)

    assert (match.x, match.y) == (8142027.0, -284087.0)
