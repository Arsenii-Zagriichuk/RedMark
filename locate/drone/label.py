"""A Navcam frame's camera and onboard pose, read from its PDS4 label.

Frames, from the label and checked against NASA's flight path:
- the camera model is in the drone's body frame (HELI_M_FRAME);
- the body frame's quaternion and offset are relative to the flight's
  take-off frame (HELI_G_FRAME), whose axes follow the drone's heading at
  take-off and whose z points down;
- the take-off frame's quaternion turns its axes into north, east, down.
The take-off point itself is the previous flight's landing waypoint, which
NASA publishes in map metres. The onboard pose drifts (Ingenuity's own track
can be about 20 m off), so it only centres the search; the match fixes it.
"""

from dataclasses import dataclass

import numpy as np

from locate.drone.camera import Cahvore
from prep.jezero.frames import first_label_match, frame_block, read_label


@dataclass(frozen=True)
class DroneFrame:
    file_stem: str
    flight: int
    sclk: float  # spacecraft clock at the exposure, seconds
    camera: Cahvore  # in the body frame
    body_to_ned: np.ndarray  # 3x3: body-frame vectors to north, east, down
    camera_ned: np.ndarray  # camera centre from the take-off point, metres north, east, down


def _vector(block: str, tag: str, suffix: str) -> np.ndarray:
    inner = first_label_match(rf"<geom:{tag}>(.*?)</geom:{tag}>", block)
    return np.array(
        [float(first_label_match(rf"<geom:{c}{suffix}[^>]*>([^<]+)<", inner)) for c in "xyz"]
    )


def _rotation(block: str) -> np.ndarray:
    """The block's Quaternion_Plus_Direction as a matrix from its frame to its parent."""
    inner = first_label_match(
        r"<geom:Quaternion_Plus_Direction>(.*?)</geom:Quaternion_Plus_Direction>", block
    )
    w, x, y, z = (
        float(first_label_match(rf"<geom:{t}>([^<]+)<", inner))
        for t in ("qcos", "qsin1", "qsin2", "qsin3")
    )
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
            [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
            [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
        ]
    )


def read_drone_frame(xml: str) -> DroneFrame:
    model = first_label_match(r"<geom:CAHVORE_Model>(.*?)</geom:CAHVORE_Model>", xml)
    if np.any(_vector_terms(model, "Entrance_Terms")):
        raise ValueError("CAHVORE entrance terms are not zero; the closed-form projection is wrong")
    camera = Cahvore(
        c=_vector(model, "Vector_Center", "_position"),
        a=_vector(model, "Vector_Axis", "_unit"),
        h=_vector(model, "Vector_Horizontal", "_pixel"),
        v=_vector(model, "Vector_Vertical", "_pixel"),
        o=_vector(model, "Vector_Optical", "_unit"),
        r=_vector_terms(model, "Radial_Terms"),
        linearity=float(first_label_match(r"<geom:cahvore_model_parameter>([^<]+)<", model)),
    )
    navcam = read_label(xml)
    takeoff = frame_block(xml, f"HELI_G_FRAME_{navcam.flight}")
    body = frame_block(xml, rf"HELI_M_FRAME_{navcam.flight}_\d+")
    takeoff_to_ned = _rotation(takeoff)
    body_to_ned = takeoff_to_ned @ _rotation(body)
    body_offset = _vector(body, "Vector_Origin_Offset", "_position")
    return DroneFrame(
        file_stem=navcam.file_stem,
        flight=navcam.flight,
        sclk=navcam.sclk,
        camera=camera,
        body_to_ned=body_to_ned,
        camera_ned=takeoff_to_ned @ body_offset + body_to_ned @ camera.c,
    )


def _vector_terms(model: str, tag: str) -> np.ndarray:
    inner = first_label_match(rf"<geom:{tag}>(.*?)</geom:{tag}>", model)
    return np.array(
        [float(first_label_match(rf"<geom:{c}>([^<]+)<", inner)) for c in ("c0", "c1", "c2")]
    )


def takeoff_position(waypoints: dict, flight: int) -> tuple[float, float]:
    """Map metres of `flight`'s take-off: where flight - 1 landed, from NASA's waypoints."""
    for feature in waypoints["features"]:
        p = feature["properties"]
        if int(p["Flight"]) == flight - 1:
            return float(p["Easting"]), float(p["Northing"])
    raise ValueError(f"no waypoint for flight {flight - 1}, where flight {flight} took off")


def onboard_position(frame: DroneFrame, takeoff: tuple[float, float]) -> tuple[float, float]:
    """The drone's onboard position: map metres of the camera's nadir by its own reckoning."""
    north, east, _ = frame.camera_ned
    return takeoff[0] + east, takeoff[1] + north
