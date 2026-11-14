"""Stops for the stage 2 attempt: which Curiosity stops in the walk area have a
top-down Navcam mosaic, and fetching one stop into a pile folder.

Fetching a stop downloads its VRT mosaic, turns it into an overhead view at
25 cm, reads the rover's onboard heading from one of the mosaic's source
frames, and cuts the photo-map window the match searches (SEARCH_HALF_M either
side of the rover's PLACES position, standing in for a stage 1 prior). The
46 MB mosaic image is deleted once its view is saved; its checksum and URL stay
in the pile's index.csv.
"""

import csv
import json
import re
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import from_bounds

from contracts.models.site import SiteConfig
from locate.ground.match import MapWindow
from locate.ground.mosaic import (
    MOSAIC_NAME,
    VIEW_CELL_M,
    OverheadView,
    overhead_view,
    read_mosaic,
    rover_heading_deg,
)
from locate.horizon.sources import sha256_file

MOSAIC_ARCHIVE = "https://planetarydata.jpl.nasa.gov/img/data/msl/msl_navcam_mosaic/DATA"
FRAME_ARCHIVE = "https://planetarydata.jpl.nasa.gov/img/data/msl/MSLNAV_1XXX/DATA"
PHOTO_MAP_URL = "https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/MSL_Gale_Orthophoto_Mosaic_25cm_v3.tif"
"""The full 25 cm Gale photo map (USGS, 50 GB), read a window at a time when
the site's photo-map crop isn't in REDMARK_DATA."""
SEARCH_HALF_M = 60.0
LISTING = "gale/ground/vrt-mosaics.json"
_INDEX_LOCK = threading.Lock()
INDEX_FIELDS = ["photo_id", "sol", "site", "drive", "heading_deg", "img_sha256", "img_url"]


@dataclass(frozen=True)
class Stop:
    """A Curiosity stop in the walk area with a top-down mosaic, and its PLACES position."""

    photo_id: str
    sol: int
    site: int
    drive: int
    x: float
    y: float


@dataclass(frozen=True)
class PileStop:
    """A fetched stop: its overhead view, the window to search and the onboard heading."""

    photo_id: str
    site: int
    drive: int
    heading_deg: float
    view: OverheadView
    window: MapWindow
    files: tuple[Path, ...]


def walk_area_stops(root: Path, places: Path, site: SiteConfig) -> list[Stop]:
    """Every stop in the walk area with a VRT mosaic, one mosaic per stop, by sol."""
    bounds = site.bounds
    positions = {}
    with places.open() as f:
        for row in csv.DictReader(f):
            x, y = float(row["easting"]), float(row["northing"])
            if (
                row["frame"] == "ROVER"
                and bounds.min_x <= x <= bounds.max_x
                and bounds.min_y <= y <= bounds.max_y
            ):
                positions[int(row["site"]), int(row["drive"])] = (int(row["sol"]), x, y)
    names = _mosaic_listing(root / LISTING, sorted({sol for sol, _, _ in positions.values()}))
    stops: dict[tuple[int, int], Stop] = {}
    for name in sorted(names):
        match = MOSAIC_NAME.match(name)
        key = int(match.group(2)), int(match.group(3))
        if key in positions and key not in stops:
            _, x, y = positions[key]
            stops[key] = Stop(name, int(match.group(1)), *key, x, y)
    return sorted(stops.values(), key=lambda stop: (stop.sol, stop.photo_id))


def fetch_stop(stop: Stop, folder: Path, photo_map: Path | None) -> None:
    """Fetch one stop into folder: <photo id>.LBL, its source frame's label,
    <photo id>.npz (view, mask, window) and a row in index.csv."""
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / f"{stop.photo_id}.npz").exists():
        return
    label = folder / f"{stop.photo_id}.LBL"
    image = label.with_suffix(".IMG")
    url = f"{MOSAIC_ARCHIVE}/SOL{stop.sol:05d}/{stop.photo_id}"
    _download(url + ".LBL", label)
    _download(url + ".IMG", image)
    mosaic = read_mosaic(label)
    view = overhead_view(mosaic.pixels)
    heading = rover_heading_deg(
        _source_frame_label(label, stop.sol, folder).read_text(errors="ignore")
    )
    window = read_map_window(stop.x, stop.y, SEARCH_HALF_M, photo_map)
    np.savez_compressed(
        folder / f"{stop.photo_id}.npz",
        view=view.image.astype(np.float32),
        mask=view.mask,
        window=window.image,
        corner=np.array([window.left_x, window.top_y]),
    )
    row = [
        stop.photo_id,
        stop.sol,
        stop.site,
        stop.drive,
        round(heading, 3),
        sha256_file(image),
        url + ".IMG",
    ]
    index = folder / "index.csv"
    with _INDEX_LOCK, index.open("a", newline="") as f:
        new = f.tell() == 0
        writer = csv.writer(f)
        if new:
            writer.writerow(INDEX_FIELDS)
        writer.writerow(row)
    image.unlink()


