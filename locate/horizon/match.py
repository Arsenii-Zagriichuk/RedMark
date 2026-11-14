"""Match a photo's skyline against the horizon grid.

The photo skyline is a set of samples: azimuth relative to the photo's own
heading (unknown to the matcher) and elevation above the level horizon (known
from the camera's tilt). For every grid spot and every heading the photo is
laid onto the calculated skyline and scored by its clipped mean difference,
so a stretch of misread skyline (haze taken for a ridge) costs at most
CLIP_DEG per sample instead of dragging the match away.
"""

from dataclasses import dataclass

import numpy as np

CLIP_DEG = 1.0
SPOTS_PER_CHUNK = 16


@dataclass(frozen=True)
class Match:
    iy: int
    ix: int
    heading_deg: float
    """Heading of the photo's reference direction (relative azimuth 0)."""
    cost_deg: np.ndarray
    """Best clipped mean difference at each grid spot, in degrees."""


def match_skyline(
    elevation_deg: np.ndarray,
    azimuth_step_deg: float,
    relative_azimuth_deg: np.ndarray,
    photo_elevation_deg: np.ndarray,
) -> Match:
    """The grid spot and heading whose calculated skyline best fits the photo.

    elevation_deg is the grid's [iy, ix, iaz] skyline, with azimuths every
    azimuth_step_deg from 0. Photo samples falling in one azimuth step are
    merged by their median, so overlapping frames count once.
    """
    n_az = elevation_deg.shape[-1]
    offsets, photo = _binned(relative_azimuth_deg, photo_elevation_deg, azimuth_step_deg, n_az)
    look = (np.arange(n_az)[:, None] + offsets[None, :]) % n_az  # [heading, sample]
    spots = elevation_deg.reshape(-1, n_az)
    best_cost = np.empty(spots.shape[0])
    best_heading = np.empty(spots.shape[0], np.int64)
    for start in range(0, spots.shape[0], SPOTS_PER_CHUNK):
        calculated = spots[start : start + SPOTS_PER_CHUNK][:, look]  # [spot, heading, sample]
        cost = np.minimum(np.abs(calculated - photo), CLIP_DEG).mean(axis=2)
        best_heading[start : start + SPOTS_PER_CHUNK] = cost.argmin(axis=1)
        best_cost[start : start + SPOTS_PER_CHUNK] = cost.min(axis=1)
    cost_grid = best_cost.reshape(elevation_deg.shape[:2])
    iy, ix = np.unravel_index(np.nanargmin(cost_grid), cost_grid.shape)
    heading = best_heading[iy * elevation_deg.shape[1] + ix] * azimuth_step_deg
    return Match(int(iy), int(ix), float(heading), cost_grid)


def _binned(relative_deg, elevation_deg, step_deg, n_az):
    """Azimuth-step offsets that hold samples, and the median elevation in each."""
    keep = np.isfinite(relative_deg) & np.isfinite(elevation_deg)
    offsets = np.round(np.asarray(relative_deg)[keep] / step_deg).astype(np.int64) % n_az
    elevation = np.asarray(elevation_deg)[keep]
    if offsets.size == 0:
        raise ValueError("the photo has no skyline samples")
    order = np.argsort(offsets, kind="stable")
    offsets, elevation = offsets[order], elevation[order]
    unique, starts = np.unique(offsets, return_index=True)
    medians = np.array([np.median(chunk) for chunk in np.split(elevation, starts[1:])])
    return unique, medians.astype(np.float32)
