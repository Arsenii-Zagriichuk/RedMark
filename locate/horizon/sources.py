"""The terrain behind the Gale skylines, read from REDMARK_DATA.

Three tiers, finest first:

- the 1 m Gale terrain, in a window round the walk area, for the near skyline;
- a 10 m copy of the whole Gale file (averaged), for the middle distance;
- the HRSC and MOLA blended terrain at 200 m for everything beyond the Gale
  file: the top of Mount Sharp and most of the crater rim.

All are on the 3,396,190 m sphere. The Gale file is equirectangular with true
scale at the equator, the same frame as the site map; the blended crop is in
degrees of longitude and latitude, which on that sphere is the same frame
scaled by 59,274.7 m per degree, so no resampling is needed. The far tier is
shifted by the median height difference where it overlaps the Gale file, so
the two join without a step. The 10 m copy and the far crop are cached next
to the grid, since reading the whole 1 m file takes minutes; each cache
records the checksum of the file it came from and is rebuilt when that changes.
"""

import hashlib
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.windows import Window, from_bounds

from contracts.models.common import Bounds
from contracts.paths import REPO_ROOT
from locate.horizon.render import MARS_RADIUS_M, Raster, Terrain, Tier

GALE_DEM = "MSL_Gale_DEM_Mosaic_1m_v3.tif"
FAR_DEM = "terrain/Gale_HRSC_MOLA_BlendDEM_200mp_v2_crop.tif"
MID_RES_M = 10.0
NEAR_REACH_M = 1_000.0
FAR_REACH_M = 120_000.0
METRES_PER_DEGREE = MARS_RADIUS_M * np.pi / 180


@dataclass(frozen=True)
class GaleTerrain:
    terrain: Terrain
    far_offset_m: float
    """Added to the far tier's heights to join them to the Gale terrain."""
    tier_res_m: tuple[float, ...]


def load_gale_terrain(data_root: Path, walk_area: Bounds, cache_dir: Path) -> GaleTerrain:
    near = read_heights(data_root / GALE_DEM, _grow(walk_area, NEAR_REACH_M))
    mid = _cached(
        cache_dir / f"gale-{MID_RES_M:.0f}m.npz",
        data_root / GALE_DEM,
        lambda: _read_decimated(data_root / GALE_DEM),
    )
    reach = _grow(walk_area, FAR_REACH_M)
    far = _cached(
        cache_dir
        / f"far-200m-{reach.min_x:.0f}_{reach.min_y:.0f}_{reach.max_x:.0f}_{reach.max_y:.0f}.npz",
        data_root / FAR_DEM,
        lambda: read_heights(data_root / FAR_DEM, reach),
    )
    offset = height_offset(mid, far)
    far = Raster(far.heights + np.float32(offset), far.left, far.top, far.res)
    terrain = Terrain([Tier(near, NEAR_REACH_M), Tier(mid), Tier(far)])
    return GaleTerrain(terrain, offset, (near.res, mid.res, far.res))


def read_heights(path: Path, bounds: Bounds) -> Raster:
    """Heights inside bounds (map metres), as a raster in map metres.

    Works for files in the site's equirectangular metres and for files in
    degrees on the same sphere.
    """
    with rasterio.open(path) as src:
        scale = METRES_PER_DEGREE if src.crs.is_geographic else 1.0
        window = from_bounds(
            bounds.min_x / scale,
            bounds.min_y / scale,
            bounds.max_x / scale,
            bounds.max_y / scale,
            src.transform,
        )
        window = window.round_offsets().round_lengths()
        window = window.intersection(Window(0, 0, src.width, src.height))
        heights = src.read(1, window=window, masked=True).astype(np.float32).filled(np.nan)
        transform = src.window_transform(window)
    return Raster(
        heights, left=transform.c * scale, top=transform.f * scale, res=transform.a * scale
    )


def height_offset(gale: Raster, other: Raster) -> float:
    """Median of Gale minus the other height at the other's cells the Gale file covers."""
    rows, cols = np.indices(other.heights.shape)
    x = other.left + (cols.ravel() + 0.5) * other.res
    y = other.top - (rows.ravel() + 0.5) * other.res
    diff = gale.sample(x, y) - other.heights.ravel()
    return float(np.nanmedian(diff))


def _grow(bounds: Bounds, margin_m: float) -> Bounds:
    return Bounds(
        min_x=bounds.min_x - margin_m,
        min_y=bounds.min_y - margin_m,
        max_x=bounds.max_x + margin_m,
        max_y=bounds.max_y + margin_m,
    )


def _read_decimated(path: Path) -> Raster:
    with rasterio.open(path) as src:
        factor = MID_RES_M / src.res[0]
        shape = (round(src.height / factor), round(src.width / factor))
        heights = src.read(1, out_shape=shape, resampling=Resampling.average, masked=True)
        heights = heights.astype(np.float32).filled(np.nan)
        res = src.width * src.res[0] / shape[1]
    return Raster(heights, left=src.bounds.left, top=src.bounds.top, res=res)


class UncommittedCode(RuntimeError):
    """A results file would record a commit that doesn't hold the code or config that wrote it."""


def git_commit(*paths: str | Path, repo: Path = REPO_ROOT) -> str:
    """The commit the repo is at, for a results file's provenance.

    paths are git pathspecs for the code and config the results depend on (the
    script, the modules it uses, its repo inputs). If any of them is edited or
    not yet committed, the commit would not reproduce the results, so this
    refuses instead of recording it: commit first, then run.
    """
    if not paths:
        raise ValueError("name the code and config the results depend on")
    changed = _git(repo, "status", "--porcelain", "--untracked-files=all", "--", *map(str, paths))
    if changed:
        raise UncommittedCode(
            "commit these before writing results, so the recorded commit can reproduce them:\n"
            + changed
        )
    return _git(repo, "rev-parse", "HEAD")


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, cwd=repo, check=True
    ).stdout.rstrip("\n")


def sha256_file(path: Path) -> str:
    """SHA-256 of a file, hashed once per run for each version of the file."""
    stat = path.stat()
    return _sha256(path.resolve(), stat.st_size, stat.st_mtime_ns)


@lru_cache
def _sha256(path: Path, size: int, mtime_ns: int) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 24):
            digest.update(chunk)
    return digest.hexdigest()


def _cached(path: Path, source: Path, read: Callable[[], Raster]) -> Raster:
    """The raster cached at path, rebuilt if the source file has changed since."""
    source_sha256 = sha256_file(source)
    if path.exists():
        with np.load(path) as f:
            if "source_sha256" in f and str(f["source_sha256"]) == source_sha256:
                return Raster(f["heights"], float(f["left"]), float(f["top"]), float(f["res"]))
    raster = read()
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".partial.npz")
    np.savez(
        partial,
        heights=raster.heights,
        left=raster.left,
        top=raster.top,
        res=raster.res,
        source_sha256=source_sha256,
    )
    partial.replace(path)  # never leave a half-written cache behind
    return raster
