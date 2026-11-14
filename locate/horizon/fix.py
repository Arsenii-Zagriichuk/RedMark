"""First horizon fix (P3-02): Navcam frames to a fix result, end to end.

At one rover stop, sol 3655 (site 98, drive 1520), inside the walk area:

1. find the skyline in each frame (locate.horizon.sky);
2. turn each skyline pixel into a heading and elevation with the frame's
   camera model and the rover's attitude from its label (locate.horizon.navcam),
   then forget the absolute heading: the matcher gets azimuths relative to the
   photo's own pointing, and elevations, as a crew member with a level
   (gravity) sensor but no compass would have;
3. match against the cached horizon grid (locate.horizon.match) for position
   and heading;
4. write a fix result, scored through the shared scorer against PLACES (the
   answer key) and the camera pointing in the label, plus its overlay image.

Two fixes: one frame alone (about 45° of skyline), and all 12 frames of the
stop's horizon ring combined into 360°, the way a person turns on the spot;
the ring's frames are placed relative to its first frame using their labels.
A fix's photo id and heading are those of its reference photo, the first
frame: the archive id, and the camera pointing in its label.

These frames are tuning pile: the same stop checked the grid in P3-01.
Run with `uv run python -m locate.horizon.fix`.
"""

import csv
import json
import time
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import yaml  # noqa: E402

from contracts.models.common import Method, Point, Provenance, SiteId, TerrainType  # noqa: E402
from contracts.models.fix_result import FixResult  # noqa: E402
from contracts.models.site import SiteConfig  # noqa: E402
from contracts.paths import REPO_ROOT, data_root  # noqa: E402
from contracts.scoring import score_fix  # noqa: E402
from locate.horizon.base_map import LayerImage, read_layer_image  # noqa: E402
from locate.horizon.match import Match, match_skyline  # noqa: E402
from locate.horizon.navcam import NavcamFrame, pixel_headings, read_frame  # noqa: E402
from locate.horizon.sky import skyline_rows  # noqa: E402
from locate.horizon.sources import git_commit, sha256_file  # noqa: E402

GRID = "gale/horizon/grid.npz"
PLACES = "places/localized_pos.csv"
SITE_CONFIG = REPO_ROOT / "sites" / "gale.yaml"
RING_GLOB = "navcam/NRB_*ILT_S0981520NCAM00266M1.LBL"
# Picked before any fix was run: the frame facing the slopes of Mount Sharp.
SINGLE = "NRB_721967057ILT_S0981520NCAM00266M1"
# Bedrock all round in the ring frames, checked by eye.
TERRAIN = TerrainType.textured
# Spots that fit within this factor of the best spot's cost stay inside the
# uncertainty circle; P3-03 calibrates the circle against the answer key.
CIRCLE_COST_FACTOR = 1.5
CLOSE_UP_M = 800.0
BASE_MAP_PIXELS = 2048  # across the walk area, enough for an 800 m close-up
OVERLAYS = REPO_ROOT / "results" / "horizon" / "overlays"
FIXES = REPO_ROOT / "results" / "horizon" / "fixes"


@dataclass(frozen=True)
class Grid:
    xs: np.ndarray
    ys: np.ndarray
    azimuths_deg: np.ndarray
    elevation_deg: np.ndarray

    @property
    def step_deg(self) -> float:
        return float(self.azimuths_deg[1] - self.azimuths_deg[0])

    @property
    def spacing_m(self) -> float:
        return float(self.xs[1] - self.xs[0])


def load_grid(root: Path) -> Grid:
    with np.load(root / GRID) as f:
        return Grid(f["xs"], f["ys"], f["azimuths_deg"], f["elevation_deg"])


def main() -> None:
    root = data_root()
    grid = load_grid(root)
    ring_labels = sorted(root.glob(RING_GLOB))
    if len(ring_labels) != 12:
        raise SystemExit(f"expected the 12 ring frames in {root / 'navcam'}")
    site = SiteConfig.model_validate(yaml.safe_load(SITE_CONFIG.read_text()))
    base_map = read_layer_image(root / site.files["base_map"], pixels_across=BASE_MAP_PIXELS)
    for labels in ([path for path in ring_labels if path.stem == SINGLE], ring_labels):
        fix = horizon_fix(labels, grid, root, base_map)
        print(
            f"{fix.photo_id} ({len(labels)} frames): {fix.truth.position_error_m:.0f} m, "
            f"heading error "
            f"{fix.truth.heading_error_deg:.2f}°, circle {fix.uncertainty_m:.0f} m, "
            f"{fix.time_per_fix_s:.1f} s"
        )


def horizon_fix(
    labels: list[Path],
    grid: Grid,
    root: Path,
    base_map: LayerImage,
    *,
    terrain: TerrainType = TERRAIN,
    overlay_prefix: str = "p3-02",
) -> FixResult:
    """One fix from the frames of one stop, scored and written with its overlay
    in results/horizon/overlays/<overlay_prefix>-<photo id>.png."""
    started = time.perf_counter()
    frames = [read_frame(path) for path in labels]
    photo_id = frames[0].photo_id
    reference = frames[0].heading_deg
    photo = photo_skyline(frames, reference)
    match = match_skyline(
        grid.elevation_deg, grid.step_deg, photo.relative_deg, photo.elevation_deg
    )
    uncertainty = circle_radius_m(match, grid)
    elapsed = time.perf_counter() - started

    overlay = OVERLAYS / f"{overlay_prefix}-{photo_id}.png"
    fix = FixResult(
        photo_id=photo_id,
        site=SiteId.gale,
        method=Method.horizon,
        position=Point(x=grid.xs[match.ix], y=grid.ys[match.iy]),
        heading_deg=match.heading_deg,
        uncertainty_m=uncertainty,
        confidence_pct=0.0,  # not measured until the hidden-pile test (P3-03)
        time_per_fix_s=round(elapsed, 2),
        terrain_type=terrain,
        simulated=False,
        overlay=overlay.relative_to(REPO_ROOT).as_posix(),
        truth=None,
        provenance=fix_provenance(labels, root, SITE_CONFIG, base_map),
    )
    first = frames[0]
    east, north = first.camera_offset_m()
    rover_x, rover_y = rover_position(root / PLACES, first.site, first.drive)
    fix = score_fix(fix, Point(x=rover_x + east, y=rover_y + north), reference)

    draw_overlay(overlay, fix, match, grid, frames, photo, base_map)
    FIXES.mkdir(parents=True, exist_ok=True)
    (FIXES / f"{photo_id}.json").write_text(
        json.dumps(fix.model_dump(mode="json"), indent=2) + "\n"
    )
    return fix


@dataclass(frozen=True)
class PhotoSkyline:
    """Every skyline pixel of a stop's frames."""

    relative_deg: np.ndarray
    """Heading relative to the first frame's pointing, -180 to 180."""
    elevation_deg: np.ndarray
    rows: list[np.ndarray]
    """The skyline row in each column, per frame (NaN where none)."""


def photo_skyline(frames: list[NavcamFrame], reference_deg: float) -> PhotoSkyline:
    relative, elevation, rows = [], [], []
    for frame in frames:
        found = skyline_rows(frame.image)
        cols = np.flatnonzero(np.isfinite(found))
        heading, el = pixel_headings(frame.camera, frame.rover_quaternion, cols, found[cols])
        relative.append((heading - reference_deg + 180.0) % 360.0 - 180.0)
        elevation.append(el)
        rows.append(found)
    return PhotoSkyline(np.concatenate(relative), np.concatenate(elevation), rows)


def circle_radius_m(match: Match, grid: Grid) -> float:
    """Distance from the best spot to the farthest spot that fits within
    CIRCLE_COST_FACTOR of it; never under half the grid cell's diagonal."""
    near_best = match.cost_deg <= CIRCLE_COST_FACTOR * match.cost_deg[match.iy, match.ix]
    iy, ix = np.nonzero(near_best)
    distance = np.hypot(grid.xs[ix] - grid.xs[match.ix], grid.ys[iy] - grid.ys[match.iy])
    return float(max(distance.max(), grid.spacing_m * np.sqrt(2) / 2))


def rover_position(places: Path, site: int, drive: int) -> tuple[float, float]:
    """The rover's (easting, northing) at a stop, from the PLACES rover positions."""
    with places.open() as f:
        rows = [
            row
            for row in csv.DictReader(f)
            if row["frame"] == "ROVER" and int(row["site"]) == site and int(row["drive"]) == drive
        ]
    if len(rows) != 1:
        raise ValueError(f"expected one PLACES row for site {site} drive {drive}, got {len(rows)}")
    return float(rows[0]["easting"]), float(rows[0]["northing"])


def draw_overlay(path, fix, match, grid, frames, photo: PhotoSkyline, base_map) -> None:
    """Photo skyline on the matched calculated skyline; the fix, its circle and
    the true position on the base map, over the match cost and close up; and
    the frames with the skyline found in each."""
    fig = plt.figure(figsize=(22, 14))
    layout = fig.add_gridspec(3, 3, height_ratios=(1, 1.3, 0.9))
    skylines = fig.add_subplot(layout[0, :])
    at_matched_heading = (fix.heading_deg + photo.relative_deg) % 360.0
    at_label_heading = (fix.truth.heading_deg + photo.relative_deg) % 360.0
    truth = fix.truth.position
    true_ix = int(np.abs(grid.xs - truth.x).argmin())
    true_iy = int(np.abs(grid.ys - truth.y).argmin())
    skylines.plot(
        grid.azimuths_deg,
        grid.elevation_deg[true_iy, true_ix],
        c="0.6",
        lw=0.8,
        ls="--",
        label="calculated, grid spot nearest the true position",
    )
    skylines.plot(
        grid.azimuths_deg,
        grid.elevation_deg[match.iy, match.ix],
        c="red",
        lw=1.0,
        label="calculated, matched spot",
    )
    for headings, colour, where in (
        (at_label_heading, "0.75", "the label's heading"),
        (at_matched_heading, "tab:blue", "the matched heading"),
    ):
        skylines.scatter(headings, photo.elevation_deg, s=1, c=colour, label=f"photo, at {where}")
    skylines.set_xlim(0, 360)
    skylines.set_xlabel("heading from map north, degrees")
    skylines.set_ylabel("elevation, degrees")
    skylines.legend(loc="upper left", bbox_to_anchor=(1.0, 1.0), markerscale=6)
    skylines.set_title(
        f"{fix.photo_id}: heading {fix.heading_deg:.2f}° (label {fix.truth.heading_deg:.2f}°, "
        f"error {fix.truth.heading_error_deg:.2f}°)"
    )

    on_map = fig.add_subplot(layout[1, 0])
    on_map.imshow(base_map.image, extent=base_map.extent)
    _draw_fix(on_map, fix)
    on_map.set_xlim(base_map.extent[:2])
    on_map.set_ylim(base_map.extent[2:])
    on_map.legend(loc="upper right")
    on_map.set_title(f"Fix on the base map: {base_map.title}")
    on_map.set_xlabel("map x, metres")
    on_map.set_ylabel("map y, metres")

    costs = fig.add_subplot(layout[1, 1])
    half = grid.spacing_m / 2
    image = costs.imshow(
        match.cost_deg,
        origin="lower",
        extent=(grid.xs[0] - half, grid.xs[-1] + half, grid.ys[0] - half, grid.ys[-1] + half),
        cmap="viridis_r",
    )
    _draw_fix(costs, fix)
    fig.colorbar(image, ax=costs, label="clipped mean skyline difference, degrees")
    costs.set_title(
        f"Match cost over the {grid.spacing_m:.0f} m grid: "
        f"error {fix.truth.position_error_m:.0f} m, circle {fix.uncertainty_m:.0f} m"
    )
    costs.set_xlabel("map x, metres")

    zoom = fig.add_subplot(layout[1, 2])
    zoom.imshow(base_map.image, extent=base_map.extent)
    _draw_fix(zoom, fix)
    zoom.set_xlim(truth.x - CLOSE_UP_M, truth.x + CLOSE_UP_M)
    zoom.set_ylim(truth.y - CLOSE_UP_M, truth.y + CLOSE_UP_M)
    zoom.set_title(f"Base map close up: {CLOSE_UP_M:.0f} m round the true position")

    every = max(1, len(frames) // 4)
    strip = layout[2, :].subgridspec(1, len(frames[::every][:4]))
    for i, (frame, rows) in enumerate(list(zip(frames, photo.rows, strict=True))[::every][:4]):
        ax = fig.add_subplot(strip[0, i])
        low, high = np.percentile(frame.image, [1, 99])
        ax.imshow(np.clip((frame.image - low) / (high - low), 0, 1), cmap="gray")
        ax.plot(rows, c="red", lw=0.8)
        ax.set_title(f"{frame.photo_id}, pointing {frame.heading_deg:.0f}°", fontsize=7)
        ax.axis("off")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=90, bbox_inches="tight")
    plt.close(fig)


def _draw_fix(ax, fix: FixResult) -> None:
    """The fix, its uncertainty circle and the true position."""
    position, truth = fix.position, fix.truth.position
    ax.add_patch(
        plt.Circle((position.x, position.y), fix.uncertainty_m, fill=False, ec="red", lw=1.2)
    )
    ax.plot(position.x, position.y, "r+", ms=14, mew=2, label="fix")
    ax.plot(truth.x, truth.y, "mx", ms=10, mew=2, label="true position (PLACES)")


def fix_provenance(
    labels: list[Path], root: Path, site_config: Path, base_map: LayerImage
) -> Provenance:
    """Every file a fix and its overlay read: the grid, the answer key, the
    frames, the site config and the base map. Data files are recorded from
    REDMARK_DATA, repo files from the repo root."""
    inputs = [root / GRID, root / PLACES]
    for label in labels:
        inputs += [label, label.with_suffix(".IMG")]
    inputs += [site_config, *base_map.files]
    return Provenance(
        script="locate/horizon/fix.py",
        commit=git_commit(),
        inputs=[{"path": _recorded(path, root), "sha256": sha256_file(path)} for path in inputs],
    )


def _recorded(path: Path, root: Path) -> str:
    path = path.resolve()
    for base in (root.resolve(), REPO_ROOT):
        if path.is_relative_to(base):
            return path.relative_to(base).as_posix()
    raise ValueError(f"{path} is neither in REDMARK_DATA nor in the repo")


if __name__ == "__main__":
    main()
