"""The ground match: slide an overhead view over a photo-map window and take the
spot where they correlate best (masked normalised cross-correlation).

Both images are high-passed first, so the match follows ground texture (ridges,
rocks, sand edges) rather than overall brightness, which differs between the
orbiter's and the rover's lighting.
"""

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import gaussian_filter
from scipy.signal import fftconvolve

from locate.ground.mosaic import VIEW_CELL_M, OverheadView

HIGHPASS_M = 4.0
"""Texture finer than this is kept. Chosen on the tuning pile (locate/ground/tune.py)."""
RUNNER_UP_EXCLUSION_M = 4.0
"""The runner-up peak is the best one at least this far from the best."""


@dataclass(frozen=True)
class MapWindow:
    """A north-up piece of the photo map, VIEW_CELL_M cells; (left_x, top_y) is
    its north-west corner in map metres."""

    image: np.ndarray
    left_x: float
    top_y: float


@dataclass(frozen=True)
class GroundMatch:
    """Where the view's centre (the rover) lands on the map, and how sharp the
    best correlation is against the runner-up."""

    x: float
    y: float
    peak: float
    runner_up: float


def ground_match(
    window: MapWindow, view: OverheadView, highpass_m: float = HIGHPASS_M
) -> GroundMatch:
    mask = view.mask.astype(np.float64)
    seen_mean = view.image[view.mask].mean()
    template = _highpass(np.where(view.mask, view.image, seen_mean), highpass_m)
    search = _highpass(window.image.astype(np.float64), highpass_m)
    score = _masked_ncc(search, template, mask)

    row, col = np.unravel_index(np.argmax(score), score.shape)
    half = view.image.shape[0] / 2
    exclusion = round(RUNNER_UP_EXCLUSION_M / VIEW_CELL_M)
    rest = score.copy()
    rest[
        max(0, row - exclusion) : row + exclusion + 1, max(0, col - exclusion) : col + exclusion + 1
    ] = -np.inf
    return GroundMatch(
        x=window.left_x + (col + half) * VIEW_CELL_M,
        y=window.top_y - (row + half) * VIEW_CELL_M,
        peak=float(score[row, col]),
        runner_up=float(rest.max()) if np.isfinite(rest.max()) else float("nan"),
    )


def _highpass(image: np.ndarray, sigma_m: float) -> np.ndarray:
    return image - gaussian_filter(image, sigma_m / VIEW_CELL_M)


def _masked_ncc(search: np.ndarray, template: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Normalised cross-correlation over the masked cells only, at every
    placement of the template fully inside search (top-left corner indexed)."""
    n = mask.sum()
    template = np.where(mask > 0, template - (template * mask).sum() / n, 0.0)
    template_norm = np.sqrt((template * template).sum())
    flipped_mask = mask[::-1, ::-1]
    products = fftconvolve(search, template[::-1, ::-1], mode="valid")
    sums = fftconvolve(search, flipped_mask, mode="valid")
    squares = fftconvolve(search * search, flipped_mask, mode="valid")
    variance = np.maximum(squares - sums * sums / n, 1e-9)
    return products / (template_norm * np.sqrt(variance))
