"""The simulated Gale drone fix for the demo (P2-07).

    REDMARK_DATA=~/redmark-data uv run --group gpu python -m locate.drone.gale_fix \\
        [--matcher lightglue]

Places the crew on the demo walk: Person 4's fastest route from base camp to
the first science target at the app's default limits, at two thirds of its
walking time, where the app's walk schedule puts the drone fix
(app/src/walk/schedule.ts). Cuts the drone's photo from the Gale photo map
with the crew's suit markers drawn in (locate.drone.gale_view), then runs it
through the real pipeline: straighten by the drone's onboard heading, search
the map around its onboard position, match with LoFTR and JPL's weights, fit,
and carry the detected markers onto the map.

The photo comes from the same map it is matched to, so the fix shows the
pipeline, not accuracy: the fix result says simulated, every image says
SIMULATED, and no error is measured or reported.

Writes, for photo id gale-sim-drone-0001:
- results/drone/fixes/<id>.json, the crew's fix (the midpoint of the two
  detected astronauts, facing their mean heading);
- results/drone/overlays/<id>-<matcher>-<run-id>.png, the overlay: the
  photo with the detected astronauts, and the map with the photo's matched
  outline, the astronauts and the route;
- results/drone/overlays/<id>-photo-<run-id>.png, the photo alone with the
  detected astronauts, for the Drone fix screen;
- cache/demo/fixes/drone-fix-gale.json, the demo cache entry for
  GET /fixes/drone/<id>, with both images copied to cache/demo/drone/overlays/.
"""

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import numpy as np
import rasterio
import yaml
from PIL import Image, ImageDraw, ImageFont, PngImagePlugin

from contracts.models.common import Method, Point, Provenance, SiteId, TerrainType
from contracts.models.fix_result import FixResult
from contracts.paths import REPO_ROOT, data_root
from locate.drone.fix import (
    UNCALIBRATED_CONFIDENCE_PCT,
    UNCALIBRATED_UNCERTAINTY_M,
    DroneFix,
    MapWindow,
    locate_on_map,
)
from locate.drone.gale_view import Astronaut, DronePhoto, take_photo
from locate.drone.ground import HALF_SIZE_M, read_map_window
from locate.drone.matchers import (
    JPL_LOFTR_WEIGHTS,
    LIGHTGLUE_CHECKPOINTS,
    TORCH_HUB,
    lightglue_matcher,
    loftr_matcher,
    pick_device,
)
from locate.drone.pipeline import RESOLUTION, SEARCH_RADIUS_M
from locate.drone.records import provenance, recorded

PHOTO_ID = "gale-sim-drone-0001"
DEMO_STEP = "drone.fix.gale"
RESULTS = "results/drone"
DEMO_CACHE = "cache/demo/fixes"
"""Where the service's recorder saves GET /fixes/... calls: the path's first segment."""
DEMO_IMAGES = "cache/demo/drone/overlays"
"""The Gale drone fix's images, by their file names in results/; only this script writes here."""

# The code the fix depends on, the route engine included; uncommitted changes stop the run.
FIX_CODE = ["locate/drone", "prep", "contracts", "route", "sites", "pyproject.toml", "uv.lock"]

# The demo walk, as the app plans it (app/src/plan/routes.ts): the fastest
# route from base camp to the first science target at the default limits, and
# the drone fix two thirds of the way through the walk (app/src/walk/schedule.ts).
WALK_LIMITS = {
    "max_slope_deg": 20,
    "max_distance_from_habitat_m": 2000,
    "planning_speed_kmh": 2,
    "max_walk_h": 6,
}
DRONE_FIX_AT = 2 / 3

# The simulated scene. These set up the picture, not a result: the crew walks
# side by side (the buddy rule) facing along the route; the drone hovers
# behind them, facing the same way, so both are in its photo off the nadir.
CREW_SPACING_M = 2.0
DRONE_BEHIND_M = 8.0
TRAVEL_SPAN_M = 10.0  # the route's direction is taken over this far either side
# The drone's own idea of where it is and which way it faces is off, as a
# real drone's is: the search starts from here, and the fit must turn the
# photo by the heading error.
ONBOARD_DRIFT_M = (6.3, -4.7)
ONBOARD_HEADING_ERROR_DEG = 3.0

OVERLAY_HALF_M = 45.0  # the overlay's map panel reaches this far from the crew
OVERLAY_SCALE = 4  # overlay pixels per map pixel
SIMULATED_NOTE = (
    "SIMULATED. The photo is cut from the same Gale 25 cm map it is matched to: it shows the"
    " pipeline, not accuracy. Astronaut detection is a mock-up."
)


