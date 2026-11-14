"""Build the Gale walk-area crop pack (P2-01).

    REDMARK_DATA=~/redmark-data uv run python -m prep.gale.build_pack

Reads, from $REDMARK_DATA (file names as published):
  MSL_Gale_Orthophoto_Mosaic_25cm_v3.tif      the 25 cm photo map (the base map)
  MSL_Gale_DEM_Mosaic_1m_v3.tif               the 1 m terrain
  THEMIS_TI_Mosaic_Quant_30S120E_100mpp.cub   THEMIS thermal inertia, 100 m
  places/localized_pos.csv                    Curiosity's positions (PLACES)
and writes, under $REDMARK_DATA/gale/crops/:
  photo-map-25cm.tif, terrain-1m.tif, thermal-inertia-100m.tif
                        each source cut to the walk area plus a margin, on its own grid
  rover-positions.csv   Curiosity's positions inside the crops
  overlays/*.png        one overlay per source on the base map, to check by eye
  pack.json             crop bounds, frame check and provenance
and, in the repo, sites/gale.yaml, the Gale entries in prep/data-manifest.yaml
and copies of the overlays in prep/gale/evidence/.

Walk area and margins come from prep/gale/walk_area.yaml, so a new walk area is
a rerun, not a code change. CRISM and Curiosity chemistry join in a later pull
request, once downloaded.
"""

import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import matplotlib
import numpy as np
import rasterio
import yaml
from rasterio.enums import Resampling

from contracts.models.data_manifest import DataManifest
from contracts.models.site import SiteConfig
from contracts.paths import REPO_ROOT, data_root
from prep.gale.crop import Bounds, crop_is_current, crop_on_source_grid
from prep.gale.pack import (
    PixelGrid,
    best_shift,
    compare_heights,
    grow,
    offset_in_pixels,
    places_grids,
    rover_positions,
    site_config,
    walk_area,
)

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Circle, Rectangle  # noqa: E402

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
OUT = "gale/crops"
EVIDENCE = REPO_ROOT / "prep" / "gale" / "evidence"
OVERLAY_PX = 2000  # long side of the downsampled base map in each overlay
ZOOM_HALF_M = 300  # half-width of the full-detail zoom panels
# Frame check: the terrain under Curiosity's stops must match PLACES' elevation
# within half a metre at 9 in 10 stops, with the median under half a metre.
HEIGHT_WITHIN_M = 0.5
HEIGHT_SHARE = 0.9
# The THEMIS offset search: every 25 m shift up to 300 m (three THEMIS pixels) each way.
OFFSET_STEP_M = 25.0
OFFSET_SEARCH_M = 300.0


def main() -> None:
    if not os.environ.get("REDMARK_DATA"):
        sys.exit("set REDMARK_DATA to the shared data folder; the pack never goes in the stub data")
    build(data_root())


