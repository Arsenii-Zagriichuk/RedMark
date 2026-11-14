"""Calculated skylines from terrain heights on the Mars sphere.

A skyline is the elevation angle of the horizon in every direction from one
spot. Positions are map metres in the site projection (equirectangular, true
scale at the equator, so at Gale they are within 0.3% of ground metres).
Azimuths are headings: degrees clockwise from map north.
"""

from dataclasses import dataclass

import numpy as np

MARS_RADIUS_M = 3_396_190.0


@dataclass(frozen=True)
class Raster:
    """Heights on a north-up grid. Row 0 is the north edge; NaN means no data."""

    heights: np.ndarray
    left: float
    top: float
    res: float

    def sample(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        """Bilinear height at each point; NaN outside the grid or next to no data."""
        col = (np.asarray(x, np.float64) - self.left) / self.res - 0.5
        row = (self.top - np.asarray(y, np.float64)) / self.res - 0.5
        c0 = np.floor(col).astype(np.int64)
        r0 = np.floor(row).astype(np.int64)
        rows, cols = self.heights.shape
        inside = (c0 >= 0) & (r0 >= 0) & (c0 + 1 < cols) & (r0 + 1 < rows)
        out = np.full(col.shape, np.nan)
        c, r = c0[inside], r0[inside]
        fc, fr = col[inside] - c, row[inside] - r
        h = self.heights
        top_edge = h[r, c] * (1 - fc) + h[r, c + 1] * fc
        bottom_edge = h[r + 1, c] * (1 - fc) + h[r + 1, c + 1] * fc
        out[inside] = top_edge * (1 - fr) + bottom_edge * fr
        return out


@dataclass(frozen=True)
class Tier:
    """One terrain source, used for points up to max_distance_m from the spot."""

    raster: Raster
    max_distance_m: float = np.inf


class Terrain:
    """Terrain from several sources, finest first.

    Each point takes its height from the finest tier that reaches its
    distance and has data there, so the 1 m terrain shapes the near skyline,
    a coarser copy the middle distance and MOLA the far crater rim.
    """

    def __init__(self, tiers: list[Tier]):
        self.tiers = tiers

    def height(self, x: np.ndarray, y: np.ndarray, distance_m: np.ndarray) -> np.ndarray:
        x, y = np.asarray(x, np.float64), np.asarray(y, np.float64)
        distance_m = np.broadcast_to(distance_m, x.shape)
        out = np.full(x.shape, np.nan)
        for tier in self.tiers:
            todo = np.isnan(out) & (distance_m <= tier.max_distance_m)
            if todo.any():
                out[todo] = tier.raster.sample(x[todo], y[todo])
        return out


def skyline(
    terrain: Terrain,
    x: float,
    y: float,
    *,
    observer_height_m: float,
    azimuths_deg: np.ndarray,
    distances_m: np.ndarray,
) -> np.ndarray:
    """Horizon elevation in degrees for each azimuth, seen from (x, y).

    The eye is observer_height_m above the ground at (x, y). Every sample is
    placed on the sphere, so far ground sits lower than on a flat map: 60 km
    away it drops about 530 m, about 0.5°. Directions with no data anywhere
    come back NaN.
    """
    ground = terrain.height(np.array([x]), np.array([y]), np.array([0.0]))[0]
    eye_radius = MARS_RADIUS_M + ground + observer_height_m
    az = np.radians(np.asarray(azimuths_deg, np.float64))[:, None]
    d = np.asarray(distances_m, np.float64)[None, :]
    px = x + d * np.sin(az)
    py = y + d * np.cos(az)
    heights = terrain.height(px, py, np.broadcast_to(d, px.shape))
    angle = d / MARS_RADIUS_M
    point_radius = MARS_RADIUS_M + heights
    elevation = np.degrees(
        np.arctan2(point_radius * np.cos(angle) - eye_radius, point_radius * np.sin(angle))
    )
    has_data = ~np.isnan(elevation).all(axis=1)
    out = np.full(az.shape[0], np.nan)
    out[has_data] = np.nanmax(elevation[has_data], axis=1)
    return out
