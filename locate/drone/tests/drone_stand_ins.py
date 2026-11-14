"""Stand-ins shared by the drone tests: a synthetic photo map and a matcher
that needs no GPU.

`ncc_matcher` finds the view in each map tile by normalised cross-correlation,
so it only succeeds if the view really is the map, north up, at 25 cm, shifted
by whole pixels.
"""

import numpy as np

from locate.drone.fix import Matches


def smooth_noise(size: int, sigma_px: float, seed: int) -> np.ndarray:
    radius = int(3 * sigma_px)
    kernel = np.exp(-0.5 * (np.arange(-radius, radius + 1) / sigma_px) ** 2)
    kernel /= kernel.sum()
    field = np.random.default_rng(seed).normal(size=(size, size))
    field = np.apply_along_axis(np.convolve, 0, field, kernel, mode="same")
    return np.apply_along_axis(np.convolve, 1, field, kernel, mode="same")


def _correlate(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """c[k] = sum_p a[p] * b[p + k - (a.shape - 1)], for every overlap."""
    shape = (a.shape[0] + b.shape[0] - 1, a.shape[1] + b.shape[1] - 1)
    spectrum = np.fft.rfft2(a[::-1, ::-1], shape) * np.fft.rfft2(b, shape)
    return np.fft.irfft2(spectrum, shape)


def ncc_matcher(query: np.ndarray, reference: np.ndarray) -> Matches:
    """Finds the shift that best lines up the view's seen pixels (non-zero)
    with the tile, by normalised cross-correlation, and returns a grid of
    matches at that shift if the correlation is strong."""
    seen = (query > 0).astype(np.float64)
    q = query.astype(np.float64) * seen
    t = reference.astype(np.float64)
    ones = np.ones_like(t)
    n = _correlate(seen, ones)
    sum_q, sum_q2 = _correlate(q, ones), _correlate(q * q, ones)
    sum_t, sum_t2 = _correlate(seen, t), _correlate(seen, t * t)
    sum_qt = _correlate(q, t)
    with np.errstate(invalid="ignore", divide="ignore"):
        cov = sum_qt - sum_q * sum_t / n
        ncc = cov / np.sqrt((sum_q2 - sum_q**2 / n) * (sum_t2 - sum_t**2 / n))
    ncc[n < 0.6 * seen.sum()] = -1
    k = np.unravel_index(np.nanargmax(ncc), ncc.shape)
    if ncc[k] < 0.8:
        return Matches(query_xy=np.empty((0, 2)), reference_xy=np.empty((0, 2)))
    shift = np.array([k[1] - (query.shape[1] - 1), k[0] - (query.shape[0] - 1)], dtype=float)
    rows, cols = np.mgrid[4 : query.shape[0] : 8, 4 : query.shape[1] : 8]
    grid = np.column_stack([cols.ravel(), rows.ravel()]).astype(float)
    grid = grid[seen[grid[:, 1].astype(int), grid[:, 0].astype(int)] > 0]
    moved = grid + shift
    inside = np.all((moved >= 0) & (moved <= np.array(reference.shape[::-1]) - 1), axis=1)
    return Matches(query_xy=grid[inside], reference_xy=moved[inside])
