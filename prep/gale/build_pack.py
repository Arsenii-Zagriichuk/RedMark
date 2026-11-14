"""Build the Gale walk-area crop pack (P2-01).

    REDMARK_DATA=~/redmark-data uv run python -m prep.gale.build_pack

Reads, from $REDMARK_DATA (file names as published):
  MSL_Gale_Orthophoto_Mosaic_25cm_v3.tif      the 25 cm photo map (the base map)
  MSL_Gale_DEM_Mosaic_1m_v3.tif               the 1 m terrain
  THEMIS_TI_Mosaic_Quant_30S120E_100mpp.cub   THEMIS thermal inertia, 100 m
  places/localized_pos.csv                    Curiosity's localised positions (PLACES)
and downloads once, if missing:
  gale/source/crism/frt0000b6f1_07_sr165j_mtr3.img, .hdr
                                              CRISM summary parameters, 18 m
  gale/source/apxs/msl_apxs_concentrations_*.csv
                                              Curiosity's APXS chemistry, every table
                                              overlapping the sols it spent in the crops
  places/localized_interp.csv                 Curiosity's position at every drive (PLACES)
and writes, under $REDMARK_DATA/gale/crops/:
  photo-map-25cm.tif, terrain-1m.tif, thermal-inertia-100m.tif, crism-summary-18m.tif
                        each source cut to the walk area plus a margin, on its own grid
  rover-positions.csv   Curiosity's localised positions inside the crops
  chemistry-apxs.csv    APXS measurements inside the crops, at the rover's position
  overlays/*.png        one overlay per source on the base map, to check by eye
  pack.json             crop bounds, frame check, offsets and provenance
and, in the repo, sites/gale.yaml, the Gale entries in prep/data-manifest.yaml
and copies of the overlays in prep/gale/evidence/.

The pack is built in gale/crops.next/ and replaces gale/crops/ only if every
check passes; the repo files are written after that. A failed check leaves the
published pack, the site config and the manifest as they were.

Walk area and margins come from prep/gale/walk_area.yaml, so a new walk area is
a rerun, not a code change. Only the crops are read once they exist, so a rerun
does not need the 50 GB photo map.
"""

import csv
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import rasterio
import truststore
import yaml
from rasterio.windows import from_bounds

from contracts.models.site import SiteConfig
from contracts.paths import REPO_ROOT, data_root
from prep.common import (
    Bounds,
    download,
    manifest_entry,
    publish_stage,
    sha256,
    start_stage,
    update_manifest,
)
from prep.gale import overlays
from prep.gale.crop import crop_is_current, crop_on_source_grid
from prep.gale.pack import (
    PixelGrid,
    apxs_points,
    apxs_tables_for,
    band_gaps,
    best_move,
    check_apxs_placement,
    compare_heights,
    grow,
    offset_in_pixels,
    photo_move_on_terrain,
    places_grids,
    rover_positions,
    rover_sols_inside,
    rover_track,
    site_config,
    slope_degrees,
    walk_area,
)
from prep.gale.rasters import read_at, read_window

