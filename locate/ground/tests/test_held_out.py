"""No held-out view shares ground with a tuning view: their 24 m north-up squares never overlap."""

from locate.ground.hidden_pile import held_out
from locate.ground.pile import Stop

TUNING = Stop("N_R000_4671_ILT119VRT_S_0486_UNCORM1", 4671, 119, 486, 8143000.0, -285000.0)


def _stop(drive: int, east_m: float, north_m: float) -> Stop:
    return Stop(
        f"N_R000_4700_ILT120VRT_S_{drive:04d}_UNCORM1",
        4700,
        120,
        drive,
        TUNING.x + east_m,
        TUNING.y + north_m,
    )


def test_a_stop_whose_square_overlaps_a_tuning_square_diagonally_is_left_out():
    # 26.33 m apart, but the squares share a 1.089 m by 11.03 m strip.
    diagonal = _stop(198, 22.911, 12.97)

    assert held_out([TUNING, diagonal]) == []


def test_a_stop_whose_square_only_touches_a_tuning_square_is_held_out():
    beside = _stop(232, 24.0, 0.0)  # edge to edge
    far = _stop(264, 30.0, -30.0)

    assert held_out([TUNING, beside, far]) == [beside, far]
