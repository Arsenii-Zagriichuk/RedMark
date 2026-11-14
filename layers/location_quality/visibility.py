"""Which map cells can see a landmark, from the terrain (layer 5, P3-05).

A cell sees a point when the straight line from an eye observer_height_m above
the cell's ground to the point clears all terrain in between, on the Mars
sphere (the same curvature as the horizon renderer). The landmark's own body,
the ground within body_radius_m of the point, never blocks the view of it: a
butte's own near edge would otherwise hide its summit from anyone below it,
although they are looking right at the butte.

Line of sight is the same in both directions, so instead of one ray per cell
(16 million at 1 m) the rays are cast once from the point, fanned across the
cells: along each ray the running maximum of the elevation angle seen from the
point is the line a cell's eye must rise above. Rays are close enough that
neighbouring rays are under half a cell apart at the far edge of the cells,
and each cell reads the ray nearest to it.
"""

from dataclasses import dataclass

import numpy as np

from locate.horizon.grid import ray_distances
from locate.horizon.render import MARS_RADIUS_M, Terrain

# Away from the cells, ray samples thin out so that each gap stays about this
# wide as seen from the nearest cell; the horizon grid uses the same step.
FAR_STEP_DEG = 0.25
# Rays are spaced so the gap between neighbours at the far edge of the cells
# is at most this share of a cell.
RAY_GAP_CELLS = 0.7
RAYS_PER_CHUNK = 256


