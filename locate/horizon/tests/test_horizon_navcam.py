"""Pixel headings from a Navcam camera model. Expected values are worked by
hand, or are JPL's own numbers from the image label."""

import numpy as np
import pytest

from locate.horizon.navcam import CameraModel, pixel_headings

LEVEL = (1.0, 0.0, 0.0, 0.0)  # rover frame lined up with the site frame
TURNED_EAST = (np.cos(np.pi / 4), 0.0, 0.0, np.sin(np.pi / 4))  # 90° about +Z (down)


def worked_camera() -> CameraModel:
    """Looks north and level from the origin; focal length 1000 px; optical
    centre at column 512, row 256. Site frame: +X north, +Y east, +Z down."""
    a = np.array([1.0, 0.0, 0.0])
    return CameraModel(
        c=np.zeros(3),
        a=a,
        h=1000.0 * np.array([0.0, 1.0, 0.0]) + 512.0 * a,
        v=1000.0 * np.array([0.0, 0.0, 1.0]) + 256.0 * a,
    )


def test_the_optical_centre_looks_along_the_axis():
    azimuth, elevation = pixel_headings(worked_camera(), LEVEL, np.array([512.0]), [256.0])
    assert (azimuth[0], elevation[0]) == pytest.approx((0.0, 0.0), abs=1e-9)


def test_columns_to_the_right_turn_east_and_rows_up_rise():
    # 1000 * tan(10°) = 176.33 px right; 1000 * tan(5°) = 87.49 px up.
    azimuth, elevation = pixel_headings(
        worked_camera(), LEVEL, np.array([512.0 + 176.327, 512.0]), np.array([256.0, 256 - 87.489])
    )
    assert azimuth == pytest.approx([10.0, 0.0], abs=1e-3)
    assert elevation == pytest.approx([0.0, 5.0], abs=1e-3)


def test_the_rover_attitude_turns_the_camera_into_the_site_frame():
    # Rover turned to face east: the north-looking camera now looks east; a
    # pixel 10° to its left looks 80°.
    azimuth, elevation = pixel_headings(
        worked_camera(), TURNED_EAST, np.array([512.0, 512.0 - 176.327]), np.array([256.0, 256.0])
    )
    assert azimuth == pytest.approx([90.0, 80.0], abs=1e-3)
    assert elevation == pytest.approx([0.0, 0.0], abs=1e-3)


def test_a_real_frame_points_where_its_label_says():
    # NRB_721967191ILT_S0981520NCAM00266M1 (sol 3655): camera model and rover
    # attitude from the label; SITE_DERIVED_GEOMETRY_PARMS gives the camera
    # pointing, the look of the 1024 x 1024 detector's centre pixel, as
    # azimuth 274.965°, elevation -4.96324°.
    camera = CameraModel(
        c=np.array([0.620686, 0.715171, -1.91284]),
        a=np.array([0.177183, 0.95513, 0.23731]),
        h=np.array([-1109.28, 710.673, 113.624]),
        v=np.array([31.5501, 210.959, 1307.87]),
    )
    quaternion = (0.15206, 0.126541, 0.0674722, -0.977912)
    azimuth, elevation = pixel_headings(camera, quaternion, [511.5], [511.5])
    assert azimuth[0] == pytest.approx(274.965, abs=0.01)
    assert elevation[0] == pytest.approx(-4.96324, abs=0.01)
