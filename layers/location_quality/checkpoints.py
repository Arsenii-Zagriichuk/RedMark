"""Checkpoint candidates (layer 5, P3-06): where the crew should stop to take a fix.

A checkpoint sits on a ridge top or open ground (GLOSSARY.md), never in a
hollow, where nearby ridges hide the skyline. Candidates are the cells with the
best location-quality score, picked one at a time: each pick rules out every
cell within the spacing of it, so the candidates spread over the walk area
instead of crowding one good patch. The route (P4-07) chooses among them.
"""

import numpy as np

from layers.location_quality.visibility import Cells


def checkpoint_candidates(
    score: np.ndarray, hollow: np.ndarray, cells: Cells, *, count: int, spacing_m: float
) -> list[tuple[float, float]]:
    """Up to count cell centres (map x, y), best score first, at least spacing_m apart."""
    xs, ys = cells.centres()
    open_score = np.where(hollow | np.isnan(score), -np.inf, score)
    picked: list[tuple[float, float]] = []
    while len(picked) < count:
        best = np.unravel_index(np.argmax(open_score), open_score.shape)
        if not np.isfinite(open_score[best]):
            break
        x, y = float(xs[best[1]]), float(ys[best[0]])
        picked.append((x, y))
        open_score[np.hypot(xs[None, :] - x, ys[:, None] - y) < spacing_m] = -np.inf
    return picked
