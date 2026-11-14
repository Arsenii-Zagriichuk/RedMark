import numpy as np
import pytest

from route.tie_points import fit_tie_points


@pytest.mark.parametrize(
    ("heading", "expected_heading"), [(0, 90), (90, 180), (180, 270), (270, 0)]
)
def test_four_known_pairs_give_the_known_position_and_heading_in_ground_metres(
    heading, expected_heading
):
    photo = np.array([[10, 10], [110, 10], [110, 90], [10, 90]])
    positions = np.array(
        [
            [4354020, 1092220],
            [4354020, 1092020],
            [4353860, 1092020],
            [4353860, 1092220],
        ]
    )

    fit = fit_tie_points(photo, positions, reference_px=(60, 50), heading_deg=heading)

    assert fit.position == pytest.approx((4353940, 1092120), abs=1e-6)
    difference = abs(fit.heading_deg - expected_heading)
    assert min(difference, 360 - difference) < 1e-6
    assert fit.residual_m == pytest.approx(0, abs=1e-6)


def test_pairs_whose_transform_crosses_a_horizon_are_not_a_ground_map():
    photo = [[0, 0], [100, 0], [100, 100], [0, 100]]
    positions = [[0, 100], [-200 / 3, -200 / 3], [-200 / 3, 0], [0, 0]]

    with pytest.raises(ValueError, match="horizon"):
        fit_tie_points(photo, positions, reference_px=(50, 50), heading_deg=0)


def test_a_projective_photo_uses_the_local_heading_at_its_reference_pixel():
    photo = [[0, 0], [100, 0], [100, 100], [0, 100]]
    positions = [
        [4354000, 1092300],
        [4354100, 1092300],
        [4354050, 1092200],
        [4354000, 1092200],
    ]

    fit = fit_tie_points(photo, positions, reference_px=(50, 50), heading_deg=0)

    assert fit.position == pytest.approx((4354033.333333, 1092233.333333), abs=1e-6)
    assert fit.heading_deg == pytest.approx(14.036243, abs=1e-6)


@pytest.mark.parametrize(
    ("photo", "positions", "message"),
    [
        ([[0, 0], [1, 0], [1, 1]], [[0, 0], [1, 0], [1, 1]], "four"),
        ([[0, 0], [1, 0], [2, 0], [3, 0]], [[0, 0], [1, 0], [2, 0], [3, 0]], "area"),
        ([[0, 0], [1, 0], [1, 1], [0, np.nan]], [[0, 0]] * 4, "finite"),
    ],
)
def test_pairs_that_cannot_define_a_ground_map_are_refused(photo, positions, message):
    with pytest.raises(ValueError, match=message):
        fit_tie_points(photo, positions, reference_px=(0.5, 0.5), heading_deg=0)