def build_simulated_fix_result(
    *,
    photo_id: str,
    crew: list[Astronaut],
    time_per_fix_s: float,
    terrain_type: TerrainType,
    overlay: str,
    provenance: Provenance,
) -> FixResult:
    """The crew's simulated Gale drone fix: the detected astronauts' midpoint,
    facing their mean heading. It has no truth, so no error."""
    x, y = np.mean([astronaut.position for astronaut in crew], axis=0)
    angles = np.radians([astronaut.heading_deg for astronaut in crew])
    heading = float(np.degrees(np.arctan2(np.sin(angles).sum(), np.cos(angles).sum())) % 360.0)
    return FixResult(
        photo_id=photo_id,
        site=SiteId.gale,
        method=Method.drone,
        position=Point(x=float(x), y=float(y)),
        heading_deg=0.0 if heading >= 360.0 else heading,
        uncertainty_m=UNCALIBRATED_UNCERTAINTY_M,
        confidence_pct=UNCALIBRATED_CONFIDENCE_PCT,
        time_per_fix_s=time_per_fix_s,
        terrain_type=terrain_type,
        simulated=True,
        overlay=overlay,
        truth=None,
        provenance=provenance,
    )


def write_demo_cache(photo_id: str, images: list[str], root: Path) -> Path:
    """Save the demo cache entry for GET /fixes/drone/<photo_id> under root,
    with the response as the service serves it, and copy its images."""
    for image in images:
        if not (root / image).is_file():
            raise FileNotFoundError(f"{photo_id} has no image at {image}")
    copies = root / DEMO_IMAGES
    shutil.rmtree(copies, ignore_errors=True)
    copies.mkdir(parents=True)
    for image in images:
        shutil.copyfile(root / image, copies / Path(image).name)
    served = root / RESULTS / "fixes" / f"{photo_id}.json"
    entry = {
        "step": DEMO_STEP,
        "request": {"method": "GET", "path": f"/fixes/drone/{photo_id}", "body": None},
        "status": 200,
        "contract": "fix_result",
        "response": json.loads(served.read_text()),
    }
    path = root / DEMO_CACHE / f"{DEMO_STEP.replace('.', '-')}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entry, indent=2) + "\n")
    return path


def _along(path: np.ndarray, distance: float) -> np.ndarray:
    """The point `distance` metres along `path`, clamped to its ends."""
    steps = np.hypot(*np.diff(path, axis=0).T)
    reach = np.concatenate([[0.0], np.cumsum(steps)])
    distance = float(np.clip(distance, 0.0, reach[-1]))
    return np.array(
        [np.interp(distance, reach, path[:, 0]), np.interp(distance, reach, path[:, 1])]
    )


def walk_point(route: dict, fraction: float) -> tuple[np.ndarray, float]:
    """Where the crew is `fraction` of the way through the route's walking
    time, and the heading of the route there. Within a leg, at even speed."""
    path = np.array([[p["x"], p["y"]] for p in route["path"]])
    steps = np.hypot(*np.diff(path, axis=0).T)
    reach = np.concatenate([[0.0], np.cumsum(steps)])
    target = fraction * sum(leg["time_s"] for leg in route["legs"])
    elapsed = 0.0
    for leg in route["legs"]:
        if elapsed + leg["time_s"] >= target or leg is route["legs"][-1]:
            share = (target - elapsed) / leg["time_s"] if leg["time_s"] else 0.0
            start, end = reach[leg["start_index"]], reach[leg["end_index"]]
            distance = start + min(share, 1.0) * (end - start)
            break
        elapsed += leg["time_s"]
    here = _along(path, distance)
    behind, ahead = _along(path, distance - TRAVEL_SPAN_M), _along(path, distance + TRAVEL_SPAN_M)
    east, north = ahead - behind
    return here, float(np.degrees(np.arctan2(east, north)) % 360.0)


def _offset(point: np.ndarray, heading_deg: float, forward: float, right: float) -> np.ndarray:
    h = np.radians(heading_deg)
    ahead, to_right = np.array([np.sin(h), np.cos(h)]), np.array([np.cos(h), -np.sin(h)])
    return point + forward * ahead + right * to_right


def _terrain_type(sand_raster: Path, at: np.ndarray) -> TerrainType:
    """Plain on layer 2's loose sand (1 in sand.tif), textured anywhere else."""
    with rasterio.open(sand_raster) as src:
        value = next(src.sample([tuple(at)]))[0]
    return TerrainType.plain if value == 1 else TerrainType.textured


