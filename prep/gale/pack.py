"""The Gale walk-area pack's pure parts: walk area, site config and the frame check."""

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from prep.gale.crop import Bounds


@dataclass(frozen=True)
class PixelGrid:
    """A map's pixel grid: top-left corner and pixel size, in map metres."""

    left: float
    top: float
    res: float


def walk_area(habitat: tuple[float, float], radius_m: float) -> Bounds:
    """The square holding every point within `radius_m` of the habitat."""
    x, y = habitat
    return (x - radius_m, y - radius_m, x + radius_m, y + radius_m)


def grow(bounds: Bounds, margin_m: float) -> Bounds:
    min_x, min_y, max_x, max_y = bounds
    return (min_x - margin_m, min_y - margin_m, max_x + margin_m, max_y + margin_m)


def site_config(
    *,
    name: str,
    projection: str,
    habitat: tuple[float, float],
    base_camp: tuple[float, float],
    walk_radius_m: float,
    files: dict[str, str],
    replayed_sol: int | None,
) -> dict:
    """sites/gale.yaml. Science targets are added in P2-03, the sol by Person 4."""
    min_x, min_y, max_x, max_y = walk_area(habitat, walk_radius_m)
    return {
        "site": "gale",
        "name": name,
        "projection": projection,
        "bounds": {"min_x": min_x, "min_y": min_y, "max_x": max_x, "max_y": max_y},
        "habitat": {"x": habitat[0], "y": habitat[1]},
        "base_camp": {"x": base_camp[0], "y": base_camp[1]},
        "science_targets": [],
        "checkpoints": [],
        "files": files,
        "replayed_sol": replayed_sol,
    }


def fit_pixel_grid(
    eastings: list[float], northings: list[float], samples: list[float], lines: list[float]
) -> PixelGrid:
    """The pixel grid on which each position (easting, northing) is pixel (sample, line)."""
    res_x, left = np.polyfit(samples, eastings, 1)
    res_y, top = np.polyfit(lines, northings, 1)
    return PixelGrid(left=float(left), top=float(top), res=float((res_x - res_y) / 2))


def offset_in_pixels(grid: PixelGrid, *, on: PixelGrid) -> tuple[float, float]:
    """Where `grid`'s top-left corner falls on `on`, as (column, row) of `on`.

    Whole numbers mean the two grids line up pixel for pixel.
    """
    if not np.isclose(grid.res, on.res, rtol=1e-6):
        raise ValueError(f"grids of resolution {grid.res} and {on.res} m cannot line up")
    return ((grid.left - on.left) / on.res, (on.top - grid.top) / on.res)


def best_shift(
    coarse: np.ndarray,
    fine: np.ndarray,
    *,
    factor: int,
    origin_px: tuple[int, int],
    search_px: int,
) -> dict:
    """The shift of `coarse` that best lines it up with `fine`, by correlation.

    `coarse` has pixels `factor` times the size of `fine`'s, and its top-left
    corner sits at `origin_px` (col, row) on `fine`. Each shift (col, row), in
    fine pixels up to `search_px` either way, compares every coarse pixel with
    the block of `fine` it would cover if the coarse layer were moved by that
    shift. The correlation's sign does not matter, so the strongest |r| wins.
    Returns the best shift, its r and the r with no shift.
    """
    scores = {}
    for d_row in range(-search_px, search_px + 1):
        for d_col in range(-search_px, search_px + 1):
            scores[(d_col, d_row)] = _block_correlation(
                coarse, fine, factor, origin_px[0] + d_col, origin_px[1] + d_row
            )
    shift = max(scores, key=lambda s: abs(scores[s]))
    return {"shift_px": shift, "r": scores[shift], "r_unshifted": scores[(0, 0)]}


def _block_correlation(coarse, fine, factor, col0, row0) -> float:
    # Skip coarse rows and columns whose block starts before the fine image.
    skip_rows, skip_cols = max(0, -(row0 // factor)), max(0, -(col0 // factor))
    row0, col0 = row0 + skip_rows * factor, col0 + skip_cols * factor
    rows = min(coarse.shape[0] - skip_rows, (fine.shape[0] - row0) // factor)
    cols = min(coarse.shape[1] - skip_cols, (fine.shape[1] - col0) // factor)
    blocks = fine[row0 : row0 + rows * factor, col0 : col0 + cols * factor]
    blocks = blocks.reshape(rows, factor, cols, factor).mean(axis=(1, 3))
    layer = coarse[skip_rows : skip_rows + rows, skip_cols : skip_cols + cols]
    valid = np.isfinite(blocks) & np.isfinite(layer)
    return float(np.corrcoef(blocks[valid], layer[valid])[0, 1])


def places_grids(places_csv: Path) -> dict[str, PixelGrid]:
    """The orthophoto and terrain grids PLACES localised Curiosity on."""
    with places_csv.open(newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["frame"] == "ROVER"]
    eastings = [float(r["easting"]) for r in rows]
    northings = [float(r["northing"]) for r in rows]
    return {
        kind: fit_pixel_grid(
            eastings,
            northings,
            [float(r[f"{kind}_pixel_sample"]) for r in rows],
            [float(r[f"{kind}_pixel_line"]) for r in rows],
        )
        for kind in ("map", "dem")
    }


def rover_positions(places_csv: Path, bounds: Bounds) -> list[dict]:
    """Curiosity's localised positions inside `bounds`, in drive order."""
    min_x, min_y, max_x, max_y = bounds
    positions = []
    with places_csv.open(newline="") as f:
        for r in csv.DictReader(f):
            x, y = float(r["easting"]), float(r["northing"])
            if r["frame"] == "ROVER" and min_x <= x <= max_x and min_y <= y <= max_y:
                positions.append(
                    {
                        "sol": int(r["sol"]),
                        "site": int(r["site"]),
                        "drive": int(r["drive"]),
                        "x": x,
                        "y": y,
                    }
                )
    return positions
