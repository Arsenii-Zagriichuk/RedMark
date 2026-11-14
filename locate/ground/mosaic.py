"""Curiosity's top-down Navcam mosaics (VRT products in the PDS mosaic archive),
turned into overhead views at the photo map's 25 cm.

A VRT mosaic is the Navcam frames of one stop projected straight down onto a
plane fitted to the ground: 4800 x 4800 pixels of 5 mm, 24 m across, centred on
the rover, in its local level frame. Line 0 is the north edge and sample 0 the
west edge, so it is north-up like the map.
"""

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from locate.horizon.navcam import label_number, label_vector

MOSAIC_CELL_M = 0.005
VIEW_CELL_M = 0.25
ROVER_MASK_M = 3.0
"""The rover's own deck, wheels and shadow cover the ground this close to its centre."""
SEEN_SHARE = 0.5
"""A view cell counts when at least this share of its mosaic pixels saw ground."""
MOSAIC_NAME = re.compile(r"^N_[A-Z]\d{3}_(\d{4})_ILT(\d{3})VRT_S_(\d{4})_")


@dataclass(frozen=True)
class OverheadView:
    """North-up, VIEW_CELL_M cells, the rover at the centre. mask is True where
    the cell saw ground and is far enough from the rover to compare with the map."""

    image: np.ndarray
    mask: np.ndarray

    @property
    def size_m(self) -> float:
        return self.image.shape[0] * VIEW_CELL_M


@dataclass(frozen=True)
class Mosaic:
    photo_id: str
    sol: int
    site: int
    drive: int
    pixels: np.ndarray


def overhead_view(pixels: np.ndarray, mosaic_cell_m: float = MOSAIC_CELL_M) -> OverheadView:
    """Average the mosaic into VIEW_CELL_M cells. Zero pixels saw nothing."""
    step = round(VIEW_CELL_M / mosaic_cell_m)
    cells = pixels.shape[0] // step
    pixels = pixels[: cells * step, : cells * step].astype(np.float64)
    seen = (pixels > 0).astype(np.float64)
    seen_share = seen.reshape(cells, step, cells, step).mean(axis=(1, 3))
    total = pixels.reshape(cells, step, cells, step).mean(axis=(1, 3))
    image = np.where(seen_share > 0, total / np.maximum(seen_share, 1e-12), 0.0)

    centre = (np.arange(cells) + 0.5) * VIEW_CELL_M - cells * VIEW_CELL_M / 2
    distance = np.hypot(centre[:, None], centre[None, :])
    mask = (seen_share >= SEEN_SHARE) & (distance > ROVER_MASK_M)
    return OverheadView(image=image, mask=mask)


def read_mosaic(label_path: Path) -> Mosaic:
    """A VRT mosaic from its PDS3 label and the .IMG beside it (16-bit, big-endian)."""
    label = label_path.read_text(errors="ignore")
    name = MOSAIC_NAME.match(label_path.stem)
    if name is None:
        raise ValueError(f"{label_path.name} is not a VRT mosaic")
    if not re.search(r"MAP_PROJECTION_TYPE\s*=\s*\"?VERTICAL\b", label):
        raise ValueError(f"{label_path.name} is not a vertical projection")
    scale = label_number(label, "MAP_SCALE")
    if scale != MOSAIC_CELL_M:
        raise ValueError(f"{label_path.name} has {scale} m pixels, not {MOSAIC_CELL_M}")
    record_bytes = int(label_number(label, "RECORD_BYTES"))
    pointer = re.search(r"\^IMAGE\s*=\s*\(\s*\"[^\"]+\"\s*,\s*(\d+)\s*\)", label)
    if pointer is None:
        raise ValueError(f"{label_path.name} has no image pointer")
    image = label_path.with_suffix(".IMG")
    lines, samples = _image_size(label, image, record_bytes)
    pixels = np.fromfile(
        image,
        dtype=">u2",
        count=lines * samples,
        offset=record_bytes * (int(pointer.group(1)) - 1),
    ).reshape(lines, samples)
    return Mosaic(
        photo_id=label_path.stem,
        sol=int(name.group(1)),
        site=int(name.group(2)),
        drive=int(name.group(3)),
        pixels=pixels,
    )


def _image_size(label: str, image: Path, record_bytes: int) -> tuple[int, int]:
    """(lines, samples) from the label's IMAGE object, or, in labels from about
    sol 4741 on that leave it out, from the VICAR header inside the .IMG."""
    if re.search(r"^\s*OBJECT\s*=\s*IMAGE\s*$", label, re.M):
        return int(label_number(label, "LINES")), int(label_number(label, "LINE_SAMPLES"))
    pointer = re.search(r"\^IMAGE_HEADER\s*=\s*\(\s*\"[^\"]+\"\s*,\s*(\d+)\s*\)", label)
    if pointer is None:
        raise ValueError(f"{image.name}: label has neither an IMAGE object nor an image header")
    with image.open("rb") as f:
        f.seek(record_bytes * (int(pointer.group(1)) - 1))
        vicar = f.read(record_bytes).decode("ascii", errors="ignore")
    if "FORMAT='HALF'" not in vicar or not re.search(r"(?<!B)INTFMT='HIGH'", vicar):
        raise ValueError(f"{image.name} is not 16-bit big-endian")
    size = re.search(r"\bNL=(\d+)\s+NS=(\d+)", vicar)
    if size is None:
        raise ValueError(f"{image.name}: no image size in its VICAR header")
    return int(size.group(1)), int(size.group(2))


def rover_heading_deg(label: str) -> float:
    """The rover's heading from north, from a Navcam frame label's onboard
    attitude (ROVER_NAV_FRAME in the site frame: x north, y east, z down)."""
    group = re.search(r"GROUP\s*=\s*ROVER_COORD_SYSTEM_PARMS\b(.*?)END_GROUP", label, re.S)
    if group is None:
        raise ValueError("ROVER_COORD_SYSTEM_PARMS not in label")
    quaternion = np.asarray(label_vector(group.group(1), "ORIGIN_ROTATION_QUATERNION"))
    s, x, y, z = quaternion / np.linalg.norm(quaternion)
    # The rover's forward axis (its x) in the site frame: the rotation matrix's first column.
    north = 1 - 2 * (y * y + z * z)
    east = 2 * (x * y + s * z)
    return float(np.degrees(np.arctan2(east, north)) % 360.0)
