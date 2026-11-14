"""Build the horizon grid for Gale (P3-01).

For a square grid of spots across the walk area, calculate each spot's 360°
skyline and cache it in $REDMARK_DATA/gale/horizon/:

- grid.npz: xs, ys (map metres), azimuths_deg, ground_m (ground height at each
  spot) and elevation_deg[iy, ix, iaz], the horizon elevation in degrees;
- grid-meta.json: spacing, ray settings, computing time, the far-terrain height
  offset, and the script, commit and input checksums that wrote it.

Run with `uv run python -m locate.horizon.grid`. The walk area comes from
sites/gale.yaml, so a new walk area is a rerun, not a code change.
"""

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import yaml

from contracts.models.site import SiteConfig
from contracts.paths import REPO_ROOT, data_root
from locate.horizon.render import skyline
from locate.horizon.sources import FAR_DEM, FAR_REACH_M, GALE_DEM, load_gale_terrain

SPACING_M = 100.0
AZIMUTH_STEP_DEG = 0.25
NEAREST_M = 5.0
FINEST_STEP_M = 1.0
# Curiosity's Navcam sits about 1.9 m above the ground; the test photos are Navcam.
OBSERVER_HEIGHT_M = 1.9


def ray_distances(nearest_m: float, farthest_m: float, finest_m: float, step_deg: float):
    """Sample distances along a ray: every finest_m near the spot, then growing so
    that the gap between samples stays about one azimuth step wide."""
    grow = np.tan(np.radians(step_deg))
    out = [nearest_m]
    while out[-1] < farthest_m:
        out.append(out[-1] + max(finest_m, out[-1] * grow))
    return np.array(out)


def spots_along(low: float, high: float, spacing: float) -> np.ndarray:
    return np.arange(low, high + spacing / 2, spacing)


def main() -> None:
    site = SiteConfig.model_validate(yaml.safe_load((REPO_ROOT / "sites/gale.yaml").read_text()))
    root = data_root()
    missing = [name for name in (GALE_DEM, FAR_DEM) if not (root / name).exists()]
    if missing:
        sys.exit(f"{', '.join(missing)} not in {root}: set REDMARK_DATA to the data folder")
    out_dir = root / "gale" / "horizon"
    started = time.perf_counter()
    gale = load_gale_terrain(root, site.bounds, out_dir / "cache")
    loaded = time.perf_counter()
    print(
        f"terrain loaded in {loaded - started:.0f} s; far-terrain offset {gale.far_offset_m:+.1f} m"
    )

    xs = spots_along(site.bounds.min_x, site.bounds.max_x, SPACING_M)
    ys = spots_along(site.bounds.min_y, site.bounds.max_y, SPACING_M)
    azimuths = np.arange(0.0, 360.0, AZIMUTH_STEP_DEG)
    distances = ray_distances(NEAREST_M, FAR_REACH_M, FINEST_STEP_M, AZIMUTH_STEP_DEG)
    elevation = np.empty((ys.size, xs.size, azimuths.size), np.float32)
    ground = np.empty((ys.size, xs.size), np.float32)
    for iy, y in enumerate(ys):
        for ix, x in enumerate(xs):
            ground[iy, ix] = gale.terrain.height(np.array([x]), np.array([y]), np.array([0.0]))[0]
            elevation[iy, ix] = skyline(
                gale.terrain,
                x,
                y,
                observer_height_m=OBSERVER_HEIGHT_M,
                azimuths_deg=azimuths,
                distances_m=distances,
            )
        print(f"row {iy + 1}/{ys.size}", file=sys.stderr, flush=True)
    finished = time.perf_counter()

    out_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out_dir / "grid.npz",
        xs=xs,
        ys=ys,
        azimuths_deg=azimuths,
        ground_m=ground,
        elevation_deg=elevation,
    )
    meta = {
        "site": site.site.value,
        "walk_area": site.bounds.model_dump(),
        "spacing_m": SPACING_M,
        "spots": int(xs.size * ys.size),
        "azimuth_step_deg": AZIMUTH_STEP_DEG,
        "observer_height_m": OBSERVER_HEIGHT_M,
        "ray_samples": int(distances.size),
        "ray_reach_m": [NEAREST_M, float(distances[-1])],
        "tier_res_m": list(gale.tier_res_m),
        "far_offset_m": round(gale.far_offset_m, 2),
        "missing_directions": int(np.isnan(elevation).sum()),
        "terrain_load_s": round(loaded - started, 1),
        "compute_s": round(finished - loaded, 1),
        "provenance": {
            "script": "locate/horizon/grid.py",
            "commit": _commit(),
            "inputs": [
                {"path": name, "sha256": _sha256(root / name)} for name in (GALE_DEM, FAR_DEM)
            ]
            + [{"path": "sites/gale.yaml", "sha256": _sha256(REPO_ROOT / "sites/gale.yaml")}],
        },
    }
    (out_dir / "grid-meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps({k: v for k, v in meta.items() if k != "provenance"}, indent=2))


def _commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=REPO_ROOT, check=True
    ).stdout.strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 24):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
