"""Curiosity Navcam frames: the image, and which way each pixel looks.

A frame's PDS3 label carries its CAHVOR camera model in the rover frame
(+X forward, +Y right, +Z down) and the rover's attitude as a quaternion
from the rover frame to the site frame (+X north, +Y east, +Z down, level).
Together they give every pixel's heading from north and its elevation above
the level horizon. The R (radial distortion) part of CAHVOR is left out: for
Navcam its coefficients are about 0.002, which moves a ray far less than the
grid's 0.25° step. The site frame's north is map north, since the site map is
equirectangular.
"""

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class CameraModel:
    """CAHV: centre (m), axis, and the horizontal and vertical image vectors (px)."""

    c: np.ndarray
    a: np.ndarray
    h: np.ndarray
    v: np.ndarray


@dataclass(frozen=True)
class NavcamFrame:
    photo_id: str
    image: np.ndarray
    """Pixel values, row 0 at the top."""
    camera: CameraModel
    rover_quaternion: tuple[float, float, float, float]
    """Rover frame to site frame, (s, v1, v2, v3)."""
    heading_deg: float
    """The camera pointing from north, as the label's site-frame geometry gives it."""
    site: int
    drive: int

    def camera_offset_m(self) -> tuple[float, float]:
        """The camera's (east, north) offset from the rover's origin, in metres."""
        north, east, _ = _rotation(self.rover_quaternion) @ self.camera.c
        return float(east), float(north)


def pixel_headings(
    camera: CameraModel,
    rover_quaternion: tuple[float, float, float, float],
    cols: np.ndarray,
    rows: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """The heading from map north (0 to 360°) and elevation (°) each pixel looks along."""
    cols = np.asarray(cols, np.float64)[:, None]
    rows = np.asarray(rows, np.float64)[:, None]
    # A pixel's ray lies in the plane (P - C)·(H - x A) = 0 and in (P - C)·(V - y A) = 0.
    ray = np.cross(camera.h - cols * camera.a, camera.v - rows * camera.a)
    ray *= np.sign(ray @ camera.a)[:, None]
    north, east, down = (_rotation(rover_quaternion) @ ray.T) / np.linalg.norm(ray, axis=1)
    return np.degrees(np.arctan2(east, north)) % 360.0, np.degrees(np.arcsin(-down))


def read_frame(label_path: Path) -> NavcamFrame:
    """A Navcam RDR frame (16-bit, one band) from its .LBL and the .IMG beside it."""
    label = label_path.read_text()
    rover = _group(label, "ROVER_COORD_SYSTEM_PARMS")
    site, drive = (int(v) for v in label_vector(rover, "COORDINATE_SYSTEM_INDEX")[:2])
    image_object = re.search(r"^OBJECT\s*=\s*IMAGE\s*$(.*?)^END_OBJECT", label, re.S | re.M)
    image_object = image_object.group(1)
    lines = int(label_number(image_object, "LINES"))
    samples = int(label_number(image_object, "LINE_SAMPLES"))
    if "MSB_INTEGER" not in image_object or label_number(image_object, "BANDS") != 1:
        raise ValueError(f"{label_path.name}: expected one band of 16-bit MSB integers")
    record = int(re.search(r"\^IMAGE\s*=\s*\([^,]+,\s*(\d+)\)", label).group(1))
    raw = np.fromfile(
        label_path.with_suffix(".IMG"),
        dtype=">i2",
        offset=(record - 1) * int(label_number(label, "RECORD_BYTES")),
        count=lines * samples,
    )
    model = _group(label, "GEOMETRIC_CAMERA_MODEL_PARMS")
    if '"ROVER_NAV_FRAME"' not in model:
        raise ValueError(f"{label_path.name}: camera model is not in the rover frame")
    c, a, h, v = (np.array(label_vector(model, f"MODEL_COMPONENT_{i}")) for i in range(1, 5))
    site_geometry = _group(label, "SITE_DERIVED_GEOMETRY_PARMS")
    return NavcamFrame(
        # Anchored: SOURCE_PRODUCT_ID and INPUT_PRODUCT_ID name the raw frame.
        photo_id=re.search(r'^PRODUCT_ID\s*=\s*"([^"]+)"', label, re.M).group(1),
        image=raw.reshape(lines, samples).astype(np.float32),
        camera=CameraModel(c, a, h, v),
        rover_quaternion=tuple(label_vector(rover, "ORIGIN_ROTATION_QUATERNION")),
        heading_deg=label_number(site_geometry, "INSTRUMENT_AZIMUTH"),
        site=site,
        drive=drive,
    )


def _rotation(quaternion) -> np.ndarray:
    s, x, y, z = np.asarray(quaternion, np.float64) / np.linalg.norm(quaternion)
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - s * z), 2 * (x * z + s * y)],
            [2 * (x * y + s * z), 1 - 2 * (x * x + z * z), 2 * (y * z - s * x)],
            [2 * (x * z - s * y), 2 * (y * z + s * x), 1 - 2 * (x * x + y * y)],
        ]
    )


def _group(label: str, name: str) -> str:
    match = re.search(rf"GROUP\s*=\s*{name}\b(.*?)END_GROUP\s*=\s*{name}\b", label, re.S)
    if match is None:
        raise ValueError(f"{name} not in label")
    return match.group(1)


def label_number(text: str, key: str) -> float:
    """The first number given for key in a PDS3 label."""
    match = re.search(rf"^\s*{key}\s*=\s*\(?\s*(-?[\d.eE+-]+)", text, re.M)
    if match is None:
        raise ValueError(f"{key} not in label")
    return float(match.group(1))


def label_vector(text: str, key: str) -> list[float]:
    """The numbers in parentheses given for key in a PDS3 label."""
    match = re.search(rf"^\s*{key}\s*=\s*\(([^)]*)\)", text, re.M | re.S)
    if match is None:
        raise ValueError(f"{key} not in label")
    return [float(value) for value in match.group(1).split(",")]