PROJECTION = "+proj=eqc +lat_ts=0 +lon_0=0 +R=3396190 +units=m +no_defs"
PLACES = "places/localized_pos.csv"
PLACES_URL = (
    "https://planetarydata.jpl.nasa.gov/img/data/msl/msl_places/data_localizations/"
    "localized_pos.csv"
)
SOURCES = {
    "photo_map": {
        "file": "MSL_Gale_Orthophoto_Mosaic_25cm_v3.tif",
        "crop": "gale/crops/photo-map-25cm.tif",
        "name": "MSL Gale orthophoto mosaic, 25 cm, v3 (the base map)",
        "url": "https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/"
        "MSL_Gale_Orthophoto_Mosaic_25cm_v3.tif",
        "credit": "Calef, F. J. III and Parker, T. (2016), MSL Gale Merged Orthophoto "
        "Mosaic, USGS Astrogeology Science Center; HiRISE: NASA/JPL-Caltech/University "
        "of Arizona",
    },
    "terrain": {
        "file": "MSL_Gale_DEM_Mosaic_1m_v3.tif",
        "crop": "gale/crops/terrain-1m.tif",
        "name": "MSL Gale DEM mosaic, 1 m, v3",
        "url": "https://planetarymaps.usgs.gov/mosaic/Mars/MSL/MSL_Gale_DEM_Mosaic_1m_v3.tif",
        "credit": "Calef, F. J. III and Parker, T. (2016), MSL Gale Merged DEM 1m v3, "
        "USGS Astrogeology Science Center.",
    },
    "thermal_inertia": {
        "file": "THEMIS_TI_Mosaic_Quant_30S120E_100mpp.cub",
        "crop": "gale/crops/thermal-inertia-100m.tif",
        "name": "THEMIS quantitative thermal inertia mosaic, 30S120E tile, 100 m",
        "url": "https://astrogeology.usgs.gov/search/map/"
        "themis_thermal_inertia_mosaic_quantitative_30s120e_100mpp",
        "credit": "THEMIS quantitative thermal inertia mosaic: USGS Astrogeology Science "
        "Center; THEMIS: NASA/JPL-Caltech/Arizona State University",
    },
}
PLACES_INTERP = "places/localized_interp.csv"
PLACES_INTERP_URL = (
    "https://planetarydata.jpl.nasa.gov/img/data/msl/msl_places/data_localizations/"
    "localized_interp.csv"
)
PLACES_CREDIT = "MSL PLACES localization archive, NASA/JPL-Caltech, PDS Imaging Node."
# The one CRISM targeted cube covering the whole crop (FRT0000B6F1, 9 Jul 2008,
# 18 m), found with the PDS ODE footprint search. Its refined summary
# parameters are the per-pixel mineral indices; P2-03 picks the highlights.
CRISM_URL = (
    "https://pds-geosciences.wustl.edu/mro/mro-m-crism-5-rdr-mptargeted-v1/mrocr_4001/"
    "mtrdr/2008/2008_191/frt0000b6f1/"
)
CRISM = {
    "file": "gale/source/crism/frt0000b6f1_07_sr165j_mtr3.img",
    # The ENVI header places the cube; GDAL reads it next to the .img.
    "header": "gale/source/crism/frt0000b6f1_07_sr165j_mtr3.hdr",
    "crop": "gale/crops/crism-summary-18m.tif",
    "name": "CRISM MTRDR refined spectral summary parameters, FRT0000B6F1, 18 m",
    "credit": "CRISM Map-projected Targeted Reduced Data Records (MTRDR), "
    "MRO-M-CRISM-5-RDR-MPTARGETED-V1.0: NASA/JPL-Caltech/JHU-APL, PDS Geosciences Node",
}
APXS_URL = "https://pds-geosciences.wustl.edu/msl/msl-m-apxs-4_5-rdr-v1/mslapx_1xxx/extras/"
# Every numbered concentration table in the archive (listed 14 Nov 2026). The
# build reads those overlapping the sols Curiosity spent inside the crops, and
# keeps each measurement by where the rover stood. Sols before 1294 are in
# other tables, from long before Curiosity reached the crops (sol 3843).
APXS_TABLES = [
    f"msl_apxs_concentrations_{first}_{last}.csv"
    for first, last in (
        (1294, 1417), (1418, 1869), (1870, 2003), (2004, 2127), (2128, 2224),
        (2225, 2358), (2359, 2482), (2483, 2579), (2580, 2713), (2714, 2837),
        (2838, 2934), (2935, 3068), (3069, 3192), (3193, 4133), (4134, 4257),
        (4258, 4354), (4355, 4488), (4489, 4612), (4613, 4709), (4710, 4843),
    )
]  # fmt: skip
APXS_DIR = "gale/source/apxs"
APXS_CREDIT = "MSL APXS RDR (MSL-M-APXS-4/5-RDR-V1.0), NASA/JPL-Caltech, PDS Geosciences Node"
OUT = "gale/crops"
# The candidate pack is built here and replaces OUT only once every check passes.
STAGE = "gale/crops.next"
# The data-manifest entries this pack owns: its own folder and its sources at the
# data root. A rebuild replaces them all, so a source it stops using drops out.
MANIFEST_OWNED = ("gale/", "MSL_Gale_", "THEMIS_TI_", PLACES, PLACES_INTERP)
EVIDENCE = REPO_ROOT / "prep" / "gale" / "evidence"
# Frame check: the terrain under Curiosity's stops must match PLACES' elevation
# within half a metre at 9 in 10 stops, with the median under half a metre.
HEIGHT_WITHIN_M = 0.5
HEIGHT_SHARE = 0.9
# The THEMIS offset search: every 25 m shift up to 300 m (three THEMIS pixels) each way.
OFFSET_STEP_M = 25.0
OFFSET_SEARCH_M = 300.0
# The CRISM offset search: CRISM's 770 nm reflectance against the photo map's
# brightness at 6 m, every move up to 300 m each way. CRISM's pointing is not
# tied to HiRISE, so the best move is applied when the match is clear, r of
# 0.6 or more; THEMIS's best is |r| 0.34 and stays unapplied.
CRISM_STEP_M = 6.0
CRISM_SEARCH_M = 300.0
CRISM_MIN_R = 0.6
# Frame check on the photo map itself: its brightness must line up with the
# terrain's shading (both from the same HiRISE stereo images) within 5 m, at
# 2 m pixels, searching 100 m each way. A whole-pixel shift of the photo map
# passes the grid and height checks; this one catches it.
PHOTO_STEP_M = 2.0
PHOTO_SEARCH_M = 100.0
PHOTO_WITHIN_M = 5.0
# The walk-area figures: ground in the 100 m square round the habitat and base camp.
SQUARE_M = 100.0
STEEP_DEG = 10.0


