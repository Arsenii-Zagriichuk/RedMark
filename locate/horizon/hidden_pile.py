"""The hidden pile for the horizon test (P3-03): Navcam horizon rings kept apart
from tuning.

The frames are split by stretch of the traverse, not by sol: Curiosity often
stays parked for several sols, so a split by sol would put frames of one spot
on both sides. The tuning pile is every stop at sites 96 to 100, round the
sol 3655 ring (site 98) that the grid check and the first fix were tuned on.
Every other Curiosity stop in the walk area may go in the hidden pile.

`uv run python -m locate.horizon.hidden_pile` fetches it from the PDS Imaging
Node. The other stops are cut into STRETCHES runs of the traverse, and from
each the first stop (by sol) with a horizon ring is taken, so the pile spreads
along the whole traverse and is chosen before any fix is run. The ring frames,
their labels and an index (photo, stop, file, size, SHA-256, source) go in
HIDDEN_PILE; the archive's sol listings are cached beside them.
"""

import csv
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from contracts.models.site import SiteConfig
from contracts.paths import data_root
from locate.horizon.fix import PLACES, read_site_config
from locate.horizon.navcam import label_pointing
from locate.horizon.sources import sha256_file

ARCHIVE = "https://planetarydata.jpl.nasa.gov/img/data/msl/MSLNAV_1XXX/DATA"
STRETCHES = 20
MAX_DOWNLOAD_BYTES = 350_000_000
# Left or right Navcam reduced frames: full (F), subframe (S) or downsampled (D); not
# thumbnails. A stereo pan's two cameras count as two sequences, so a ring never holds both.
FRAME = re.compile(r"(N[LR]B)_\d{9}ILT_[FSD](\d{3})(\d{4})(NCAM\d{5})M1\.LBL")
MIN_RING_FRAMES = 5  # 200° of skyline needs at least 5 frames 45° wide

TUNING_SITES = range(96, 101)
HIDDEN_PILE = "hidden/horizon"
"""The hidden pile's folder in REDMARK_DATA, outside navcam/ so no glob over the
tuning frames can reach it. Only the scoring scripts name it."""
HORIZON_ELEVATION_DEG = 20.0
"""A frame sees the horizon when it points within this of level (Navcam is 45° tall)."""
FRAME_WIDTH_DEG = 45.0
RING_COVERAGE_DEG = 200.0
"""A stop's frames are a ring when together they see at least this much skyline."""


def is_tuning_site(site: int) -> bool:
    return site in TUNING_SITES


@dataclass(frozen=True)
class Pointing:
    """Where one frame looks, from its label's site-frame geometry."""

    photo_id: str
    sequence: str
    azimuth_deg: float
    elevation_deg: float


def horizon_ring(frames: list[Pointing]) -> list[Pointing]:
    """The frames of one stop that make its horizon ring, or [] if none goes round.

    Only frames that see the horizon count. Of the sequences they belong to,
    the one that covers the most skyline is the ring, if it covers
    RING_COVERAGE_DEG.
    """
    level = [f for f in frames if abs(f.elevation_deg) <= HORIZON_ELEVATION_DEG]
    by_sequence: dict[str, list[Pointing]] = {}
    for frame in level:
        by_sequence.setdefault(frame.sequence, []).append(frame)
    if not by_sequence:
        return []
    widest = max(by_sequence.values(), key=coverage_deg)
    return widest if coverage_deg(widest) >= RING_COVERAGE_DEG else []


def coverage_deg(frames: list[Pointing]) -> int:
    """Whole degrees of azimuth that at least one frame sees."""
    seen = set()
    for frame in frames:
        start = frame.azimuth_deg - FRAME_WIDTH_DEG / 2
        seen.update(int(start + i) % 360 for i in range(int(FRAME_WIDTH_DEG)))
    return len(seen)


@dataclass(frozen=True)
class Stop:
    """A Curiosity stop from the PLACES rover positions."""

    sol: int
    site: int
    drive: int


def walk_area_stops(places: Path, site_config: SiteConfig) -> list[Stop]:
    """Every rover stop inside the walk area, in traverse order."""
    bounds = site_config.bounds
    with places.open() as f:
        stops = [
            Stop(int(row["sol"]), int(row["site"]), int(row["drive"]))
            for row in csv.DictReader(f)
            if row["frame"] == "ROVER"
            and bounds.min_x <= float(row["easting"]) <= bounds.max_x
            and bounds.min_y <= float(row["northing"]) <= bounds.max_y
        ]
    return sorted(stops, key=lambda stop: (stop.sol, stop.site, stop.drive))


