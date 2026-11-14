"""The hidden pile: which stops may go in it, and which frames make a stop's ring."""

from locate.horizon.hidden_pile import Pointing, horizon_ring, is_tuning_site


def test_the_stretch_round_the_tuning_stop_is_tuning_pile():
    # Sol 3655's ring (site 98) was tuned on; sites 96 to 100 stay on its side.
    assert [is_tuning_site(site) for site in (95, 96, 98, 100, 101)] == [
        False,
        True,
        True,
        True,
        False,
    ]


def _frames(sequence, azimuths, elevation=0.0):
    return [
        Pointing(f"{sequence}-{i}", sequence, azimuth, elevation)
        for i, azimuth in enumerate(azimuths)
    ]


def test_twelve_level_frames_round_the_stop_are_its_ring():
    ring = _frames("NCAM00266", range(0, 360, 30), elevation=2.0)

    assert horizon_ring(ring) == ring


def test_seven_frames_30_degrees_apart_are_a_ring():
    # 6 × 30° + 45° = 225° of skyline, over the 200° a ring needs.
    pan = _frames("NCAM00297", range(280, 490, 30), elevation=-17.0)

    assert horizon_ring(pan) == pan


def test_four_frames_side_by_side_are_not_a_ring():
    # 4 × 45° = 180° of skyline, under 200°.
    pan = _frames("NCAM00297", range(0, 180, 45))

    assert horizon_ring(pan) == []


def test_frames_all_looking_one_way_are_not_a_ring():
    sky_movie = _frames("NCAM00575", [102.7] * 15, elevation=6.4)

    assert horizon_ring(sky_movie) == []


def test_only_the_tier_that_sees_the_horizon_is_kept():
    level = _frames("NCAM00581", range(0, 360, 40), elevation=-5.0)
    ground = _frames("NCAM00581", range(20, 380, 40), elevation=-45.0)

    assert horizon_ring(level + ground) == level


def test_the_ring_comes_from_the_one_sequence_that_goes_round():
    ring = _frames("NCAM00578", range(0, 360, 30))
    sky_movie = _frames("NCAM00575", [10.0] * 15)

    assert horizon_ring(sky_movie + ring) == ring
