"""The Gale walk-area pack's pure parts: walk area, site config, frame check, chemistry."""

import bisect
import csv
import re
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from prep.common import Bounds


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
    current: dict,
) -> dict:
    """sites/gale.yaml, rewritten over `current`, the config on disk.

    The pack owns the geometry and its own `files` entries. What later tickets
    add is kept: the sol (Person 4), science targets (P2-03), checkpoints and
    any other files.
    """
    min_x, min_y, max_x, max_y = walk_area(habitat, walk_radius_m)
    return {
        "site": "gale",
        "name": name,
        "projection": projection,
        "bounds": {"min_x": min_x, "min_y": min_y, "max_x": max_x, "max_y": max_y},
        "habitat": {"x": habitat[0], "y": habitat[1]},
        "base_camp": {"x": base_camp[0], "y": base_camp[1]},
        "science_targets": current.get("science_targets") or [],
        "checkpoints": current.get("checkpoints") or [],
        "files": (current.get("files") or {}) | files,
        "replayed_sol": current.get("replayed_sol"),
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


def best_move(
    coarse: np.ndarray,
    coarse_grid: PixelGrid,
    fine: np.ndarray,
    fine_grid: PixelGrid,
    search_m: float,
) -> dict:
    """How far to move `coarse` (east, north, in metres) to line it up best with `fine`.

    `coarse`'s pixels must be a whole number of `fine`'s. Moves are tried in
    steps of one fine pixel up to `search_m` either way; the move counts from
    where `coarse_grid` puts the layer, so it includes the part of a fine pixel
    by which the two grids are off. Returns the move, its r and the r unmoved.
    """
    col, row = offset_in_pixels(
        PixelGrid(coarse_grid.left, coarse_grid.top, fine_grid.res), on=fine_grid
    )
    found = best_shift(
        coarse,
        fine,
        factor=round(coarse_grid.res / fine_grid.res),
        origin_px=(round(col), round(row)),
        search_px=round(search_m / fine_grid.res),
    )
    d_col, d_row = found["shift_px"]
    return {
        "move_m": [
            round((round(col) + d_col - col) * fine_grid.res, 3),
            round(-(round(row) + d_row - row) * fine_grid.res, 3),
        ],
        "r": found["r"],
        "r_unmoved": found["r_unshifted"],
    }


def shading(heights: np.ndarray, res: float, azimuth_deg: float) -> np.ndarray:
    """How steeply each cell faces light from `azimuth_deg` (clockwise from north).

    The slope along the light's direction, positive where the ground tilts
    towards the light: a photo's brightness follows it.
    """
    dz_south, dz_east = np.gradient(heights, res)  # rows run south
    a = np.radians(azimuth_deg)
    return -(np.sin(a) * dz_east - np.cos(a) * dz_south)


def slope_degrees(heights: np.ndarray, res: float) -> np.ndarray:
    dz_south, dz_east = np.gradient(heights, res)
    return np.degrees(np.arctan(np.hypot(dz_east, dz_south)))


def photo_move_on_terrain(
    photo: np.ndarray,
    photo_grid: PixelGrid,
    heights: np.ndarray,
    terrain_grid: PixelGrid,
    search_m: float,
    coarse: int = 4,
) -> dict:
    """How far the terrain must move (east, north, metres) to line up with the photo.

    Both on grids of one pixel size. The photo's brightness follows the
    terrain's shading; the light's azimuth is unknown, so every 30 degrees is
    tried. Each azimuth is searched on `coarse`-times larger pixels, the best
    match of all wins, and the move is refined at full size within one coarse
    pixel of it.
    """
    res = photo_grid.res
    coarse_photo = _block_mean(photo, coarse)
    coarse_photo_grid = PixelGrid(photo_grid.left, photo_grid.top, res * coarse)
    coarse_terrain_grid = PixelGrid(terrain_grid.left, terrain_grid.top, res * coarse)
    rough = {}
    for az in range(0, 360, 30):
        shade = _block_mean(shading(heights, res, az), coarse)
        rough[az] = best_move(shade, coarse_terrain_grid, coarse_photo, coarse_photo_grid, search_m)
    best_az = max(rough, key=lambda az: rough[az]["r"])
    east, north = rough[best_az]["move_m"]
    shade = shading(heights, res, best_az)
    fine = best_move(
        shade,
        PixelGrid(terrain_grid.left + east, terrain_grid.top + north, res),
        photo,
        photo_grid,
        res * coarse,
    )
    return {
        "azimuth_deg": best_az,
        "move_m": [round(east + fine["move_m"][0], 3), round(north + fine["move_m"][1], 3)],
        "r": fine["r"],
        "r_unmoved": best_move(shade, terrain_grid, photo, photo_grid, 0.0)["r"],
    }


def _block_mean(a: np.ndarray, k: int) -> np.ndarray:
    rows, cols = a.shape[0] // k, a.shape[1] // k
    blocks = a[: rows * k, : cols * k].reshape(rows, k, cols, k)
    with np.errstate(invalid="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN blocks stay NaN
        return np.nanmean(blocks, axis=(1, 3))


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


def compare_heights(places_m: list[float], terrain_m: list[float], within_m: float) -> dict:
    """How well the terrain's heights at Curiosity's stops match PLACES' elevations.

    A sideways shift between the two frames shows up as height differences on
    slopes; stops with no terrain under them are left out.
    """
    diff = np.asarray(terrain_m, dtype=float) - np.asarray(places_m, dtype=float)
    diff = diff[np.isfinite(diff)]
    return {
        "count": int(diff.size),
        "median_m": round(float(np.median(diff)), 3),
        "share_within": round(float(np.mean(np.abs(diff) <= within_m)), 3),
        "within_m": within_m,
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
                        "z": float(r["elevation"]),
                    }
                )
    return positions


def rover_track(places_interp_csv: Path) -> list[dict]:
    """Every rover pose in PLACES' every-drive table, in order: sol, site, drive, x, y."""
    track = []
    with places_interp_csv.open(newline="") as f:
        for r in csv.DictReader(f):
            if r["frame"] == "ROVER":
                track.append(
                    {
                        "sol": int(r["sol"]),
                        "sclk": float(r["sclk"]),
                        "site": int(r["site"]),
                        "drive": int(r["drive"]),
                        "x": float(r["easting"]),
                        "y": float(r["northing"]),
                    }
                )
    return sorted(track, key=lambda p: (p["sol"], p["sclk"]))


def rover_sols_inside(places_interp_csv: Path, bounds: Bounds) -> tuple[int, int]:
    """The first and last sol Curiosity stood inside `bounds`, from PLACES."""
    min_x, min_y, max_x, max_y = bounds
    sols = []
    with places_interp_csv.open(newline="") as f:
        for r in csv.DictReader(f):
            x, y = float(r["easting"]), float(r["northing"])
            if r["frame"] == "ROVER" and min_x <= x <= max_x and min_y <= y <= max_y:
                sols.append(int(r["sol"]))
    return min(sols), max(sols)


# An APXS table name: msl_apxs_concentrations_<first sol>_<last sol>.csv
_APXS_TABLE = re.compile(r"_(\d+)_(\d+)\.csv$")


def apxs_tables_for(tables: list[str], sols: tuple[int, int]) -> list[str]:
    """The tables whose sol range overlaps `sols`, in the order given."""
    first, last = sols
    chosen = []
    for name in tables:
        start, end = (int(n) for n in _APXS_TABLE.search(name).groups())
        if start <= last and end >= first:
            chosen.append(name)
    return chosen


def apxs_points(apxs_csvs: list[Path], track: list[dict], bounds: Bounds) -> list[dict]:
    """Every APXS measurement inside `bounds`, in sol order, where the rover stood.

    The rover stands where its last drive before the measurement's sol ended
    (PLACES gives the sol each pose was reached). check_apxs_placement holds
    this against the source-file names where those can be trusted; in the sol
    3193 to 4133 table they are scrambled, so they are not used to place.
    APXS sits on the arm, so the target is within about 2 m.
    Concentrations are copied as published (oxides in wt%, Ni, Zn and Br in ppm).
    """
    min_x, min_y, max_x, max_y = bounds
    sols = [p["sol"] for p in track]
    points = []
    for path in apxs_csvs:
        with path.open(newline="", encoding="utf-8-sig") as f:
            rows = csv.reader(f)
            header = next(rows)
            # Concentrations and their errors run from Na2O to Br_err.
            values = header[header.index("Na2O") : header.index("Br_err") + 1]
            for row in rows:
                if not row:
                    continue
                record = dict(zip(header, row, strict=False))
                sol = int(record["sol"])
                before = bisect.bisect_left(sols, sol) - 1
                if before < 0:
                    raise ValueError(f"{record['target']}: PLACES has no pose before sol {sol}")
                pose = track[before]
                if min_x <= pose["x"] <= max_x and min_y <= pose["y"] <= max_y:
                    points.append(
                        {"sol": sol, "target": record["target"]}
                        | {k: pose[k] for k in ("site", "drive", "x", "y")}
                        | {k: float(record[k]) for k in values}
                    )
    return sorted(points, key=lambda p: p["sol"])


# An APXS source file name: ...ESC<sol, 4 digits><site, 3><drive, 4>...
_APXS_FILE = re.compile(r"ESC(\d{4})(\d{3})(\d{4})")
# An overnight or multi-sol measurement's files can start a sol or two after its row's sol.
_FILE_SOL_SLACK = 2


def check_apxs_placement(apxs_csvs: list[Path], track: list[dict]) -> dict:
    """How often placing by sol gives the site and drive the source-file names give.

    Only rows whose file names carry their own sol (within two sols) are checked.
    """
    sols = [p["sol"] for p in track]
    checked = same = elsewhere = 0
    for path in apxs_csvs:
        with path.open(newline="", encoding="utf-8-sig") as f:
            rows = csv.reader(f)
            next(rows)
            for row in rows:
                if not row:
                    continue
                file_sol, site, drive = (int(n) for n in _APXS_FILE.search(row[-1]).groups())
                if abs(file_sol - int(row[0])) > _FILE_SOL_SLACK:
                    elsewhere += 1
                    continue
                pose = track[bisect.bisect_left(sols, int(row[0])) - 1]
                checked += 1
                same += (pose["site"], pose["drive"]) == (site, drive)
    return {"rows_checked": checked, "same_pose": same, "files_name_another_sol": elsewhere}


# CRISM marks no data with 65535; real summary values are far below this.
_CRISM_VALID_BELOW = 1e3


def band_gaps(cube: np.ma.MaskedArray, names: list[str], regions: dict[str, np.ndarray]) -> dict:
    """Cells without data in each band of a CRISM cube, counted in each region.

    `cube` is (band, row, col); a cell has no data if masked or at the no-data
    value. Each region is a boolean mask of the cube's cells. Bands with no gap
    anywhere are left out of the list and counted as complete.
    """
    missing = np.ma.getmaskarray(cube) | (np.abs(cube.filled(0)) >= _CRISM_VALID_BELOW)
    counts = {
        name: {region: int(missing[i][inside].sum()) for region, inside in regions.items()}
        for i, name in enumerate(names)
    }
    return {
        "bands": len(names),
        "bands_complete": {r: sum(c[r] == 0 for c in counts.values()) for r in regions},
        "cells_without_data": {n: c for n, c in counts.items() if any(c.values())},
    }
