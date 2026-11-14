"""Seam: the CAHVORE camera model that straightens Ingenuity's fisheye.

Expected pixels come from worked examples of an ideal fisheye: a camera
looking down +z with focal length 100 px and centre (320, 240). An
equidistant fisheye (linearity 0) puts a ray at angle theta from the axis
f * theta pixels from the centre; a perspective one (linearity 1) puts it
f * tan(theta) away.
"""

import math

import numpy as np
import pytest

from locate.drone.camera import Cahvore


def _ideal_camera(linearity: float, radial: tuple[float, float, float] = (0, 0, 0)) -> Cahvore:
    axis = np.array([0.0, 0.0, 1.0])
    return Cahvore(
        c=np.zeros(3),
        a=axis,
        h=100 * np.array([1.0, 0, 0]) + 320 * axis,
        v=100 * np.array([0, 1.0, 0]) + 240 * axis,
        o=axis,
        r=np.array(radial),
        linearity=linearity,
    )


def test_point_on_the_axis_lands_on_the_image_centre():
    x, y = _ideal_camera(0).project(np.array([[0.0, 0.0, 5.0]]))
    assert x[0] == pytest.approx(320)
    assert y[0] == pytest.approx(240)


def test_fisheye_puts_a_45_degree_ray_f_theta_from_the_centre():
    x, y = _ideal_camera(0).project(np.array([[1.0, 0.0, 1.0], [0.0, -2.0, 2.0]]))
    assert x == pytest.approx([320 + 100 * math.pi / 4, 320])
    assert y == pytest.approx([240, 240 - 100 * math.pi / 4])


def test_perspective_linearity_puts_a_45_degree_ray_f_tan_theta_from_the_centre():
    x, _ = _ideal_camera(1).project(np.array([[1.0, 0.0, 1.0]]))
    assert x[0] == pytest.approx(420)


def test_radial_terms_stretch_the_distance_from_the_centre():
    # chi = pi/4; distorted chi = chi * (1 + 0.1 * chi^2) = 0.8338455...
    x, _ = _ideal_camera(0, radial=(0, 0.1, 0)).project(np.array([[1.0, 0.0, 1.0]]))
    assert x[0] == pytest.approx(320 + 83.38455, abs=1e-4)


def test_points_behind_the_camera_are_not_projected():
    x, y = _ideal_camera(0).project(np.array([[0.0, 0.0, -1.0]]))
    assert math.isnan(x[0]) and math.isnan(y[0])