@dataclass(frozen=True)
class Cells:
    """A north-up grid of map cells: row 0 at the top edge, column 0 at the left."""

    left: float
    top: float
    res: float
    shape: tuple[int, int]
    """(rows, columns)."""

    @property
    def right(self) -> float:
        return self.left + self.shape[1] * self.res

    @property
    def bottom(self) -> float:
        return self.top - self.shape[0] * self.res

    def centres(self) -> tuple[np.ndarray, np.ndarray]:
        """Cell-centre x of each column and y of each row."""
        xs = self.left + (np.arange(self.shape[1]) + 0.5) * self.res
        ys = self.top - (np.arange(self.shape[0]) + 0.5) * self.res
        return xs, ys

    def distance_to(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        """Distance from each point to the nearest edge of the cells (0 inside)."""
        dx = np.maximum(np.maximum(self.left - x, x - self.right), 0.0)
        dy = np.maximum(np.maximum(self.bottom - y, y - self.top), 0.0)
        return np.hypot(dx, dy)


def sees_point(
    terrain: Terrain,
    point: tuple[float, float],
    cells: Cells,
    *,
    body_radius_m: float,
    observer_height_m: float,
) -> np.ndarray:
    """True for each cell whose eye sees the point (the terrain top there).

    The point must lie outside the cells. Cells with no ground height are False.
    """
    px, py = point
    if cells.distance_to(np.array(px), np.array(py)) <= 0:
        raise ValueError("the point must lie outside the cells")
    point_ground = terrain.height(
        np.array([px]), np.array([py]), cells.distance_to(np.array([px]), np.array([py]))
    )[0]
    if np.isnan(point_ground):
        raise ValueError(f"no terrain height at the point {point}")
    point_radius = MARS_RADIUS_M + float(point_ground)

    corners_x = np.array([cells.left, cells.right, cells.left, cells.right])
    corners_y = np.array([cells.top, cells.top, cells.bottom, cells.bottom])
    centre_az = np.arctan2((cells.left + cells.right) / 2 - px, (cells.top + cells.bottom) / 2 - py)
    corner_az = _wrap(np.arctan2(corners_x - px, corners_y - py) - centre_az)
    nearest = float(cells.distance_to(np.array(px), np.array(py)))
    farthest = float(np.hypot(corners_x - px, corners_y - py).max())

    # Fine samples, one cell apart, from where the cells could start to their far edge.
    fine = np.arange(nearest - cells.res, farthest + cells.res, cells.res)
    fine = fine[fine > 0]
    # Coarse samples from the point's body out to the fine ones, closer together
    # nearer the cells.
    gap = fine[0] - body_radius_m
    coarse = (
        fine[0] - ray_distances(cells.res, gap, cells.res, FAR_STEP_DEG)[::-1]
        if gap > cells.res
        else np.empty(0)
    )
    coarse = coarse[coarse > body_radius_m]

    ray_step = RAY_GAP_CELLS * cells.res / farthest
    ray_az = centre_az + np.arange(
        corner_az.min() - ray_step, corner_az.max() + 2 * ray_step, ray_step
    )

    # The highest elevation angle (seen from the point) of the terrain up to each fine sample.
    horizon = np.empty((ray_az.size, fine.size), np.float32)
    for start in range(0, ray_az.size, RAYS_PER_CHUNK):
        az = ray_az[start : start + RAYS_PER_CHUNK, None]
        coarse_max = _elevation(terrain, cells, px, py, point_radius, az, coarse).max(
            axis=1, initial=-np.inf
        )
        fine_elev = _elevation(terrain, cells, px, py, point_radius, az, fine)
        fine_elev[:, fine <= body_radius_m] = -np.inf
        running = np.maximum.accumulate(fine_elev, axis=1)
        horizon[start : start + az.shape[0]] = np.maximum(running, coarse_max[:, None])

    xs, ys = cells.centres()
    out = np.zeros(cells.shape, bool)
    for row, y in enumerate(ys):
        x = xs
        ground = terrain.height(x, np.full_like(x, y), np.zeros_like(x))
        dist = np.hypot(x - px, y - py)
        eye = MARS_RADIUS_M + ground + observer_height_m
        angle = dist / MARS_RADIUS_M
        eye_elev = np.arctan2(eye * np.cos(angle) - point_radius, eye * np.sin(angle))
        ray = np.rint(_wrap(np.arctan2(x - px, y - py) - ray_az[0]) / ray_step).astype(np.int64)
        # The terrain at least one cell in front of the eye: the cell's own
        # ground is what the eye stands on. The fine samples start a cell
        # before the nearest cell, so this index is never negative.
        before = np.floor((dist - cells.res - fine[0]) / cells.res).astype(np.int64)
        blocking = horizon[np.clip(ray, 0, ray_az.size - 1), np.clip(before, 0, fine.size - 1)]
        out[row] = eye_elev >= blocking
    return out


def _elevation(
    terrain: Terrain,
    cells: Cells,
    px: float,
    py: float,
    point_radius: float,
    az: np.ndarray,
    distances: np.ndarray,
) -> np.ndarray:
    """Elevation angle (radians) seen from the point of the terrain at each
    distance along each ray; no data counts as no blocking."""
    if distances.size == 0:
        return np.empty((az.shape[0], 0))
    x = px + distances[None, :] * np.sin(az)
    y = py + distances[None, :] * np.cos(az)
    heights = terrain.height(x, y, cells.distance_to(x, y))
    radius = MARS_RADIUS_M + heights
    angle = distances[None, :] / MARS_RADIUS_M
    elev = np.arctan2(radius * np.cos(angle) - point_radius, radius * np.sin(angle))
    return np.where(np.isnan(elev), -np.inf, elev)


def _wrap(angle: np.ndarray) -> np.ndarray:
    """An angle in radians, wrapped into [-pi, pi)."""
    return (angle + np.pi) % (2 * np.pi) - np.pi


@dataclass(frozen=True)
class Landmark:
    """A far feature on the skyline, as the points that stand for it: its
    summit, or for the crater rim, points along the crest."""

    id: str
    title: str
    points: tuple[tuple[float, float], ...]
    body_radius_m: float
    """Ground within this distance of a point is the landmark itself and never hides it."""
    in_sentence: str | None = None
    """How a direction names it mid-sentence ("the upper Mount Sharp peak"); the title if None."""


def landmark_masks(
    terrain: Terrain, landmarks: list[Landmark], cells: Cells, *, observer_height_m: float
) -> dict[str, np.ndarray]:
    """For each landmark, True where a cell sees at least one of its points."""
    masks = {}
    for landmark in landmarks:
        seen = np.zeros(cells.shape, bool)
        for point in landmark.points:
            seen |= sees_point(
                terrain,
                point,
                cells,
                body_radius_m=landmark.body_radius_m,
                observer_height_m=observer_height_m,
            )
        masks[landmark.id] = seen
    return masks


def location_quality(masks: dict[str, np.ndarray]) -> np.ndarray:
    """The share of the landmarks each cell sees, 0 to 1, every landmark weighing the same."""
    return np.mean([mask.astype(np.float32) for mask in masks.values()], axis=0)
