"""The ground fix takes its heading from the rover's onboard attitude in a source frame's label."""

import pytest

from locate.ground.mosaic import rover_heading_deg


def _label(quaternion: str) -> str:
    return f"""
GROUP                             = ROVER_COORD_SYSTEM_PARMS
  COORDINATE_SYSTEM_NAME          = "ROVER_NAV_FRAME"
  ORIGIN_OFFSET_VECTOR            = (37.3903,-112.782,-8.41367)
  ORIGIN_ROTATION_QUATERNION      = {quaternion}
  REFERENCE_COORD_SYSTEM_NAME     = "SITE_FRAME"
END_GROUP                         = ROVER_COORD_SYSTEM_PARMS
"""


def test_a_quarter_turn_about_down_faces_east():
    assert rover_heading_deg(_label("(0.7071068,0.0,0.0,0.7071068)")) == pytest.approx(90.0)


def test_the_sol_3655_stop_faces_where_places_says():
    # Site 98 drive 1520: PLACES gives yaw -163.08°, i.e. heading 196.92°.
    heading = rover_heading_deg(_label("(0.15206,0.126541,0.0674722,\n -0.977912)"))
    assert heading == pytest.approx(196.92, abs=0.05)