def build(root: Path) -> None:
    spec = yaml.safe_load((REPO_ROOT / "prep" / "gale" / "walk_area.yaml").read_text())
    habitat = (spec["habitat"]["x"], spec["habitat"]["y"])
    base_camp = (spec["base_camp"]["x"], spec["base_camp"]["y"])
    walk = walk_area(habitat, spec["walk_radius_m"])
    asked = grow(walk, spec["crop_margin_m"])
    out = root / OUT

    checksums = _source_checksums(root, [s["file"] for s in SOURCES.values()] + [PLACES])
    crops: dict[str, dict] = {}
    for key, source in SOURCES.items():
        crop = root / source["crop"]
        source_id = f"{source['file']} sha256:{checksums[source['file']]} bounds:{asked}"
        if crop_is_current(crop, source_id):
            with rasterio.open(crop) as src:
                covered = tuple(src.bounds)
        else:
            print(f"cropping {source['file']}")
            covered = crop_on_source_grid(root / source["file"], asked, crop, PROJECTION, source_id)
        with rasterio.open(crop) as src:
            res = src.res[0]
        crops[key] = {"path": source["crop"], "bounds": list(covered), "res_m": res}
        print(f"{key}: {source['crop']} covers {covered} at {res:g} m")

    positions = rover_positions(root / PLACES, asked)
    with (out / "rover-positions.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["sol", "site", "drive", "x", "y", "z"])
        writer.writeheader()
        writer.writerows(positions)
    print(f"rover positions in the crops: {len(positions)}")

    frame_check = _frame_check(root, crops, positions)
    print(f"frame check: {json.dumps(frame_check)}")
    ti_offset = _thermal_inertia_offset(root, crops)
    print(f"thermal inertia offset (not corrected): {json.dumps(ti_offset)}")

    overlays = out / "overlays"
    overlays.mkdir(parents=True, exist_ok=True)
    _photo_map_overlay(root, crops, walk, habitat, base_camp, positions, frame_check, overlays)
    _terrain_overlay(root, crops, walk, habitat, overlays)
    _thermal_inertia_overlay(root, crops, walk, habitat, ti_offset, overlays)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    for png in sorted(overlays.glob("*.png")):
        shutil.copy(png, EVIDENCE / png.name)

    pack = {
        "walk_area": list(walk),
        "crop_bounds_asked": list(asked),
        "habitat": list(habitat),
        "base_camp": list(base_camp),
        "crops": crops,
        "rover_positions": f"{OUT}/rover-positions.csv",
        "frame_check": frame_check,
        "thermal_inertia_offset": ti_offset,
        "provenance": {
            "script": "prep/gale/build_pack.py",
            "commit": _git_commit(),
            "inputs": [{"path": p, "sha256": d} for p, d in sorted(checksums.items())]
            + [
                {
                    "path": "prep/gale/walk_area.yaml",
                    "sha256": _sha256(REPO_ROOT / "prep/gale/walk_area.yaml"),
                }
            ],
        },
    }
    (out / "pack.json").write_text(json.dumps(pack, indent=2) + "\n")

    _write_site_config(spec, habitat, base_camp)
    _write_manifest(root, checksums)
    if not frame_check["passed"]:
        sys.exit("frame check failed: PLACES and the crops do not share one frame")
    print(f"pack written to {out}")


def _frame_check(root: Path, crops: dict, positions: list[dict]) -> dict:
    """Do Curiosity's PLACES positions and our crops share one frame?

    Two checks. PLACES' orthophoto and terrain grids must be our maps' grids,
    a whole number of pixels apart. And the terrain's height at each of
    Curiosity's stops must match PLACES' elevation there: a whole-pixel shift
    between the frames would pass the first check but fail this one on slopes.
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
    for kind, key in (("map", "photo_map"), ("dem", "terrain")):
        with rasterio.open(root / SOURCES[key]["file"]) as src:
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
    return result


def _thermal_inertia_offset(root: Path, crops: dict) -> dict:
    """How far THEMIS would have to move to line up best with the base map.

    THEMIS at 100 m is compared, by correlation, with the photo map's
    brightness and the terrain's slope, both averaged to 25 m, for every shift
    up to OFFSET_SEARCH_M. Recorded, not applied: the correlations are weak.
    """
    ti, ti_grid = _read_at(root / crops["thermal_inertia"]["path"], 100.0)
    brightness, photo_grid = _read_at(root / crops["photo_map"]["path"], OFFSET_STEP_M)
    heights, terrain_grid = _read_at(root / crops["terrain"]["path"], OFFSET_STEP_M)
    dy, dx = np.gradient(heights, OFFSET_STEP_M)
    result: dict = {"search_m": OFFSET_SEARCH_M, "step_m": OFFSET_STEP_M}
    for name, fine, grid in (
        ("photo_brightness", brightness, photo_grid),
        ("slope", np.degrees(np.arctan(np.hypot(dx, dy))), terrain_grid),
    ):
        col, row = offset_in_pixels(PixelGrid(ti_grid.left, ti_grid.top, grid.res), on=grid)
        found = best_shift(
            ti,
            fine,
            factor=round(ti_grid.res / grid.res),
            origin_px=(round(col), round(row)),
            search_px=round(OFFSET_SEARCH_M / OFFSET_STEP_M),
        )
        d_col, d_row = found["shift_px"]
        result[name] = {
            # Move THEMIS east by x and north by y (metres) to line up best.
            "best_move_m": [d_col * OFFSET_STEP_M, -d_row * OFFSET_STEP_M],
            "r_best": round(found["r"], 3),
            "r_unmoved": round(found["r_unshifted"], 3),
        }
    return result


def _read_at(path: Path, res_m: float) -> tuple[np.ndarray, PixelGrid]:
    """A crop averaged to `res_m` pixels, with NaN for no data, and its grid."""
    with rasterio.open(path) as src:
        factor = res_m / src.res[0]
        shape = (round(src.height / factor), round(src.width / factor))
        data = src.read(1, out_shape=shape, resampling=Resampling.average, masked=True)
        grid = PixelGrid(src.bounds.left, src.bounds.top, src.width * src.res[0] / shape[1])
    data = data.astype(np.float64)
    if src.dtypes[0] == "uint8":  # the photo map's 0 is no data
        data = np.ma.masked_equal(data, 0)
    return data.filled(np.nan), grid


def _photo_map_overlay(root, crops, walk, habitat, base_camp, positions, check, folder) -> None:
    image, extent = _read_small(root / crops["photo_map"]["path"])
    fig, (wide, zoom) = plt.subplots(1, 2, figsize=(22, 11), gridspec_kw={"wspace": 0.08})
    for ax in (wide, zoom):
        _show_gray(ax, image, extent)
        ax.plot([p["x"] for p in positions], [p["y"] for p in positions], "-", c="red", lw=1)
        ax.plot([p["x"] for p in positions], [p["y"] for p in positions], "o", c="red", ms=2.5)
        ax.plot(*habitat, "*", c="cyan", ms=16, mec="black", label="habitat")
        ax.plot(*base_camp, "^", c="yellow", ms=10, mec="black", label="base camp")
    _walk_area_patches(wide, walk, habitat)
    for p in positions[:: max(1, len(positions) // 12)]:
        wide.annotate(
            f"sol {p['sol']}",
            (p["x"], p["y"]),
            color="red",
            fontsize=8,
            xytext=(4, 4),
            textcoords="offset points",
        )
    wide.plot([], [], "-o", c="red", ms=2.5, label="Curiosity (PLACES)")
    wide.legend(loc="lower left")
    wide.set_title("Base map: walk area, habitat, base camp and Curiosity's positions")
    # Full detail round Curiosity's stop nearest the habitat.
    nearest = min(positions, key=lambda p: np.hypot(p["x"] - habitat[0], p["y"] - habitat[1]))
    cx, cy = nearest["x"], nearest["y"]
    detail, detail_extent = _read_window(
        root / crops["photo_map"]["path"],
        (cx - ZOOM_HALF_M, cy - ZOOM_HALF_M, cx + ZOOM_HALF_M, cy + ZOOM_HALF_M),
    )
    _show_gray(zoom, detail, detail_extent)
    zoom.plot([p["x"] for p in positions], [p["y"] for p in positions], "-o", c="red", ms=3, lw=1)
    zoom.set_xlim(detail_extent[0], detail_extent[1])
    zoom.set_ylim(detail_extent[2], detail_extent[3])
    photo, dem = check["photo_map"], check["terrain"]
    zoom.set_title(
        f"Curiosity's drive nearest the habitat, full detail. PLACES grid vs ours: "
        f"photo map {photo['offset_px']} px "
        f"({photo['off_grid_m']} m off grid), terrain {dem['offset_px']} px "
        f"({dem['off_grid_m']} m off grid)",
        fontsize=9,
    )
    _save(fig, folder / "photo-map.png")


def _terrain_overlay(root, crops, walk, habitat, folder) -> None:
    image, extent = _read_small(root / crops["photo_map"]["path"])
    heights, h_extent = _read_small(root / crops["terrain"]["path"], float_data=True)
    fig, (wide, zoom) = plt.subplots(1, 2, figsize=(22, 11), gridspec_kw={"wspace": 0.08})
    _show_gray(wide, image, extent)
    res = (h_extent[1] - h_extent[0]) / heights.shape[1]
    wide.imshow(_hillshade(heights, res), cmap="gray", alpha=0.5, extent=h_extent)
    _walk_area_patches(wide, walk, habitat)
    wide.set_title("1 m terrain hillshade (50%) on the base map")
    # Full detail at the habitat, where the mesa edge gives a sharp line to match.
    x, y = habitat
    box = (x - ZOOM_HALF_M, y - ZOOM_HALF_M, x + ZOOM_HALF_M, y + ZOOM_HALF_M)
    photo, p_extent = _read_window(root / crops["photo_map"]["path"], box)
    shade, s_extent = _read_window(root / crops["terrain"]["path"], box, float_data=True)
    _show_gray(zoom, photo, p_extent)
    zoom.imshow(_hillshade(shade, 1.0), cmap="gray", alpha=0.5, extent=s_extent)
    zoom.set_xlim(p_extent[0], p_extent[1])
    zoom.set_ylim(p_extent[2], p_extent[3])
    zoom.plot(*habitat, "*", c="cyan", ms=16, mec="black")
    zoom.set_title("At the habitat, 1 m: hillshade (50%) on the photo; edges should not double")
    _save(fig, folder / "terrain.png")


def _thermal_inertia_overlay(root, crops, walk, habitat, offset, folder) -> None:
    image, extent = _read_small(root / crops["photo_map"]["path"])
    with rasterio.open(root / crops["thermal_inertia"]["path"]) as src:
        ti = src.read(1, masked=True).astype(np.float32).filled(np.nan)
        b = src.bounds
    ti_extent = (b.left, b.right, b.bottom, b.top)
    fig, (alone, blended) = plt.subplots(1, 2, figsize=(22, 11), gridspec_kw={"wspace": 0.12})
    low, high = np.nanpercentile(ti, [2, 98])
    _show_gray(alone, image, extent)
    shown = alone.imshow(
        ti, cmap="inferno", vmin=low, vmax=high, extent=ti_extent, interpolation="nearest"
    )
    _show_gray(blended, image, extent)
    blended.imshow(
        ti,
        cmap="inferno",
        vmin=low,
        vmax=high,
        extent=ti_extent,
        alpha=0.45,
        interpolation="nearest",
    )
    for ax in (alone, blended):
        _walk_area_patches(ax, walk, habitat)
    fig.colorbar(shown, ax=[alone, blended], shrink=0.7, label="thermal inertia (J m⁻² K⁻¹ s⁻½)")
    alone.set_title("THEMIS thermal inertia, 100 m")
    photo, slope = offset["photo_brightness"], offset["slope"]
    blended.set_title(
        f"Thermal inertia (45%) on the base map, not shifted. Best-matching move: "
        f"{photo['best_move_m']} m (r {photo['r_unmoved']} to {photo['r_best']}) by brightness, "
        f"{slope['best_move_m']} m (r {slope['r_unmoved']} to {slope['r_best']}) by slope",
        fontsize=9,
    )
    _save(fig, folder / "thermal-inertia.png")


def _read_small(path: Path, float_data: bool = False) -> tuple[np.ndarray, tuple]:
    with rasterio.open(path) as src:
        scale = max(src.width, src.height) / OVERLAY_PX
        shape = (round(src.height / scale), round(src.width / scale))
        data = src.read(1, out_shape=shape, resampling=Resampling.average, masked=True)
        b = src.bounds
    data = data.astype(np.float32).filled(np.nan) if float_data else data.filled(0)
    return data, (b.left, b.right, b.bottom, b.top)


def _read_window(path: Path, box: Bounds, float_data: bool = False) -> tuple[np.ndarray, tuple]:
    with rasterio.open(path) as src:
        window = rasterio.windows.from_bounds(*box, transform=src.transform)
        window = window.round_offsets().round_lengths()
        data = src.read(1, window=window, masked=True)
        b = rasterio.windows.bounds(window, src.transform)
    data = data.astype(np.float32).filled(np.nan) if float_data else data.filled(0)
    return data, (b[0], b[2], b[1], b[3])


def _show_gray(ax, image: np.ndarray, extent: tuple) -> None:
    valid = image[image > 0]
    low, high = np.percentile(valid, [1, 99]) if valid.size else (0, 255)
    ax.imshow(image, cmap="gray", vmin=low, vmax=high, extent=extent)
    ax.ticklabel_format(useOffset=False, style="plain")
    ax.tick_params(labelsize=7)
    ax.set_xlabel("easting (m)")
    ax.set_ylabel("northing (m)")


def _walk_area_patches(ax, walk: Bounds, habitat: tuple[float, float]) -> None:
    min_x, min_y, max_x, max_y = walk
    ax.add_patch(
        Rectangle(
            (min_x, min_y),
            max_x - min_x,
            max_y - min_y,
            fill=False,
            ec="cyan",
            lw=1.5,
            label="walk area",
        )
    )
    ax.add_patch(Circle(habitat, (max_x - min_x) / 2, fill=False, ec="cyan", lw=1, ls="--"))


def _hillshade(heights: np.ndarray, res: float) -> np.ndarray:
    """Light from the north-west, 45° up."""
    dy, dx = np.gradient(np.nan_to_num(heights, nan=np.nanmedian(heights)), res)
    slope = np.arctan(np.hypot(dx, dy))
    aspect = np.arctan2(-dx, dy)
    azimuth, altitude = np.radians(315.0), np.radians(45.0)
    shade = np.sin(altitude) * np.cos(slope) + np.cos(altitude) * np.sin(slope) * np.cos(
        azimuth - aspect
    )
    return np.clip(shade, 0, 1)


def _save(fig, path: Path) -> None:
    fig.savefig(path, dpi=80, bbox_inches="tight")
    plt.close(fig)


def _write_site_config(spec: dict, habitat, base_camp) -> None:
    path = REPO_ROOT / "sites" / "gale.yaml"
    # The replayed sol is Person 4's: keep whatever the config holds.
    current = yaml.safe_load(path.read_text())
    files = {key: source["crop"] for key, source in SOURCES.items()} | {
        "rover_positions": f"{OUT}/rover-positions.csv",
        "base_map": "gale/layers/base",
    }
    config = site_config(
        name=spec["name"],
        projection=PROJECTION,
        habitat=habitat,
        base_camp=base_camp,
        walk_radius_m=spec["walk_radius_m"],
        files=files,
        replayed_sol=current.get("replayed_sol"),
    )
    SiteConfig.model_validate(config)
    header = (
        "# Written by prep/gale/build_pack.py (P2-01). Do not edit by hand: change\n"
        "# prep/gale/walk_area.yaml and rerun. The replayed sol is Person 4's and is\n"
        "# kept on rerun; science targets come in P2-03.\n"
    )
    path.write_text(header + yaml.safe_dump(config, sort_keys=False, allow_unicode=True))


def _write_manifest(root: Path, checksums: dict[str, str]) -> None:
    entries = [
        {
            "name": source["name"],
            "path": source["file"],
            "size_bytes": (root / source["file"]).stat().st_size,
            "source_url": source["url"],
            "checksum": checksums[source["file"]],
            "checksum_algorithm": "sha256",
            "credit": source["credit"],
        }
        for source in SOURCES.values()
    ] + [
        {
            "name": "MSL PLACES rover localizations (localized_pos.csv)",
            "path": PLACES,
            "size_bytes": (root / PLACES).stat().st_size,
            "source_url": PLACES_URL,
            "checksum": checksums[PLACES],
            "checksum_algorithm": "sha256",
            "credit": "MSL PLACES localization archive, NASA/JPL-Caltech, PDS Imaging Node.",
        }
    ]
    path = REPO_ROOT / "prep" / "data-manifest.yaml"
    text = path.read_text()
    comments = "".join(line + "\n" for line in text.splitlines() if line.startswith("#"))
    files = {f["path"]: f for f in (yaml.safe_load(text) or {}).get("files") or []}
    files.update({e["path"]: e for e in entries})
    merged = {"files": sorted(files.values(), key=lambda f: f["path"])}
    DataManifest.model_validate(merged)
    path.write_text(comments + yaml.safe_dump(merged, sort_keys=False, allow_unicode=True))


def _source_checksums(root: Path, files: list[str]) -> dict[str, str]:
    """SHA-256 of each source, cached by size and modification time (the photo map is 50 GB)."""
    cache_path = root / OUT / "source-checksums.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    result = {}
    for name in files:
        stat = (root / name).stat()
        key = f"{stat.st_size}:{stat.st_mtime_ns}"
        if cache.get(name, {}).get("key") != key:
            print(f"checksumming {name}")
            cache[name] = {"key": key, "sha256": _sha256(root / name)}
        result[name] = cache[name]["sha256"]
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, indent=2) + "\n")
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 24):
            digest.update(chunk)
    return digest.hexdigest()


def _git_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


if __name__ == "__main__":
    main()
