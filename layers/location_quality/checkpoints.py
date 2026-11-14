"""Checkpoint candidates (layer 5, P3-06): where the crew should stop to take a fix.

A checkpoint sits on a ridge top or open ground (GLOSSARY.md), never in a
hollow, where nearby ridges hide the skyline. The walk area is cut into
squares and each square gives its best cell, so there are candidates wherever
a route goes, not only in the one corner that sees every landmark. The score
takes only a few values, so many cells tie; a tie goes to the cell whose
surroundings score best, which keeps candidates off the rim of a hollow and the
edge of the map. The route (P4-07) chooses among them.
"""

import numpy as np
from scipy.ndimage import uniform_filter

from layers.location_quality.visibility import Cells


def checkpoint_candidates(
    score: np.ndarray, hollow: np.ndarray, cells: Cells, *, square_m: float, neighbourhood_m: float
) -> list[tuple[float, float]]:
    """The best cell centre (map x, y) of each square_m square, best score first.

    Ties go to the higher mean score within neighbourhood_m (outside the map counts
    as 0). Hollows and cells with no score are never candidates.
    """
    open_score = np.where(hollow | np.isnan(score), -np.inf, score)
    size = 2 * round(neighbourhood_m / cells.res) + 1
    around = uniform_filter(np.nan_to_num(score, nan=0.0), size=size, mode="constant")
    xs, ys = cells.centres()
    step = max(1, round(square_m / cells.res))
    picked = []
    for top in range(0, cells.shape[0], step):
        for left in range(0, cells.shape[1], step):
            block = open_score[top : top + step, left : left + step]
            best = block.max()
            if not np.isfinite(best):
                continue
            ties = np.where(block == best, around[top : top + step, left : left + step], -np.inf)
            row, col = np.unravel_index(np.argmax(ties), ties.shape)
            picked.append((float(best), float(xs[left + col]), float(ys[top + row])))
    picked.sort(key=lambda p: -p[0])
    return [(x, y) for _, x, y in picked]