def _font(size: int) -> ImageFont.ImageFont:
    return ImageFont.load_default(size=size)


def _banner(width: int, lines: list[str]) -> Image.Image:
    banner = Image.new("RGB", (width, 60 + 18 * len(lines)), (0, 0, 0))
    draw = ImageDraw.Draw(banner)
    draw.text((12, 6), "SIMULATED", fill=(255, 60, 60), font=_font(40))
    for i, line in enumerate(lines):
        draw.text((12, 54 + 18 * i), line, fill=(255, 255, 0), font=_font(14))
    return banner


def _photo_with_detections(photo: DronePhoto) -> Image.Image:
    image = Image.fromarray(photo.image)
    draw = ImageDraw.Draw(image)
    for helmet, backpack in photo.markers_px():
        cx, cy = (helmet + backpack) / 2
        draw.ellipse((cx - 22, cy - 22, cx + 22, cy + 22), outline=(255, 255, 0), width=3)
    return image


def _save_png(image: Image.Image, out: Path, text: dict[str, str]) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    metadata = PngImagePlugin.PngInfo()
    for key, value in text.items():
        metadata.add_itxt(key, value)
    with tempfile.TemporaryDirectory(dir=out.parent) as temporary:
        staged = Path(temporary) / out.name
        image.save(staged, pnginfo=metadata)
        staged.replace(out)


def _map_panel(
    photo_map: Path,
    centre: np.ndarray,
    estimate: DroneFix,
    found: list[Astronaut],
    fix: FixResult,
    route: dict,
) -> Image.Image:
    """The map around the crew: the route (white), the photo's matched outline
    (red), each detected astronaut (orange, facing tick) and the crew's fix
    (green)."""
    window: MapWindow = read_map_window(photo_map, tuple(centre), OVERLAY_HALF_M)
    k = OVERLAY_SCALE
    gray = np.repeat(np.repeat(window.image, k, axis=0), k, axis=1)
    canvas = Image.fromarray(gray).convert("RGB")
    draw = ImageDraw.Draw(canvas)

    def to_px(xy) -> list[tuple[float, float]]:
        return [tuple(p) for p in (window.to_px(np.atleast_2d(xy)) + 0.5) * k]

    route_px = to_px(np.array([[p["x"], p["y"]] for p in route["path"]]))
    draw.line(route_px, fill=(255, 255, 255), width=3)
    outline = to_px(estimate.outline_xy)
    draw.line(outline + outline[:1], fill=(255, 40, 40), width=3)
    for astronaut in found:
        ((ax, ay),) = to_px(astronaut.position)
        h = np.radians(astronaut.heading_deg)
        draw.ellipse((ax - 7, ay - 7, ax + 7, ay + 7), fill=(255, 140, 0))
        draw.line((ax, ay, ax + 24 * np.sin(h), ay - 24 * np.cos(h)), fill=(255, 140, 0), width=3)
    ((fx, fy),) = to_px((fix.position.x, fix.position.y))
    draw.ellipse((fx - 16, fy - 16, fx + 16, fy + 16), outline=(40, 255, 40), width=3)
    metre = k / window.resolution
    x0, y0 = 20, canvas.height - 30
    draw.rectangle((x0, y0, x0 + 10 * metre, y0 + 6), fill=(255, 255, 255))
    draw.text((x0, y0 - 18), "10 m", fill=(255, 255, 255), font=_font(14))
    return canvas