def fetch_pile(stops: list[Stop], folder: Path, photo_map: Path | None) -> None:
    """Fetch stops a few at a time, then sort the index by sol."""
    with ThreadPoolExecutor(6) as pool:
        list(pool.map(lambda stop: fetch_stop(stop, folder, photo_map), stops))
    index = folder / "index.csv"
    with index.open() as f:
        rows = sorted(csv.DictReader(f), key=lambda row: (int(row["sol"]), row["photo_id"]))
    with index.open("w", newline="") as f:
        writer = csv.DictWriter(f, INDEX_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def read_pile(folder: Path) -> list[PileStop]:
    """Every stop of a fetched pile, in index order."""
    stops = []
    with (folder / "index.csv").open() as f:
        for row in csv.DictReader(f):
            data = np.load(folder / f"{row['photo_id']}.npz")
            left_x, top_y = data["corner"]
            stops.append(
                PileStop(
                    photo_id=row["photo_id"],
                    site=int(row["site"]),
                    drive=int(row["drive"]),
                    heading_deg=float(row["heading_deg"]),
                    view=OverheadView(image=data["view"].astype(np.float64), mask=data["mask"]),
                    window=MapWindow(
                        image=data["window"], left_x=float(left_x), top_y=float(top_y)
                    ),
                    files=(
                        folder / f"{row['photo_id']}.LBL",
                        *sorted(folder.glob(f"{row['photo_id']}.source-*.LBL")),
                        folder / f"{row['photo_id']}.npz",
                    ),
                )
            )
    return stops


def read_map_window(x: float, y: float, half_m: float, photo_map: Path | None) -> MapWindow:
    """The photo map within half_m of (x, y), from the local crop when it covers
    the window, otherwise from the full USGS file over HTTP."""
    source = (
        str(photo_map)
        if photo_map is not None and _covers(photo_map, x, y, half_m)
        else f"/vsicurl/{PHOTO_MAP_URL}"
    )
    with rasterio.Env(
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_MAX_RETRY="5", GDAL_HTTP_RETRY_DELAY="2"
    ):
        with rasterio.open(source) as src:
            if abs(src.res[0] - VIEW_CELL_M) > 1e-9:
                raise ValueError(f"{source} has {src.res[0]} m cells, not {VIEW_CELL_M}")
            window = from_bounds(x - half_m, y - half_m, x + half_m, y + half_m, src.transform)
            window = window.round_offsets().round_lengths()
            left_x, top_y = src.transform * (window.col_off, window.row_off)
            image = src.read(1, window=window).astype(np.float32)
    return MapWindow(image=image, left_x=float(left_x), top_y=float(top_y))


def _covers(path: Path, x: float, y: float, half_m: float) -> bool:
    if not path.exists():
        return False
    with rasterio.open(path) as src:
        b = src.bounds
        return (
            b.left <= x - half_m
            and x + half_m <= b.right
            and b.bottom <= y - half_m
            and y + half_m <= b.top
        )


def _source_frame_label(mosaic_label: Path, sol: int, folder: Path) -> Path:
    """The reduced-frame label of the mosaic's first source frame, which carries
    the rover's onboard attitude. The frame may be from a sol or two earlier."""
    text = mosaic_label.read_text(errors="ignore")
    first = re.search(
        r"SOURCE_PRODUCT_ID\s*=\s*\(\s*\"(N[LR]B_\d{9})EDR(_[A-Z]\d{7}NCAM\d{5})M\d\"", text
    )
    if first is None:
        raise ValueError(f"{mosaic_label.name} names no Navcam source frame")
    name = f"{first.group(1)}ILT{first.group(2)}M1.LBL"
    path = folder / f"{mosaic_label.stem}.source-{name}"
    for frame_sol in (sol, sol - 1, sol - 2):
        _download(f"{FRAME_ARCHIVE}/SOL{frame_sol:05d}/{name}", path)
        if path.stat().st_size > 0:
            return path
    raise ValueError(f"no label for source frame {name} near sol {sol}")


def _mosaic_listing(cache: Path, sols: list[int]) -> list[str]:
    """Names of every VRT mosaic on these sols, from the archive's sol folders (cached)."""
    if not cache.exists():

        def names(sol: int) -> list[str]:
            page = _get(f"{MOSAIC_ARCHIVE}/SOL{sol:05d}/")
            return sorted(
                set(
                    re.findall(
                        r'href="(N_[A-Z]\d{3}_\d{4}_ILT\d{3}VRT_S_\d{4}_[A-Z0-9]+)\.LBL"', page
                    )
                )
            )

        with ThreadPoolExecutor(12) as pool:
            listing = [name for found in pool.map(names, sols) for name in found]
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(listing, indent=1))
    return json.loads(cache.read_text())


def _get(url: str) -> str:
    """A page's text; a sol with no mosaic folder (404) reads as empty."""
    result = subprocess.run(
        ["curl", "-sL", "--retry", "5", "--retry-all-errors", "--max-time", "120", url],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _download(url: str, path: Path) -> None:
    """Download url to path; a missing file (404) is saved as an empty one."""
    # curl, not urllib: it uses the system's certificate store.
    partial = path.with_name(path.name + ".part")
    status = subprocess.run(
        ["curl", "-sL", "--http1.1", "--retry", "5", "--retry-all-errors", "--max-time", "600"]
        + ["-w", "%{http_code}", "-o", str(partial), url],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    if status == "404":
        partial.write_bytes(b"")
    elif status != "200":
        raise RuntimeError(f"{url}: HTTP {status}")
    partial.rename(path)