def main() -> None:
    if not os.environ.get("REDMARK_DATA"):
        sys.exit("set REDMARK_DATA to the shared data folder; the pack never goes in the stub data")
    # Verify HTTPS with the system's certificates, as the Jezero pack does.
    truststore.inject_into_ssl()
    build(data_root())


def build(root: Path) -> None:
    spec = yaml.safe_load((REPO_ROOT / "prep" / "gale" / "walk_area.yaml").read_text())
    habitat = (spec["habitat"]["x"], spec["habitat"]["y"])
    base_camp = (spec["base_camp"]["x"], spec["base_camp"]["y"])
    walk = walk_area(habitat, spec["walk_radius_m"])
    asked = grow(walk, spec["crop_margin_m"])
    out = root / OUT
    stage = root / STAGE
    start_stage(out, stage, reuse="*.tif")  # crops are slow to cut; the rest is rewritten

    for name in ("file", "header"):
        download(CRISM_URL + Path(CRISM[name]).name, root / CRISM[name])
    download(PLACES_INTERP_URL, root / PLACES_INTERP)
    rover_sols = rover_sols_inside(root / PLACES_INTERP, asked)
    tables = apxs_tables_for(APXS_TABLES, rover_sols)
    for table in tables:
        download(APXS_URL + table, root / APXS_DIR / table)
    apxs = [f"{APXS_DIR}/{t}" for t in tables]
    checksums = _source_checksums(
        root,
        [s["file"] for s in SOURCES.values()]
        + [PLACES, PLACES_INTERP, CRISM["file"], CRISM["header"]]
        + apxs,
    )
    crops: dict[str, dict] = {}
    for key, source in SOURCES.items():
        crop = root / _staged(source["crop"])
        source_id = f"{source['file']} sha256:{checksums[source['file']]} bounds:{asked}"
        if crop_is_current(crop, source_id):
            with rasterio.open(crop) as src:
                covered = tuple(src.bounds)
        else:
            print(f"cropping {source['file']}")
            covered = crop_on_source_grid(root / source["file"], asked, crop, PROJECTION, source_id)
        with rasterio.open(crop) as src:
            res = src.res[0]
        crops[key] = {"path": _staged(source["crop"]), "bounds": list(covered), "res_m": res}
        print(f"{key}: {source['crop']} covers {covered} at {res:g} m")

    crism_offset = _crism_offset(root, crops, asked)
    print(f"CRISM offset: {json.dumps(crism_offset)}")
    move = crism_offset["move_m"] if crism_offset["applied"] else [0.0, 0.0]
    crism = root / _staged(CRISM["crop"])
    source_id = f"{CRISM['file']} sha256:{checksums[CRISM['file']]} bounds:{asked} move:{move}"
    if not crop_is_current(crism, source_id):
        print(f"cropping {CRISM['file']}")
        crop_on_source_grid(root / CRISM["file"], asked, crism, PROJECTION, source_id, tuple(move))
    with rasterio.open(crism) as src:
        crops["crism"] = {
            "path": _staged(CRISM["crop"]),
            "bounds": list(src.bounds),
            "res_m": src.res[0],
            "bands": list(src.descriptions),
        }
    print(f"crism: {CRISM['crop']} covers {crops['crism']['bounds']}, moved {move} m")

    track = rover_track(root / PLACES_INTERP)
    chemistry = apxs_points([root / t for t in apxs], track, asked)
    with (stage / "chemistry-apxs.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(chemistry[0]))
        writer.writeheader()
        writer.writerows(chemistry)
    print(f"APXS measurements in the crops: {len(chemistry)}, sols {rover_sols} read")
    placement_check = check_apxs_placement([root / t for t in apxs], track)
    print(f"APXS placement by sol against file names: {json.dumps(placement_check)}")

    positions = rover_positions(root / PLACES, asked)
    with (stage / "rover-positions.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["sol", "site", "drive", "x", "y", "z"])
        writer.writeheader()
        writer.writerows(positions)
    print(f"rover positions in the crops: {len(positions)}")

    frame_check = _frame_check(root, crops, positions)
    print(f"frame check: {json.dumps(frame_check)}")
    crism_coverage = _crism_coverage(root, crops, walk, habitat, spec["walk_radius_m"])
    gaps = {b: c for b, c in crism_coverage["cells_without_data"].items() if c["walk_radius"]}
    print(f"CRISM bands with gaps inside the walk radius: {json.dumps(gaps)}")
    walk_area_figures = _walk_area_figures(root, crops, habitat, base_camp, positions)
    print(f"walk-area figures: {json.dumps(walk_area_figures)}")
    ti_offset = _thermal_inertia_offset(root, crops)
    print(f"thermal inertia offset (not corrected): {json.dumps(ti_offset)}")

    overlay_dir = stage / "overlays"
    overlay_dir.mkdir(parents=True, exist_ok=True)
    overlays.photo_map(root, crops, walk, habitat, base_camp, positions, frame_check, overlay_dir)
    overlays.terrain(root, crops, walk, habitat, overlay_dir)
    overlays.thermal_inertia(root, crops, walk, habitat, ti_offset, overlay_dir)
    overlays.crism(root, crops, walk, habitat, crism_offset, overlay_dir)
    overlays.chemistry(root, crops, walk, habitat, positions, chemistry, overlay_dir)

    pack = {
        "walk_area": list(walk),
        "crop_bounds_asked": list(asked),
        "habitat": list(habitat),
        "base_camp": list(base_camp),
        "crops": {k: v | {"path": v["path"].replace(STAGE, OUT, 1)} for k, v in crops.items()},
        "rover_positions": f"{OUT}/rover-positions.csv",
        "chemistry": {
            "path": f"{OUT}/chemistry-apxs.csv",
            "count": len(chemistry),
            "rover_sols_inside": list(rover_sols),
            "placement_check": placement_check,
            "tables_read": tables,
            "position": "the rover's PLACES pose after its last drive before the measurement's "
            "sol; APXS is on the arm, so the target is within about 2 m",
        },
        "frame_check": frame_check,
        "thermal_inertia_offset": ti_offset,
        "crism_offset": crism_offset,
        "crism_coverage": crism_coverage,
        "walk_area_figures": walk_area_figures,
        "provenance": {
            "script": "prep/gale/build_pack.py",
            "commit": _git_commit(),
            "inputs": [{"path": p, "sha256": d} for p, d in sorted(checksums.items())]
            + [
                {
                    "path": "prep/gale/walk_area.yaml",
                    "sha256": sha256(REPO_ROOT / "prep/gale/walk_area.yaml"),
                }
            ],
        },
    }
    (stage / "pack.json").write_text(json.dumps(pack, indent=2) + "\n")

    if not frame_check["passed"]:
        sys.exit(
            "frame check failed: PLACES and the crops do not share one frame. "
            f"The candidate pack is in {stage}; the published pack is unchanged."
        )
    publish_stage(stage, out)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    for png in sorted((out / "overlays").glob("*.png")):
        shutil.copy(png, EVIDENCE / png.name)
    _write_site_config(spec, habitat, base_camp)
    _write_manifest(root, checksums, tables)
    print(f"pack written to {out}")


def _staged(path: str) -> str:
    """Where a pack file is written while the candidate pack is checked."""
    return path.replace(OUT, STAGE, 1)


def _frame_check(root: Path, crops: dict, positions: list[dict]) -> dict:
    """Do Curiosity's PLACES positions and our crops share one frame?

    Three checks. PLACES' orthophoto and terrain grids must be our maps'
    grids, a whole number of pixels apart. The terrain's height at each of
    Curiosity's stops must match PLACES' elevation there: a whole-pixel shift
    of the terrain would pass the first check but fail this one on slopes.
    And the photo map must line up with the terrain's shading, which pins the
    photo map in place: a whole-pixel shift of it would pass the other two.
    """
    fitted = places_grids(root / PLACES)
    result: dict = {"passed": True}
    with rasterio.open(root / crops["terrain"]["path"]) as src:
        terrain = [
            float(v[0]) if v[0] != src.nodata else float("nan")
            for v in src.sample([(p["x"], p["y"]) for p in positions])
        ]
    heights = compare_heights([p["z"] for p in positions], terrain, within_m=HEIGHT_WITHIN_M)
    result["heights"] = heights
    result["passed"] &= (
        abs(heights["median_m"]) < HEIGHT_WITHIN_M and heights["share_within"] >= HEIGHT_SHARE
    )
    # A crop is a whole-pixel window on its source's grid, so it has that grid.
    for kind, key in (("map", "photo_map"), ("dem", "terrain")):
        with rasterio.open(root / crops[key]["path"]) as src:
            ours = PixelGrid(src.bounds.left, src.bounds.top, src.res[0])
        col, row = offset_in_pixels(fitted[kind], on=ours)
        off_grid_m = max(abs(col - round(col)), abs(row - round(row))) * ours.res
        result[key] = {
            "places_grid": [fitted[kind].left, fitted[kind].top, fitted[kind].res],
            "offset_px": [round(col, 4), round(row, 4)],
            "off_grid_m": round(off_grid_m, 4),
        }
        # Within a centimetre of whole pixels: the same grid.
        result["passed"] &= off_grid_m < 0.01
    photo, photo_grid = read_at(root / crops["photo_map"]["path"], PHOTO_STEP_M)
    heights, terrain_grid = read_at(root / crops["terrain"]["path"], PHOTO_STEP_M)
    found = photo_move_on_terrain(photo, photo_grid, heights, terrain_grid, PHOTO_SEARCH_M)
    off_m = float(np.hypot(*found["move_m"]))
    result["photo_on_terrain"] = {
        # Move the terrain east by x and north by y (metres) to line up with the photo.
        "move_m": found["move_m"],
        "off_m": round(off_m, 2),
        "within_m": PHOTO_WITHIN_M,
        "light_azimuth_deg": found["azimuth_deg"],
        "r_best": round(found["r"], 3),
        "r_unmoved": round(found["r_unmoved"], 3),
    }
    result["passed"] &= off_m <= PHOTO_WITHIN_M
    return result


def _crism_coverage(root: Path, crops: dict, walk: Bounds, habitat, radius_m: float) -> dict:
    """Cells without data in each CRISM band: in the crop, the walk area and the walk radius.

    The cube's edge is ragged, and some bands have gaps of their own inside it.
    """
    with rasterio.open(root / crops["crism"]["path"]) as src:
        cube = src.read(masked=True)
        names = list(src.descriptions)
        rows, cols = np.mgrid[0 : src.height, 0 : src.width]
        xs, ys = rasterio.transform.xy(src.transform, rows.ravel(), cols.ravel())
    x = np.asarray(xs).reshape(rows.shape)
    y = np.asarray(ys).reshape(rows.shape)
    regions = {
        "crop": np.ones(rows.shape, bool),
        "walk_area": (walk[0] <= x) & (x <= walk[2]) & (walk[1] <= y) & (y <= walk[3]),
        "walk_radius": np.hypot(x - habitat[0], y - habitat[1]) <= radius_m,
    }
    return {"cells": {r: int(m.sum()) for r, m in regions.items()}} | band_gaps(
        cube, names, regions
    )


def _walk_area_figures(root: Path, crops: dict, habitat, base_camp, positions) -> dict:
    """The figures behind the walk-area choice in walk_area.yaml, measured on the terrain."""
    figures: dict = {}
    for name, (x, y) in (("habitat", habitat), ("base_camp", base_camp)):
        half = SQUARE_M / 2
        heights, extent = read_window(
            root / crops["terrain"]["path"], (x - half, y - half, x + half, y + half), True
        )
        slope = slope_degrees(heights, 1.0)[1:-1, 1:-1]  # edge cells have one-sided gradients
        figures[name] = {
            "mean_slope_deg": round(float(np.nanmean(slope)), 1),
            "steeper_than_10_deg_share": round(float(np.nanmean(slope > STEEP_DEG)), 3),
            "nearest_curiosity_position_m": round(
                min(float(np.hypot(p["x"] - x, p["y"] - y)) for p in positions), 0
            ),
        }
    figures["base_camp_from_habitat_m"] = round(
        float(np.hypot(base_camp[0] - habitat[0], base_camp[1] - habitat[1])), 0
    )
    figures["square_m"] = SQUARE_M
    return figures


def _thermal_inertia_offset(root: Path, crops: dict) -> dict:
    """How far THEMIS would have to move to line up best with the base map.

    THEMIS at 100 m is compared, by correlation, with the photo map's
    brightness and the terrain's slope, both averaged to 25 m, for every shift
    up to OFFSET_SEARCH_M. Recorded, not applied: the correlations are weak.
    """
    ti, ti_grid = read_at(root / crops["thermal_inertia"]["path"], 100.0)
    brightness, photo_grid = read_at(root / crops["photo_map"]["path"], OFFSET_STEP_M)
    heights, terrain_grid = read_at(root / crops["terrain"]["path"], OFFSET_STEP_M)
    dy, dx = np.gradient(heights, OFFSET_STEP_M)
    result: dict = {"search_m": OFFSET_SEARCH_M, "step_m": OFFSET_STEP_M}
    for name, fine, grid in (
        ("photo_brightness", brightness, photo_grid),
        ("slope", np.degrees(np.arctan(np.hypot(dx, dy))), terrain_grid),
    ):
        found = best_move(ti, ti_grid, fine, grid, OFFSET_SEARCH_M)
        result[name] = {
            # Move THEMIS east by x and north by y (metres) to line up best.
            "best_move_m": found["move_m"],
            "r_best": round(found["r"], 3),
            "r_unmoved": round(found["r_unmoved"], 3),
        }
    return result


def _crism_offset(root: Path, crops: dict, asked: Bounds) -> dict:
    """How far CRISM must move to line up with the base map, and whether to move it.

    CRISM's 770 nm reflectance (R770) and the photo map's brightness both
    show albedo, so they correlate where the two line up. Every move in
    CRISM_STEP_M steps up to CRISM_SEARCH_M is tried from where CRISM's ENVI
    header places the cube. (Its PDS3 label, read by GDAL's PDS driver, puts
    the cube one pixel further west and north; the measured move corrects
    either.)
    """
    with rasterio.open(root / CRISM["file"]) as src:
        window = from_bounds(*asked, transform=src.transform).round_offsets().round_lengths()
        band = src.descriptions.index("R770") + 1
        r770 = src.read(band, window=window, masked=True).astype(np.float64).filled(np.nan)
        transform = src.window_transform(window)
        grid = PixelGrid(transform.c, transform.f, src.res[0])
    r770[np.abs(r770) > 1e3] = np.nan  # fill values other than the header's no-data
    brightness, photo_grid = read_at(root / crops["photo_map"]["path"], CRISM_STEP_M)
    found = best_move(r770, grid, brightness, photo_grid, CRISM_SEARCH_M)
    return {
        "compared": "CRISM R770 against the photo map's brightness",
        "search_m": CRISM_SEARCH_M,
        "step_m": CRISM_STEP_M,
        # Move CRISM east by x and north by y (metres) to line up best.
        "move_m": found["move_m"],
        "r_best": round(found["r"], 3),
        "r_unmoved": round(found["r_unmoved"], 3),
        "applied": found["r"] >= CRISM_MIN_R,
    }


def _write_site_config(spec: dict, habitat, base_camp) -> None:
    path = REPO_ROOT / "sites" / "gale.yaml"
    # Fields later tickets own (the sol, targets, checkpoints, other files) are kept.
    current = yaml.safe_load(path.read_text()) if path.exists() else {}
    files = {key: source["crop"] for key, source in SOURCES.items()} | {
        "crism": CRISM["crop"],
        "chemistry": f"{OUT}/chemistry-apxs.csv",
        "rover_positions": f"{OUT}/rover-positions.csv",
    }
    config = site_config(
        name=spec["name"],
        projection=PROJECTION,
        habitat=habitat,
        base_camp=base_camp,
        walk_radius_m=spec["walk_radius_m"],
        files=files,
        current=current,
    )
    SiteConfig.model_validate(config)
    header = (
        "# Written by prep/gale/build_pack.py (P2-01). Do not edit by hand: change\n"
        "# prep/gale/walk_area.yaml and rerun. A rerun rewrites the geometry and the\n"
        "# pack's own files; the sol, science targets, checkpoints and other files stay.\n"
    )
    path.write_text(header + yaml.safe_dump(config, sort_keys=False, allow_unicode=True))


def _write_manifest(root: Path, checksums: dict[str, str], tables: list[str]) -> None:
    entries = [
        manifest_entry(
            root,
            source["file"],
            name=source["name"],
            source_url=source["url"],
            credit=source["credit"],
            checksum=checksums[source["file"]],
        )
        for source in SOURCES.values()
    ] + [
        manifest_entry(
            root,
            PLACES,
            name="MSL PLACES rover localizations (localized_pos.csv)",
            source_url=PLACES_URL,
            credit=PLACES_CREDIT,
            checksum=checksums[PLACES],
        ),
        manifest_entry(
            root,
            PLACES_INTERP,
            name="MSL PLACES rover positions at every drive (localized_interp.csv)",
            source_url=PLACES_INTERP_URL,
            credit=PLACES_CREDIT,
            checksum=checksums[PLACES_INTERP],
        ),
    ]
    entries += [
        manifest_entry(
            root,
            CRISM[name],
            name=CRISM["name"] + label,
            source_url=CRISM_URL + Path(CRISM[name]).name,
            credit=CRISM["credit"],
            checksum=checksums[CRISM[name]],
        )
        for name, label in (("file", ""), ("header", " (ENVI header)"))
    ]
    entries += [
        manifest_entry(
            root,
            f"{APXS_DIR}/{table}",
            name="MSL APXS concentrations, sols {} to {}".format(*table[:-4].split("_")[-2:]),
            source_url=APXS_URL + table,
            credit=APXS_CREDIT,
            checksum=checksums[f"{APXS_DIR}/{table}"],
        )
        for table in tables
    ]
    update_manifest(entries, owned=MANIFEST_OWNED)


def _source_checksums(root: Path, files: list[str]) -> dict[str, str]:
    """SHA-256 of each source, cached by size and modification time (the photo map is 50 GB)."""
    # Outside the pack, so publishing a candidate pack never drops it.
    cache_path = root / "gale" / "source-checksums.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    result = {}
    for name in files:
        stat = (root / name).stat()
        key = f"{stat.st_size}:{stat.st_mtime_ns}"
        if cache.get(name, {}).get("key") != key:
            print(f"checksumming {name}")
            cache[name] = {"key": key, "sha256": sha256(root / name)}
        result[name] = cache[name]["sha256"]
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, indent=2) + "\n")
    return result


def _git_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


if __name__ == "__main__":
    main()
