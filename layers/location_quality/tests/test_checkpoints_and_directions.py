"""Checkpoint candidates and lost-mode landmark directions (layer 5, P3-06).
Expected values are worked by hand."""

import numpy as np

from layers.location_quality.checkpoints import checkpoint_candidates
from layers.location_quality.directions import bearing_deg, landmark_view, leg_directions
from layers.location_quality.visibility import Cells, Landmark

# 10 x 10 cells of 10 m: x from 0 to 100 m, y from 0 to 100 m; row 0 is the top (y 90-100).
CELLS = Cells(left=0.0, top=100.0, res=10.0, shape=(10, 10))


def test_each_square_gives_its_best_cell_off_hollows_best_first():
    # 50 m squares: four of them, 5 x 5 cells each.
    score = np.full(CELLS.shape, 0.1, np.float32)
    hollow = np.zeros(CELLS.shape, bool)
    score[0, 0] = 1.0  # north-west square's best cell, but a hollow: never a checkpoint
    hollow[0, 0] = True
    score[2, 2] = 0.9  # so the north-west square gives (25, 75)
    score[3, 3] = np.nan  # no terrain: never a checkpoint
    score[1, 8] = 0.6  # north-east square: (85, 85)
    hollow[5:, :5] = True  # the south-west square is all hollow: no candidate
    score[9, 9] = 0.7  # south-east square: (95, 5)
    picked = checkpoint_candidates(score, hollow, CELLS, square_m=50.0, neighbourhood_m=10.0)
    assert picked == [(25.0, 75.0), (95.0, 5.0), (85.0, 85.0)]


def test_a_tie_goes_to_the_cell_with_the_better_ground_round_it():
    # One 100 m square; two cells share the best score, one of them amid good ground.
    score = np.full(CELLS.shape, 0.1, np.float32)
    score[2, 2] = 1.0
    score[6:9, 6:9] = 0.8
    score[7, 7] = 1.0  # (75, 25), its 8 neighbours at 0.8
    picked = checkpoint_candidates(
        score, np.zeros(CELLS.shape, bool), CELLS, square_m=100.0, neighbourhood_m=10.0
    )
    assert picked == [(75.0, 25.0)]


# Directions. Texoli stands 10 km due north of the cells; the rim is two far points,
# due west and due north, so its bearing from the cells is their mean, 315°.
TEXOLI = Landmark("texoli", "Texoli", ((50.0, 10_000.0),), 100.0, in_sentence="Texoli")
RIM = Landmark(
    "crater_rim",
    "Gale crater rim",
    ((-30_000.0, 50.0), (50.0, 30_000.0)),
    1000.0,
    in_sentence="the Gale crater rim",
)
SEE_ALL = {"texoli": np.ones(CELLS.shape, bool), "crater_rim": np.ones(CELLS.shape, bool)}


def one_leg(path: list[tuple[float, float]], masks=SEE_ALL, landmarks=(TEXOLI, RIM)) -> dict:
    points = [{"x": x, "y": y} for x, y in path]
    legs = [{"start_index": 0, "end_index": len(path) - 1, "distance_m": 0.0, "time_s": 0.0}]
    (leg,) = leg_directions(points, legs, list(landmarks), masks, CELLS, step_m=10.0)
    return leg


def test_bearings_are_clockwise_from_map_north():
    assert bearing_deg((0.0, 0.0), (0.0, 100.0)) == 0.0
    assert bearing_deg((0.0, 0.0), (100.0, 0.0)) == 90.0
    assert bearing_deg((0.0, 0.0), (0.0, -100.0)) == 180.0
    assert bearing_deg((0.0, 0.0), (-100.0, 0.0)) == 270.0


def test_walking_east_keeps_a_landmark_due_north_on_your_left():
    leg = one_leg([(10.0, 50.0), (90.0, 50.0)])
    assert leg["heading_deg"] == 90.0
    assert leg["landmark"] == "texoli"
    assert leg["side"] == "left"
    assert leg["text"] == "Keep Texoli on your left"


def test_walking_north_west_and_south_put_it_ahead_right_and_behind():
    assert one_leg([(50.0, 10.0), (50.0, 90.0)])["text"] == "Walk towards Texoli"
    assert one_leg([(90.0, 50.0), (10.0, 50.0)])["text"] == "Keep Texoli on your right"
    assert one_leg([(50.0, 90.0), (50.0, 10.0)])["text"] == "Keep Texoli behind you"


def test_bearings_wrap_round_north():
    # A landmark at 350° seen while walking at 10° is 20° to the left: ahead.
    north_by_west = Landmark("texoli", "Texoli", ((50.0 - 1763.3, 10_000.0),), 100.0)
    leg = one_leg([(50.0, 10.0), (63.9, 88.8)], landmarks=[north_by_west])
    assert leg["side"] == "ahead"
    assert round(leg["landmarks"][0]["relative_deg"]) == -20


def test_a_landmark_hidden_along_most_of_the_leg_is_passed_over_for_one_in_view():
    # Texoli is hidden from the east half; a leg along the east half steers by the rim.
    hidden_east = np.ones(CELLS.shape, bool)
    hidden_east[:, 5:] = False
    leg = one_leg([(60.0, 10.0), (60.0, 90.0)], masks={**SEE_ALL, "texoli": hidden_east})
    assert leg["landmark"] == "crater_rim"
    # The rim's mean bearing is 315°, 45° left of north.
    assert leg["text"] == "Keep the Gale crater rim on your left"
    texoli = next(lm for lm in leg["landmarks"] if lm["id"] == "texoli")
    assert texoli["share_of_leg_in_view"] == 0.0


def test_a_leg_with_no_landmark_in_view_has_no_direction():
    none = {name: np.zeros(CELLS.shape, bool) for name in SEE_ALL}
    leg = one_leg([(10.0, 50.0), (90.0, 50.0)], masks=none)
    assert leg["landmark"] is None
    assert leg["text"] is None


def test_a_checkpoints_landmark_view_lists_what_it_sees_and_where():
    masks = {**SEE_ALL, "crater_rim": np.zeros(CELLS.shape, bool)}
    view = landmark_view([TEXOLI, RIM], masks, CELLS, (50.0, 50.0))
    assert view == [{"id": "texoli", "title": "Texoli", "heading_deg": 0.0}]
