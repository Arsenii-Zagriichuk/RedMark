"""Build layers 2 and 3 at Gale (P2-03): walkability and science.

    REDMARK_DATA=~/redmark-data uv run python -m prep.gale.build_layers_2_3

Reads the walk-area crops the P2-01 pack wrote (named in sites/gale.yaml) and the
boxwork zones and science targets in prep/gale/walk_area.yaml, and writes, under
$REDMARK_DATA/gale/:
  rasters/sand.tif            1 on loose sand (THEMIS thermal inertia), 100 m; route engine
  rasters/ridges.tif          1 on a boxwork ridge (the 25 cm photo), 50 cm; route engine
  layers/sand/, ridges/       layer 2, group 2
  layers/minerals/            layer 3, CRISM mineral highlights on CRISM's 18 m pixels
  layers/chemistry/           layer 3, Curiosity's APXS points and drill sites
  layers/*/provenance.json    the script, commit and input checksums behind each layer
  layers/overlays/*.png       each layer on the photo map, and the ridge map beside the
                              photo in three sample areas, to check by eye
and, in the repo, `files.sand`, `files.ridges` and `science_targets` in sites/gale.yaml
and copies of the overlays in prep/gale/evidence/.

Nothing live changes until every layer, raster and overlay is built and the science
targets are checked; then all are published together, the sand and ridge rasters
included. The targets: each must sit inside the walk radius and a boxwork zone, clear of
Curiosity's track and drill sites, a ridge target on a ridge pixel and a hollow target
off the ridge map, and the route engine must find a safe route to it from base camp within the
app's default limits on the new rasters.
"""

import csv
import hashlib
import json
import math
import os
import shutil
import sys
from pathlib import Path

import yaml

from contracts.models.route_request import Limits
from contracts.models.site import SiteConfig
from contracts.paths import REPO_ROOT, data_root
from prep.common import publish_stage, sha256
from prep.gale import overlays
from prep.gale.build_pack import (
    APXS_CREDIT,
    APXS_URL,
    CRISM,
    CRISM_URL,
    EVIDENCE,
    SOURCES,
    _git_commit,
)
from prep.gale.layers import (
    build_chemistry_layer,
    build_minerals_layer,
    build_ridges_layer,
    build_sand_layer,
)
from prep.gale.science import check_reachable, check_targets, drill_sites, inside_polygon
from prep.gale.walkability import ridge_raster, sand_raster
from route.engine import daylight_s
from route.layers import load_grid

SITE = REPO_ROOT / "sites" / "gale.yaml"
WALK_AREA = REPO_ROOT / "prep" / "gale" / "walk_area.yaml"
SAND_RASTER = "gale/rasters/sand.tif"
RIDGE_RASTER = "gale/rasters/ridges.tif"
LAYERS = "gale/layers"
STAGE = "gale/layers-2-3.next"
# The app's default walk limits (app/src/plan/routes.ts): a science target must be
# reachable under these, or the app's first route request to it fails.
APP_LIMITS = Limits(
    max_slope_deg=20, max_distance_from_habitat_m=2000, planning_speed_kmh=2, max_walk_h=6
)


def main() -> None:
    if not os.environ.get("REDMARK_DATA"):
        sys.exit("set REDMARK_DATA to the shared data folder; layers never go in the stub data")
    build(data_root())


