from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class TiePointFit:
    position: tuple[float, float]
    heading_deg: float
    residual_m: float
    transform: np.ndarray

    def to_map(self, photo_px: np.ndarray) -> np.ndarray:
        return _project(self.transform, _points(photo_px))


def fit_tie_points(
    photo_px: np.ndarray,
    map_xy: np.ndarray,
    reference_px: tuple[float, float],
    heading_deg: float,
) -> TiePointFit:
    photo, positions = _points(photo_px), _points(map_xy)
    if photo.shape != positions.shape or len(photo) < 4:
        raise ValueError("at least four matching point pairs are required")
    reference = _points([reference_px])[0]
    if not np.isfinite(heading_deg):
        raise ValueError("heading must be finite")
    source, source_frame = _normalise(photo)
    target, target_frame = _normalise(positions)
    x, y = source.T
    east, north = target.T
    zeros, ones = np.zeros(len(photo)), np.ones(len(photo))
    design = np.empty((2 * len(photo), 9))
    design[::2] = np.column_stack([-x, -y, -ones, zeros, zeros, zeros, east * x, east * y, east])
    design[1::2] = np.column_stack(
        [zeros, zeros, zeros, -x, -y, -ones, north * x, north * y, north]
    )
    if np.linalg.matrix_rank(design) < 8:
        raise ValueError("tie points must span an area in both images")
    _, _, vectors = np.linalg.svd(design, full_matrices=True)
    normalised = vectors[-1].reshape(3, 3)
    if np.linalg.matrix_rank(normalised) < 3:
        raise ValueError("tie points do not define an invertible map transform")
    transform = np.linalg.solve(target_frame, normalised @ source_frame)
    transform /= np.linalg.norm(transform[2])
    position = _project(transform, reference[None])[0]
    denominator = transform[2] @ [*reference, 1]
    jacobian = (transform[:2, :2] - np.outer(position, transform[2, :2])) / denominator
    angle = np.radians(heading_deg)
    forward = jacobian @ [np.sin(angle), -np.cos(angle)]
    heading = float(np.degrees(np.arctan2(forward[0], forward[1])) % 360)
    residual = np.linalg.norm(_project(transform, photo) - positions, axis=1)
    return TiePointFit(
        position=tuple(float(v) for v in position),
        heading_deg=0.0 if heading >= 360 else heading,
        residual_m=float(np.sqrt(np.mean(residual**2))),
        transform=transform,
    )


def _points(values: np.ndarray) -> np.ndarray:
    points = np.asarray(values, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 2 or not np.isfinite(points).all():
        raise ValueError("points must be finite (x, y) pairs")
    return points


def _normalise(points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    centre = points.mean(axis=0)
    spread = np.sqrt(np.mean(np.sum((points - centre) ** 2, axis=1)))
    if spread <= np.finfo(float).eps:
        raise ValueError("tie points must span an area in both images")
    scale = np.sqrt(2) / spread
    frame = np.array([[scale, 0, -scale * centre[0]], [0, scale, -scale * centre[1]], [0, 0, 1]])
    return (points - centre) * scale, frame


def _project(transform: np.ndarray, points: np.ndarray) -> np.ndarray:
    homogeneous = np.column_stack([points, np.ones(len(points))]) @ transform.T
    denominators = homogeneous[:, 2]
    if np.any(np.abs(denominators) < 1e-12) or (
        np.any(denominators < 0) and np.any(denominators > 0)
    ):
        raise ValueError("the fitted map transform crosses the horizon")
    return homogeneous[:, :2] / homogeneous[:, 2, None]