def run(matcher_name: str) -> None:
    root = data_root()
    site_path = REPO_ROOT / "sites" / "gale.yaml"
    site = yaml.safe_load(site_path.read_text())
    photo_map = root / site["files"]["photo_map"]
    target = site["science_targets"][0]
    start = site.get("base_camp") or site["habitat"]

    from route.engine import plan  # Person 4's route engine, as the service serves it

    route = plan(
        {
            "site": "gale",
            "start": start,
            "goal": target["position"],
            "mode": "fastest",
            "uncertainty_m": 0,
            "limits": WALK_LIMITS,
        }
    )
    crew_centre, travel = walk_point(route, DRONE_FIX_AT)
    crew = [
        Astronaut(position=tuple(_offset(crew_centre, travel, 0.0, side)), heading_deg=travel)
        for side in (-CREW_SPACING_M / 2, CREW_SPACING_M / 2)
    ]
    nadir = _offset(crew_centre, travel, -DRONE_BEHIND_M, 0.0)
    photo = take_photo(photo_map, tuple(nadir), travel, crew)

    device = pick_device()
    if matcher_name == "loftr":
        weights = [root / JPL_LOFTR_WEIGHTS]
        matcher = loftr_matcher(weights[0], device)
    else:
        matcher = lightglue_matcher(root / TORCH_HUB, device)
        weights = [root / TORCH_HUB / "checkpoints" / name for name in LIGHTGLUE_CHECKPOINTS]

    started = time.perf_counter()
    ground = photo.straighten((travel + ONBOARD_HEADING_ERROR_DEG) % 360.0, RESOLUTION)
    onboard = nadir + np.array(ONBOARD_DRIFT_M)
    window = read_map_window(photo_map, tuple(onboard), SEARCH_RADIUS_M + HALF_SIZE_M)
    estimate = locate_on_map(ground, window, matcher)
    found = photo.astronauts_on_map(ground, estimate, window)
    seconds = time.perf_counter() - started
    if len(found) != len(crew):
        raise SystemExit(f"found {len(found)} astronauts in the photo, {len(crew)} were drawn")

    files = site["files"]
    route_inputs = [root / files[key] for key in ("slope", "sand", "ridges")]
    conditions = REPO_ROOT / "conditions" / f"{site['replayed_sol']}.json"
    made_by = provenance(
        Path(__file__), FIX_CODE, [photo_map, site_path, conditions, *route_inputs, *weights]
    )

    run_id = uuid4().hex
    results = REPO_ROOT / RESULTS
    overlay = results / "overlays" / f"{PHOTO_ID}-{matcher_name}-{run_id}.png"
    photo_png = results / "overlays" / f"{PHOTO_ID}-photo-{run_id}.png"
    fix = build_simulated_fix_result(
        photo_id=PHOTO_ID,
        crew=found,
        time_per_fix_s=round(seconds, 2),
        terrain_type=_terrain_type(root / files["sand"], crew_centre),
        overlay=recorded(overlay),
        provenance=made_by,
    )
    detected = json.dumps(
        [{"x": a.position[0], "y": a.position[1], "heading_deg": a.heading_deg} for a in found]
    )
    metadata = {"fix_result": fix.model_dump_json(), "astronauts": detected}

    photo_image = _photo_with_detections(photo)
    left = photo_image.resize((720, 720), Image.Resampling.LANCZOS)
    right = _map_panel(photo_map, crew_centre, estimate, found, fix, route)
    lines = [
        SIMULATED_NOTE,
        f"Left: the drone photo ({photo.resolution * 100:.0f} cm per pixel, up is the drone's"
        " heading) with the detected astronauts (yellow).",
        f"Right: the Gale map on the demo walk to {target['name']} (white), the photo's matched"
        f" outline (red, {matcher_name} on {device.type}, {estimate.inliers} of"
        f" {estimate.matches} matches agreeing),",
        "each detected astronaut and the way they face (orange) and the crew's fix (green).",
    ]
    sheet_width = left.width + right.width + 10
    banner = _banner(sheet_width, lines)
    sheet = Image.new("RGB", (sheet_width, banner.height + max(left.height, right.height)))
    sheet.paste(banner, (0, 0))
    sheet.paste(left, (0, banner.height))
    sheet.paste(right, (left.width + 10, banner.height))
    _save_png(sheet, overlay, metadata)

    photo_banner = _banner(photo_image.width, [SIMULATED_NOTE[:96], SIMULATED_NOTE[96:]])
    framed = Image.new("RGB", (photo_image.width, photo_banner.height + photo_image.height))
    framed.paste(photo_banner, (0, 0))
    framed.paste(photo_image, (0, photo_banner.height))
    _save_png(framed, photo_png, metadata)

    path = results / "fixes" / f"{PHOTO_ID}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=path.parent) as temporary:
        staged = Path(temporary) / path.name
        staged.write_text(fix.model_dump_json(indent=2) + "\n", encoding="utf-8")
        staged.replace(path)
    cache = write_demo_cache(PHOTO_ID, [recorded(overlay), recorded(photo_png)], REPO_ROOT)
    for written in (path, overlay, photo_png, cache):
        print(f"wrote {recorded(written)}")
    print(
        f"{estimate.inliers}/{estimate.matches} matches agree; {len(found)} astronauts found;"
        f" {seconds:.1f} s (simulated: no accuracy is measured)"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--matcher", choices=["loftr", "lightglue"], default="loftr")
    args = parser.parse_args()
    if not os.environ.get("REDMARK_DATA"):
        sys.exit("set REDMARK_DATA to the shared data folder with the Gale pack and JPL's weights")
    run(args.matcher)
