"""Pixel headings from a Navcam camera model. Expected values are worked by
hand, or are JPL's own numbers from the image label."""

import numpy as np
import pytest

from locate.horizon.navcam import CameraModel, pixel_headings, read_frame

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


MADE_UP_LABEL = """PDS_VERSION_ID = PDS3
RECORD_BYTES = 8
^IMAGE = ("FRAME.IMG",3)
SOURCE_PRODUCT_ID = "RAW_EDR"
PRODUCT_ID = "FRAME_ILT"
GROUP = GEOMETRIC_CAMERA_MODEL_PARMS
  MODEL_COMPONENT_1 = (0.5,0.25,-2.0)
  MODEL_COMPONENT_2 = (1.0,0.0,0.0)
  MODEL_COMPONENT_3 = (1.0,1000.0,0.0)
  MODEL_COMPONENT_4 = (1.5,0.0,1000.0)
  REFERENCE_COORD_SYSTEM_NAME = "ROVER_NAV_FRAME"
END_GROUP = GEOMETRIC_CAMERA_MODEL_PARMS
GROUP = ROVER_COORD_SYSTEM_PARMS
  COORDINATE_SYSTEM_INDEX = (98,1520,6,0)
  ORIGIN_ROTATION_QUATERNION = (0.7071068,0.0,0.0,
                                0.7071068)
END_GROUP = ROVER_COORD_SYSTEM_PARMS
GROUP = INITIAL_STATE_PARMS
  ORIGIN_ROTATION_QUATERNION = (1.0,0.0,0.0,0.0)
END_GROUP = INITIAL_STATE_PARMS
GROUP = SITE_DERIVED_GEOMETRY_PARMS
  INSTRUMENT_AZIMUTH = 92.5 <deg>
END_GROUP = SITE_DERIVED_GEOMETRY_PARMS
GROUP = DERIVED_IMAGE_PARMS
  MSL:INPUT_PRODUCT_ID = "RAW_EDR"
END_GROUP = DERIVED_IMAGE_PARMS
OBJECT = IMAGE
  LINES = 2
  LINE_SAMPLES = 3
  SAMPLE_TYPE = MSB_INTEGER
  SAMPLE_BITS = 16
  BANDS = 1
END_OBJECT = IMAGE
END
"""


def test_a_frame_is_read_from_its_own_label_fields_and_image_records(tmp_path):
    # Two 8-byte records come before the image (^IMAGE points at record 3);
    # the pixels are 1..6 as big-endian 16-bit integers. The rover is turned
    # 90° to the east, so the camera 0.5 m forward and 0.25 m right sits
    # 0.5 m east and 0.25 m south of the rover.
    (tmp_path / "FRAME.LBL").write_text(MADE_UP_LABEL)
    pixels = np.arange(1, 7, dtype=">i2").tobytes()
    (tmp_path / "FRAME.IMG").write_bytes(b"\xff" * 16 + pixels)
    frame = read_frame(tmp_path / "FRAME.LBL")
    assert frame.photo_id == "FRAME_ILT"
    assert frame.image.tolist() == [[1, 2, 3], [4, 5, 6]]
    assert (frame.site, frame.drive, frame.heading_deg) == (98, 1520, 92.5)
    assert frame.camera_offset_m() == pytest.approx((0.5, -0.25))


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