def main() -> None:
    root = data_root()
    folder = root / HIDDEN_PILE
    stops = walk_area_stops(root / PLACES, read_site_config())
    candidates = [stop for stop in stops if not is_tuning_site(stop.site)]
    if not candidates:
        raise SystemExit("no walk-area stops outside the tuning pile")
    stretch_length = -(-len(candidates) // STRETCHES)
    stretches = [
        candidates[i : i + stretch_length] for i in range(0, len(candidates), stretch_length)
    ]
    with ThreadPoolExecutor(8) as pool:
        chosen = [ring for ring in pool.map(lambda s: _first_ring(s, folder), stretches) if ring]
    if not chosen:
        raise SystemExit("no hidden stop has a horizon ring")
    total = sum(
        _remote_size(_url(stop, p.photo_id + ".IMG")) for stop, ring in chosen for p in ring
    )
    print(f"{len(chosen)} stops, {sum(len(r) for _, r in chosen)} frames, {total / 1e6:.0f} MB")
    if total > MAX_DOWNLOAD_BYTES:
        raise SystemExit(f"over the {MAX_DOWNLOAD_BYTES / 1e6:.0f} MB cap for the hidden pile")
    rows = []
    for stop, ring in chosen:
        for pointing in ring:
            for suffix in (".LBL", ".IMG"):
                path = folder / (pointing.photo_id + suffix)
                if not path.exists():
                    _fetch(_url(stop, path.name), path)
                rows.append(
                    {
                        "photo_id": pointing.photo_id,
                        "sol": stop.sol,
                        "site": stop.site,
                        "drive": stop.drive,
                        "sequence": pointing.sequence,
                        "file": path.name,
                        "size_bytes": path.stat().st_size,
                        "sha256": sha256_file(path),
                        "source_url": _url(stop, path.name),
                    }
                )
    index = folder / "index.csv"
    with index.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"{index}: {index.stat().st_size} bytes, sha256 {sha256_file(index)}")


def _first_ring(stretch: list[Stop], folder: Path) -> tuple[Stop, list[Pointing]] | None:
    for stop in stretch:
        try:
            ring = horizon_ring(_pointings(stop, folder))
        except (subprocess.CalledProcessError, RuntimeError) as error:
            # The archive drops connections now and then; one stop it won't serve
            # is skipped rather than ending the whole fetch.
            print(
                f"sol {stop.sol} site {stop.site} drive {stop.drive}: skipped, {error}", flush=True
            )
            continue
        if ring:
            print(
                f"sol {stop.sol} site {stop.site} drive {stop.drive}: {len(ring)} frames",
                flush=True,
            )
            return stop, ring
    return None


def _pointings(stop: Stop, folder: Path) -> list[Pointing]:
    """Where every reduced Navcam frame taken at the stop on its sol looks."""
    listing = folder / "listings" / f"SOL{stop.sol:05d}.html"
    if not listing.exists() or 0 < listing.stat().st_size < 5_000:  # the archive can truncate
        _fetch(f"{ARCHIVE}/SOL{stop.sol:05d}/", listing)
    names: dict[str, list[str]] = {}
    for match in FRAME.finditer(listing.read_text(errors="ignore")):
        if (int(match[2]), int(match[3])) == (stop.site, stop.drive):
            sequence = f"{match[1]} {match[4]}"
            names.setdefault(sequence, [])
            if match[0] not in names[sequence]:
                names[sequence].append(match[0])
    pointings = []
    for sequence, labels in names.items():
        if len(labels) < MIN_RING_FRAMES:
            continue
        for name in labels:
            path = folder / name
            if not path.exists():
                _fetch(_url(stop, name), path)
            azimuth, elevation = label_pointing(path.read_text(errors="ignore"))
            pointings.append(Pointing(Path(name).stem, sequence, azimuth, elevation))
    return pointings


def _url(stop: Stop, name: str) -> str:
    return f"{ARCHIVE}/SOL{stop.sol:05d}/{name}"


def _fetch(url: str, path: Path) -> None:
    """Download url to path; a missing sol folder (404) is saved as an empty file."""
    # curl, not urllib: it uses the system's certificate store.
    path.parent.mkdir(parents=True, exist_ok=True)
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


def _remote_size(url: str) -> int:
    head = subprocess.run(
        ["curl", "-sfIL", "--max-time", "60", url], capture_output=True, text=True, check=True
    ).stdout
    return int(re.findall(r"content-length:\s*(\d+)", head, re.I)[-1])


if __name__ == "__main__":
    main()
