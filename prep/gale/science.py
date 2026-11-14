"""Layer 3 at Gale (P2-03): mineral highlights, Curiosity's chemistry and drill sites,
and the checks every science target must pass."""

import math

import numpy as np
import rasterio

# CRISM summary parameters (Viviano-Beck et al. 2014, JGR Planets 119) that pick out
# the minerals of Mount Sharp's sulfate unit, lowest code first; where a pixel stands
# out in two, the higher code is shown.
MINERAL_INDICES: list[tuple[str, str, str]] = [
    ("BD1900R2", "hydrated", "Hydrated minerals"),
    ("D2300", "clay", "Fe/Mg clay"),
    ("BD2100_2", "monohydrated_sulfate", "Monohydrated sulfate"),
    ("SINDEX2", "polyhydrated_sulfate", "Polyhydrated sulfate"),
]
# A pixel stands out where its index is positive and above this percentile of the
# walk area's pixels. The indices here are weak (the 95th percentiles sit near 0.01),
# so this marks where each mineral is strongest here, not a detection threshold.
HIGHLIGHT_PERCENTILE = 95


def mineral_classes(bands: dict[str, np.ndarray]) -> np.ndarray:
    """Per pixel, the code (1-based, in MINERAL_INDICES order) of the highest-coded
    index that stands out there; 0 where none does or the data is missing."""
    shape = next(iter(bands.values())).shape
    classes = np.zeros(shape, dtype=np.uint8)
    for code, (index, _, _) in enumerate(MINERAL_INDICES, start=1):
        values = bands[index]
        known = np.isfinite(values)
        if not known.any():
            continue
        cutoff = max(np.percentile(values[known], HIGHLIGHT_PERCENTILE), 0.0)
        classes[known & (np.where(known, values, -np.inf) > cutoff)] = code
    return classes


# Science targets: a spot Curiosity never reached, so clear of its track and drill holes.
TARGET_CLEAR_OF_TRACK_M = 25.0
TARGET_CLEAR_OF_DRILL_M = 50.0
# A ridge target sits on the ridge map; a hollow target has no ridge this close.
RIDGE_TARGET_WITHIN_M = 1.0
HOLLOW_CLEAR_OF_RIDGE_M = 3.0


def drill_sites(chemistry_rows: list[dict]) -> list[dict]:
    """Curiosity's drill holes, one per hole: the APXS rows measured on drill tailings,
    named after the hole (e.g. Altadena_tailings -> Altadena), at the first such sol."""
    sites: dict[tuple[float, float], dict] = {}
    for row in sorted(chemistry_rows, key=lambda r: int(r["sol"])):
        name, found, _ = row["target"].partition("_tailings")
        if not found:
            continue
        where = (float(row["x"]), float(row["y"]))
        sites.setdefault(
            where, {"name": name, "sol": int(row["sol"]), "x": where[0], "y": where[1]}
        )
    return list(sites.values())


def check_targets(
    targets: list[dict],
    *,
    drill_sites: list[dict],
    track: list[tuple[float, float]],
    habitat: tuple[float, float],
    walk_radius_m: float,
    zones: list[list[tuple[float, float]]],
    ridges,
) -> None:
    """Refuse targets Curiosity reached or that are not what they say they are.

    Each target is {"id", "name", "kind" ("ridge" or "hollow"), "x", "y"}. Raises
    ValueError naming every broken rule, one line per target and rule."""
    problems = []
    with rasterio.open(ridges) as src:
        ridge_map, transform = src.read(1), src.transform
    for t in targets:
        at = (t["x"], t["y"])
        if math.dist(at, habitat) > walk_radius_m:
            problems.append(
                f"{t['id']}: {math.dist(at, habitat):.0f} m from the habitat, past the walk radius"
            )
        for site in drill_sites:
            away = math.dist(at, (site["x"], site["y"]))
            if away < TARGET_CLEAR_OF_DRILL_M:
                problems.append(f"{t['id']}: {away:.0f} m from drill site {site['name']}")
        to_track = _distance_to_path(at, track)
        if to_track < TARGET_CLEAR_OF_TRACK_M:
            problems.append(f"{t['id']}: {to_track:.0f} m from Curiosity's track")
        if not any(inside_polygon(at, zone) for zone in zones):
            problems.append(f"{t['id']}: outside every boxwork zone")
        if t["kind"] == "ridge" and not _ridge_within(
            ridge_map, transform, at, RIDGE_TARGET_WITHIN_M
        ):
            problems.append(f"{t['id']}: no ridge within {RIDGE_TARGET_WITHIN_M:g} m")
        if t["kind"] == "hollow" and _ridge_within(
            ridge_map, transform, at, HOLLOW_CLEAR_OF_RIDGE_M
        ):
            problems.append(
                f"{t['id']}: sits on a ridge (one within {HOLLOW_CLEAR_OF_RIDGE_M:g} m)"
            )
    if problems:
        raise ValueError("science targets refused:\n" + "\n".join(problems))


def _ridge_within(ridge_map: np.ndarray, transform, at: tuple[float, float], radius: float) -> bool:
    res = transform.a
    col, row = ~transform * at
    reach = math.ceil(radius / res) + 1
    r0, c0 = max(int(row) - reach, 0), max(int(col) - reach, 0)
    window = ridge_map[r0 : int(row) + reach + 1, c0 : int(col) + reach + 1]
    rows, cols = np.nonzero(window == 1)
    centres_x = transform.c + (c0 + cols + 0.5) * res
    centres_y = transform.f - (r0 + rows + 0.5) * res
    return bool((np.hypot(centres_x - at[0], centres_y - at[1]) <= radius).any())


def _distance_to_path(at: tuple[float, float], path: list[tuple[float, float]]) -> float:
    p = np.asarray(at, dtype=float)
    if len(path) == 1:
        return math.dist(at, path[0])
    best = math.inf
    for a, b in zip(path, path[1:], strict=False):
        a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
        span = b - a
        length2 = float(span @ span)
        t = 0.0 if length2 == 0 else min(max(float((p - a) @ span) / length2, 0.0), 1.0)
        best = min(best, float(np.linalg.norm(p - (a + t * span))))
    return best


def inside_polygon(at: tuple[float, float], polygon: list[tuple[float, float]]) -> bool:
    """Ray casting: is the point inside the polygon?"""
    x, y = at
    inside = False
    for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1], strict=True):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside
