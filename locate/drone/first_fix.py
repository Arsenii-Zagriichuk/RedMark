"""One Ingenuity frame placed on the Jezero photo map, end to end (P2-05).

    REDMARK_DATA=~/redmark-data uv run --group gpu python -m locate.drone.first_fix \\
        HNM_0152_0680432606_392FDR_N0100001HELI02756_0000LUJ05 [--matcher lightglue]

Straightens the frame onto the ground at the map's 25 cm, searches a window
of the flight's map crop around the drone's own position estimate, matches,
and fits the fix. Writes the overlay to results/drone/overlays/<frame>-<matcher>.png.
LoFTR is the matcher of record, so only its fix is written to
results/drone/fixes/<frame>.json; the LightGlue fallback's fix is printed
for comparison. Reads the Jezero pack (prep/jezero/build_pack.py) and JPL's
weights under REDMARK_DATA.
"""

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image, ImageDraw

from contracts.models.common import Provenance, TerrainType
from contracts.paths import REPO_ROOT, data_root
from locate.drone.fix import DroneEstimate, GroundView, MapWindow, build_fix_result, locate_on_map
from locate.drone.ground import HALF_SIZE_M, read_map_window, straighten
from locate.drone.label import onboard_position, read_drone_frame, takeoff_position
from locate.drone.matchers import (
    JPL_LOFTR_WEIGHTS,
    TORCH_HUB,
    lightglue_matcher,
    loftr_matcher,
    pick_device,
)

RESOLUTION = 0.25  # the photo map's scale, metres per pixel
# How far from the drone's own estimate the search reaches, metres. Its track
# can be about 20 m off; the window is wider to leave room.
SEARCH_RADIUS_M = 60.0
RESULTS = REPO_ROOT / "results" / "drone"
OVERLAY_SCALE = 2  # overlay pixels per map pixel
CHECKER_M = 4.0  # side of the overlay's photo/map checkerboard squares, metres


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _recorded(path: Path) -> str:
    """Relative to REDMARK_DATA for data files, to the repo for repo files."""
    for root in (data_root().resolve(), REPO_ROOT):
        if path.resolve().is_relative_to(root):
            return path.resolve().relative_to(root).as_posix()
    raise ValueError(f"{path} is neither in the repo nor in REDMARK_DATA")


def _provenance(inputs: list[Path]) -> Provenance:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=REPO_ROOT, check=True
    ).stdout.strip()
    return Provenance(
        script=_recorded(Path(__file__)),
        commit=commit,
        inputs=[{"path": _recorded(p), "sha256": _sha256(p)} for p in inputs],
    )


def _frame_row(frames_csv: Path, stem: str) -> dict:
    with frames_csv.open() as f:
        for row in csv.DictReader(f):
            if row["product"] == f"{stem}.IMG":
                return row
    raise SystemExit(f"{stem} is not in {frames_csv}; pick a frame from the Jezero pack")


def _draw_overlay(
    window: MapWindow,
    ground: GroundView,
    estimate: DroneEstimate,
    prior: tuple[float, float],
    title: str,
    out: Path,
) -> None:
    """The map window with the straightened photo laid on it by the fit, as a
    checkerboard of photo and map squares (where the fit is right, rocks and
    ridges run on across the squares' edges), its outline, the agreeing
    matches, the onboard estimate and the fix; the straightened photo itself
    on the left."""
    k = OVERLAY_SCALE
    rows, cols = window.image.shape
    base = np.repeat(np.repeat(window.image, k, axis=0), k, axis=1).astype(np.float64)

    # Each overlay pixel's place in the ground view, through the fit's inverse.
    a, b = estimate.to_window
    yy, xx = np.mgrid[0 : rows * k, 0 : cols * k]
    window_px = (xx + 0.5) / k - 0.5 + 1j * ((yy + 0.5) / k - 0.5)
    view_px = (window_px - b) / a
    vx, vy = np.round(view_px.real).astype(int), np.round(view_px.imag).astype(int)
    size = ground.image.shape
    inside = (vx >= 0) & (vx < size[1]) & (vy >= 0) & (vy < size[0])
    on_photo = np.zeros_like(inside)
    on_photo[inside] = ground.valid[vy[inside], vx[inside]]
    square = round(CHECKER_M / window.resolution * k)
    photo_square = on_photo & ((xx // square + yy // square) % 2 == 0)
    # The photo's grey levels mapped onto the map's within the footprint, so
    # squares differ in shape, not in tone.
    photo = ground.image[vy[on_photo], vx[on_photo]].astype(np.float64)
    ranks = np.argsort(np.argsort(photo)) / max(len(photo) - 1, 1)
    matched = np.zeros_like(base)
    matched[on_photo] = np.quantile(base[on_photo], ranks)
    gray = base.copy()
    gray[photo_square] = matched[photo_square]
    canvas = Image.fromarray(gray.astype(np.uint8)).convert("RGB")
    draw = ImageDraw.Draw(canvas)

    def to_px(xy: np.ndarray) -> list[tuple[float, float]]:
        xy = np.atleast_2d(xy)
        return [
            ((x - window.min_x) / window.resolution * k, (window.max_y - y) / window.resolution * k)
            for x, y in xy
        ]

    for px, py in to_px(estimate.inlier_xy):
        draw.ellipse((px - 2, py - 2, px + 2, py + 2), fill=(0, 200, 255))
    outline = to_px(estimate.outline_xy)
    if outline:
        draw.line(outline + outline[:1], fill=(255, 40, 40), width=3)
    (fx, fy), (ox, oy) = to_px(np.array([estimate.position, prior]))
    draw.line((ox - 9, oy - 9, ox + 9, oy + 9), fill=(255, 220, 0), width=3)
    draw.line((ox - 9, oy + 9, ox + 9, oy - 9), fill=(255, 220, 0), width=3)
    draw.ellipse((fx - 8, fy - 8, fx + 8, fy + 8), outline=(40, 255, 40), width=3)
    heading = np.radians(estimate.heading_deg)
    draw.line(
        (fx, fy, fx + 40 * np.sin(heading), fy - 40 * np.cos(heading)), fill=(40, 255, 40), width=3
    )
    metre = k / window.resolution
    x0, y0 = 20, canvas.height - 30
    draw.rectangle((x0, y0, x0 + 20 * metre, y0 + 6), fill=(255, 255, 255))
    draw.text((x0, y0 - 16), "20 m", fill=(255, 255, 255))

    left = Image.fromarray(np.repeat(np.repeat(ground.image, k, axis=0), k, axis=1)).convert("RGB")
    sheet = Image.new("RGB", (left.width + canvas.width + 10, max(left.height, canvas.height) + 70))
    sheet.paste(left, (0, 70))
    sheet.paste(canvas, (left.width + 10, 70))
    text = ImageDraw.Draw(sheet)
    for i, line in enumerate(title.splitlines()):
        text.text((10, 8 + 14 * i), line, fill=(255, 255, 0))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)


def run(stem: str, matcher_name: str) -> None:
    root = data_root()
    jezero = root / "jezero"
    row = _frame_row(jezero / "pack" / "frames.csv", stem)
    flight, sol = int(row["flight"]), int(row["sol"])
    label = jezero / "source" / "helicam" / f"sol-{sol:05d}" / f"{stem}.xml"
    image = label.with_suffix(".IMG")
    crop = jezero / "pack" / "crops" / row["crop"]
    waypoints = jezero / "source" / "nasa" / "m20_heli_waypoints.json"
    device = pick_device()
    if matcher_name == "loftr":
        weights = [root / JPL_LOFTR_WEIGHTS]
        matcher = loftr_matcher(weights[0], device)
    else:
        matcher = lightglue_matcher(root / TORCH_HUB, device)
        weights = sorted(p for p in (root / TORCH_HUB / "checkpoints").iterdir() if p.is_file())

    started = time.perf_counter()
    frame = read_drone_frame(label.read_text())
    with rasterio.open(label) as src:
        raw = src.read(1)
    prior = onboard_position(frame, takeoff_position(json.loads(waypoints.read_text()), flight))
    ground = straighten(raw, frame, RESOLUTION)
    window = read_map_window(crop, prior, SEARCH_RADIUS_M + HALF_SIZE_M)
    estimate = locate_on_map(ground, window, matcher)
    seconds = time.perf_counter() - started

    overlay = RESULTS / "overlays" / f"{stem}-{matcher_name}.png"
    shift = np.hypot(estimate.position[0] - prior[0], estimate.position[1] - prior[1])
    title = "\n".join(
        [
            f"Drone fix, flight {flight}, {stem}"
            f" ({matcher_name} on {device.type}, {seconds:.1f} s)",
            "Left: the frame straightened to the HiRISE 25 cm map, north up. Right: the search"
            f" window, the frame laid on it by the fit in {CHECKER_M:g} m squares",
            f"(photo and map alternate), its outline (red), {estimate.inliers} of"
            f" {estimate.matches} matches agreeing (cyan), the drone's own estimate (yellow x),",
            f"the fix (green, with heading), {shift:.1f} m from the drone's estimate;"
            f" turn {estimate.rotation_deg:+.1f}°, scale {estimate.scale:.3f}."
            " Not yet scored: the answer key is P4-01.",
        ]
    )
    _draw_overlay(window, ground, estimate, prior, title, overlay)
    hard_mode = row["hard_mode"] == "True"
    inputs = [label, image, crop, waypoints, jezero / "pack" / "frames.csv"]
    fix = build_fix_result(
        photo_id=stem,
        estimate=estimate,
        time_per_fix_s=round(seconds, 2),
        # The pack's hard-mode flights are over sand ripples; P4-01 tags each
        # keyed frame by eye, and P2-06 uses those tags.
        terrain_type=TerrainType.plain if hard_mode else TerrainType.textured,
        overlay=_recorded(overlay),
        provenance=_provenance(inputs + weights),
    )
    text = json.dumps(fix.model_dump(mode="json"), indent=2) + "\n"
    if matcher_name == "loftr":
        path = RESULTS / "fixes" / f"{stem}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        print(f"wrote {_recorded(path)}")
    else:
        print(text)
    print(
        f"wrote {_recorded(overlay)}; {estimate.inliers}/{estimate.matches} matches agree, "
        f"{shift:.1f} m from the onboard estimate, {seconds:.1f} s"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "frame", help="Navcam product name without .IMG, from the pack's frames.csv"
    )
    parser.add_argument("--matcher", choices=["loftr", "lightglue"], default="loftr")
    args = parser.parse_args()
    if not os.environ.get("REDMARK_DATA"):
        sys.exit(
            "set REDMARK_DATA to the shared data folder with the Jezero pack and JPL's weights"
        )
    run(args.frame, args.matcher)