def build(root: Path) -> None:
    config = SITE.read_bytes()
    spec_text = WALK_AREA.read_bytes()
    site = SiteConfig.model_validate(yaml.safe_load(config))
    spec = yaml.safe_load(spec_text)
    b = site.bounds
    walk = (b.min_x, b.min_y, b.max_x, b.max_y)
    habitat = (site.habitat.x, site.habitat.y)
    zones = [[tuple(p) for p in zone] for zone in spec["boxwork_zones"].values()]
    targets = spec["science_targets"]
    files = site.files
    commit = _git_commit()

    stage = root / STAGE
    shutil.rmtree(stage, ignore_errors=True)
    staged = {
        key: f"{STAGE}/{path}" for key, path in (("sand", SAND_RASTER), ("ridges", RIDGE_RASTER))
    }
    print("sand from thermal inertia")
    sand = sand_raster(root / files["thermal_inertia"], root / staged["sand"])
    print("ridge map from the photo map")
    ridges = ridge_raster(root / files["photo_map"], walk, zones, root / staged["ridges"])

    with (root / files["chemistry"]).open() as f:
        chemistry = list(csv.DictReader(f))
    with (root / files["rover_positions"]).open() as f:
        track = [(float(r["x"]), float(r["y"])) for r in sorted(csv.DictReader(f), key=_sol)]
    drilled = drill_sites(chemistry)
    check_targets(
        targets,
        drill_sites=drilled,
        track=track,
        habitat=habitat,
        walk_radius_m=spec["walk_radius_m"],
        zones=zones,
        ridges=ridges,
    )
    conditions = REPO_ROOT / "conditions" / f"{site.replayed_sol}.json"
    check_reachable(
        targets,
        load_grid(site.model_copy(update={"files": {**files, **staged}}), root),
        start=site.base_camp or site.habitat,
        habitat=site.habitat,
        limits=APP_LIMITS,
        daylight_s=daylight_s(json.loads(conditions.read_text())),
    )
    print(f"{len(targets)} science targets pass; {len(drilled)} drill sites in the crop")

    points = [
        {"x": float(r["x"]), "y": float(r["y"]), "so3": float(r["SO3"]), "drill": False}
        for r in chemistry
    ] + [{"x": d["x"], "y": d["y"], "so3": 0.0, "drill": True} for d in drilled]
    print("layer tiles")
    build_sand_layer(sand, walk, stage / "sand", _source(SOURCES["thermal_inertia"]))
    build_ridges_layer(ridges, walk, stage / "ridges", _source(SOURCES["photo_map"]))
    crism_source = {"name": CRISM["name"], "url": CRISM_URL}
    build_minerals_layer(root / files["crism"], walk, stage / "minerals", crism_source)
    apxs_source = {"name": "MSL APXS RDR concentrations (" + APXS_CREDIT + ")", "url": APXS_URL}
    build_chemistry_layer(points, walk, stage / "chemistry", apxs_source)
    # Each input as (the path it is published at, where it is now).
    inputs = {
        "sand": [(files["thermal_inertia"], root / files["thermal_inertia"]), (SAND_RASTER, sand)],
        "ridges": [(files["photo_map"], root / files["photo_map"]), (RIDGE_RASTER, ridges)],
        "minerals": [(files["crism"], root / files["crism"])],
        "chemistry": [(files["chemistry"], root / files["chemistry"])],
    }
    for name, paths in inputs.items():
        provenance = {
            "script": "prep/gale/build_layers_2_3.py",
            "commit": commit,
            "inputs": [{"path": p, "sha256": sha256(now)} for p, now in paths]
            + [
                {"path": "sites/gale.yaml", "sha256": hashlib.sha256(config).hexdigest()},
                {
                    "path": "prep/gale/walk_area.yaml",
                    "sha256": hashlib.sha256(spec_text).hexdigest(),
                },
            ],
        }
        (stage / name / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")

    print("overlays")
    overlay_dir = stage / "overlays"
    overlay_dir.mkdir(parents=True, exist_ok=True)
    photo = root / files["photo_map"]
    written = [
        overlays.walkability(photo, stage, walk, habitat, zones, track, overlay_dir),
        overlays.ridge_samples(
            photo, stage / "ridges", _sample_areas(spec, track), targets, overlay_dir
        ),
        overlays.science(photo, stage, walk, habitat, targets, drilled, track, overlay_dir),
    ]

    # Everything built and checked: only now does anything live change, the route
    # engine's rasters included.
    (root / LAYERS).mkdir(parents=True, exist_ok=True)
    for name in inputs:
        publish_stage(stage / name, root / LAYERS / name)
    for key, path in (("sand", SAND_RASTER), ("ridges", RIDGE_RASTER)):
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        os.replace(root / staged[key], root / path)
    # The overlays folder holds layer 1's overlays too, so only these files are replaced.
    live_overlays = root / LAYERS / "overlays"
    live_overlays.mkdir(parents=True, exist_ok=True)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    for png in written:
        os.replace(png, live_overlays / png.name)
        shutil.copy(live_overlays / png.name, EVIDENCE / png.name)
    shutil.rmtree(stage, ignore_errors=True)

    _add_to_site_config(targets)
    print(f"layers written to {root / LAYERS}")


def _sample_areas(spec: dict, track) -> list[tuple[str, tuple[float, float]]]:
    """Three places to check the ridge map against the photo: round the two science
    targets, at the centre of the boxwork Curiosity drove through, and at its stop in
    that zone farthest from the centre."""
    targets = spec["science_targets"]
    between = (
        sum(t["x"] for t in targets) / len(targets),
        sum(t["y"] for t in targets) / len(targets),
    )
    zone = [tuple(p) for p in spec["boxwork_zones"]["curiosity_boxwork"]]
    centre = (sum(p[0] for p in zone) / len(zone), sum(p[1] for p in zone) / len(zone))
    stops = [p for p in track if inside_polygon(p, zone)]
    farthest = max(stops, key=lambda p: math.dist(p, centre))
    return [
        ("Round the science targets (south-west field)", between),
        ("Curiosity's boxwork, zone centre", centre),
        ("Curiosity's boxwork, a stop on its track", farthest),
    ]


def _sol(row: dict) -> int:
    return int(row["sol"])


def _source(source: dict) -> dict:
    return {"name": source["name"], "url": source["url"]}


def _add_to_site_config(targets: list[dict]) -> None:
    """Name the sand and ridge rasters and set the science targets in sites/gale.yaml,
    keeping the rest and its header."""
    text = SITE.read_text()
    header = "".join(line + "\n" for line in text.splitlines() if line.startswith("#"))
    config = yaml.safe_load(text)
    config["files"]["sand"] = SAND_RASTER
    config["files"]["ridges"] = RIDGE_RASTER
    config["science_targets"] = [
        {"id": t["id"], "position": {"x": t["x"], "y": t["y"]}, "name": t["name"]} for t in targets
    ]
    SiteConfig.model_validate(config)
    SITE.write_text(header + yaml.safe_dump(config, sort_keys=False, allow_unicode=True))


if __name__ == "__main__":
    main()
