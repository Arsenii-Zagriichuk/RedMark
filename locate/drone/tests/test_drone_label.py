"""Seam: a Navcam frame's onboard pose, read from its PDS label.

The independent check is NASA's own flight path for flight 10, whose points
are spread evenly in time from the flight's SCLK_START to SCLK_END: the
onboard position of a frame must sit on that path at the frame's clock time.
"""

import json
from pathlib import Path

import numpy as np
import pytest

from locate.drone.label import onboard_position, read_drone_frame, takeoff_position
from prep.jezero.site_frame import to_site_frame

# Public NASA excerpts committed with the Jezero pack (see their README).
PREP_FIXTURES = Path(__file__).parents[3] / "prep" / "tests" / "fixtures"
LABEL = PREP_FIXTURES / "HNM_0152_0680432615_348FDR_N0100001HELI03026_0000LUJ05.xml"


def _nasa_path_at(flight: int, sclk: float) -> np.ndarray:
    features = json.loads((PREP_FIXTURES / "m20_heli_flight_path.json").read_text())["features"]
    feature = next(f for f in features if f["properties"]["Flight"] == flight)
    start, end = feature["properties"]["SCLK_START"], feature["properties"]["SCLK_END"]
    points = [to_site_frame(lon, lat) for lon, lat, *_ in feature["geometry"]["coordinates"]]
    index = round((sclk - start) / (end - start) * (len(points) - 1))
    return np.array(points[index])


def test_frame_reads_flight_and_clock():
    frame = read_drone_frame(LABEL.read_text())
    assert frame.flight == 10
    assert frame.file_stem == "HNM_0152_0680432615_348FDR_N0100001HELI03026_0000LUJ05"
    assert frame.sclk == pytest.approx(680432615.348, abs=0.01)


def test_takeoff_is_the_previous_flights_landing_waypoint():
    waypoints = json.loads((PREP_FIXTURES / "m20_heli_waypoints.json").read_text())
    # NASA's waypoint for flight 9 (where it landed): Easting and Northing.
    assert takeoff_position(waypoints, flight=10) == pytest.approx((4354187.788, 1092319.693))


def test_onboard_position_lies_on_nasas_flight_path_at_that_time():
    frame = read_drone_frame(LABEL.read_text())
    waypoints = json.loads((PREP_FIXTURES / "m20_heli_waypoints.json").read_text())
    x, y = onboard_position(frame, takeoff_position(waypoints, flight=10))
    distance = np.hypot(*(np.array([x, y]) - _nasa_path_at(10, frame.sclk)))
    assert distance < 3.0


def test_camera_looks_down_from_cruise_height():
    frame = read_drone_frame(LABEL.read_text())
    axis_ned = frame.body_to_ned @ (frame.camera.a / np.linalg.norm(frame.camera.a))
    assert axis_ned[2] > np.cos(np.radians(20))  # within 20° of straight down
    assert -frame.camera_ned[2] == pytest.approx(12.2, abs=0.5)  # flight 10 cruised at 12 m
