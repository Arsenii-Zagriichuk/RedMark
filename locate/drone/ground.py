"""Straighten a Navcam frame onto the ground, and cut the map window to search.

The ground is taken as flat at the take-off point's height: Ingenuity's height
is measured from there, and over the 50-odd metres a frame sees, the Jezero
floor's relief changes the scale by a few percent, which the fitted
similarity's scale absorbs.
"""

from pathlib import Path

import contourpy
import numpy as np
import rasterio
from rasterio.windows import from_bounds

from locate.drone.fix import GroundView, MapWindow
from locate.drone.label import DroneFrame
from prep.jezero.pack import stretch_to_8bit

# How far from the nadir the view reaches, and the widest ray it keeps: the
# Navcam sees about 66° either side across the frame, and rays further out
# meet the ground too obliquely to resemble the map.
HALF_SIZE_M = 32.0
MAX_RAY_DEG = 75.0
# Each output pixel averages SUPERSAMPLE x SUPERSAMPLE samples, so shrinking
# the 4 cm photo to the map's 25 cm does not alias.
SUPERSAMPLE = 4


def straighten(raw: np.ndarray, frame: DroneFrame, resolution: float) -> GroundView:
    """`raw` (lines x samples) as a north-up view of the ground under the drone."""
    size = round(2 * HALF_SIZE_M / resolution)
    fine = resolution / SUPERSAMPLE
    # Sample centres, metres east and north of the nadir; rows run north to south.
    offsets = (np.arange(size * SUPERSAMPLE) + 0.5) * fine - HALF_SIZE_M
    east, north = np.meshgrid(offsets, -offsets)
    height = -frame.camera_ned[2]
    ground_ned = np.stack([north.ravel(), east.ravel(), np.full(east.size, height)], axis=1)
    # Rows of ground_ned are camera-to-ground rays; turned into the body frame.
    rays = ground_ned @ frame.body_to_ned
    x, y = frame.camera.project(rays + frame.camera.c)

    optical = frame.camera.o / np.linalg.norm(frame.camera.o)
    ray_cos = rays @ optical / np.linalg.norm(rays, axis=1)
    lines, samples = raw.shape
    seen = (x >= 0) & (x <= samples - 1) & (y >= 0) & (y <= lines - 1)
    seen &= ray_cos >= np.cos(np.radians(MAX_RAY_DEG))
    values = np.where(seen, _bilinear(raw.astype(np.float64), x, y), np.nan)
    # A pixel is valid only if all its samples saw the ground (NaN otherwise).
    mean = values.reshape(size, SUPERSAMPLE, size, SUPERSAMPLE).mean(axis=(1, 3))
    valid = np.isfinite(mean)
    if not valid.any():
        raise ValueError(f"{frame.file_stem}: no ground in view")
    image = np.zeros((size, size), dtype=np.uint8)
    image[valid] = stretch_to_8bit(mean[valid])

    forward = frame.body_to_ned[:, 0]
    return GroundView(
        image=image,
        valid=valid,
        resolution=resolution,
        nadir_px=np.array([size / 2 - 0.5, size / 2 - 0.5]),
        heading_deg=float(np.degrees(np.arctan2(forward[1], forward[0])) % 360.0),
        outline_px=_outline(valid),
    )


def _bilinear(image: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    x = np.clip(np.nan_to_num(x), 0, image.shape[1] - 1.000001)
    y = np.clip(np.nan_to_num(y), 0, image.shape[0] - 1.000001)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = x - x0, y - y0
    return (
        image[y0, x0] * (1 - fx) * (1 - fy)
        + image[y0, x0 + 1] * fx * (1 - fy)
        + image[y0 + 1, x0] * (1 - fx) * fy
        + image[y0 + 1, x0 + 1] * fx * fy
    )


def _outline(valid: np.ndarray) -> np.ndarray:
    """The edge of what the photo saw, as (x, y) pixels: the longest contour."""
    # Padded with a ring of False, so a footprint touching the view's edge
    # still gives one closed line; the pad shifts pixels by one.
    padded = np.pad(valid, 1).astype(np.float64)
    lines = contourpy.contour_generator(z=padded).lines(0.5)
    return max(lines, key=len) - 1 if lines else np.empty((0, 2))


def read_map_window(crop: Path, centre: tuple[float, float], half_size_m: float) -> MapWindow:
    """The square of the photo map around `centre`, snapped to the crop's pixels."""
    x, y = centre
    with rasterio.open(crop) as src:
        window = (
            from_bounds(
                x - half_size_m,
                y - half_size_m,
                x + half_size_m,
                y + half_size_m,
                transform=src.transform,
            )
            .round_offsets()
            .round_lengths()
        )
        data = src.read(1, window=window, boundless=True, fill_value=src.nodata or 0)
        transform = src.window_transform(window)
        nodata = src.nodata
    seen = data != nodata if nodata is not None else np.ones(data.shape, dtype=bool)
    image = np.zeros(data.shape, dtype=np.uint8)
    if seen.any():
        image[seen] = stretch_to_8bit(data[seen])
    return MapWindow(image=image, min_x=transform.c, max_y=transform.f, resolution=transform.a)
