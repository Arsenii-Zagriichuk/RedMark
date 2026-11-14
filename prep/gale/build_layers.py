"""Build layer 1 at Gale (P2-02): the base map tiles and the slope layer.

    REDMARK_DATA=~/redmark-data uv run python -m prep.gale.build_layers

Reads the walk-area crops the P2-01 pack wrote (the photo map and terrain named
in sites/gale.yaml) and writes, under $REDMARK_DATA/gale/:
  rasters/slope.tif           slope in degrees on the terrain's own 1 m grid, over
                              the whole crop; read by the route engine
  layers/base/                the 25 cm photo map over the walk area, JPEG tiles
  layers/slope/               the slope over the walk area at 1 m, coloured by band
  layers/*/provenance.json    the script, commit and input checksums behind each layer,
                              the site config's among them
  layers/overlays/*.png       slope on the photo map, and the tiles placed by their
                              layer.json against the crop, to check by eye
and, in the repo, `files.slope` in sites/gale.yaml and copies of the overlays in
prep/gale/evidence/.

Each layer is built in gale/layers.next/ and replaces the published folder whole,
so the app never reads half a layer.
"""

import csv
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

import yaml

from contracts.models.site import SiteConfig
from contracts.paths import REPO_ROOT, data_root
from prep.common import publish_stage, sha256
from prep.gale import overlays
from prep.gale.build_pack import EVIDENCE, SOURCES, _git_commit
from prep.gale.layers import build_base_layer, build_slope_layer, slope_raster

SITE = REPO_ROOT / "sites" / "gale.yaml"
SLOPE_RASTER = "gale/rasters/slope.tif"
LAYERS = "gale/layers"
STAGE = "gale/layers.next"


def main() -> None:
    if not os.environ.get("REDMARK_DATA"):
        sys.exit("set REDMARK_DATA to the shared data folder; layers never go in the stub data")
    build(data_root())


def build(root: Path) -> None:
    # The config sets the layers' bounds and names their inputs, so its checksum, as read
    # here, goes in each layer's provenance alongside the input files'.
    config = SITE.read_bytes()
    site = SiteConfig.model_validate(yaml.safe_load(config))
    b = site.bounds
    walk = (b.min_x, b.min_y, b.max_x, b.max_y)
    habitat = (site.habitat.x, site.habitat.y)
    photo = root / site.files["photo_map"]
    terrain = root / site.files["terrain"]
    commit = _git_commit()

    print(f"slope from {terrain}")
    slope = slope_raster(terrain, root / SLOPE_RASTER)

    stage = root / STAGE
    shutil.rmtree(stage, ignore_errors=True)
    print("base map tiles")
    build_base_layer(photo, walk, stage / "base", _source("photo_map"))
    print("slope tiles")
    build_slope_layer(slope, walk, stage / "slope", _source("terrain"))
    inputs = {
        "base": [site.files["photo_map"]],
        "slope": [site.files["terrain"], SLOPE_RASTER],
    }
    for name, paths in inputs.items():
        provenance = {
            "script": "prep/gale/build_layers.py",
            "commit": commit,
            "inputs": [{"path": p, "sha256": sha256(root / p)} for p in paths]
            + [{"path": "sites/gale.yaml", "sha256": hashlib.sha256(config).hexdigest()}],
        }
        (stage / name / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")

    (root / LAYERS).mkdir(parents=True, exist_ok=True)
    for name in inputs:
        publish_stage(stage / name, root / LAYERS / name)
    shutil.rmtree(stage, ignore_errors=True)

    overlay_dir = root / LAYERS / "overlays"
    overlay_dir.mkdir(parents=True, exist_ok=True)
    positions = _rover_positions(root / site.files["rover_positions"], walk)
    overlays.slope_layer(root, photo, root / LAYERS / "slope", walk, habitat, overlay_dir)
    overlays.base_tiles(photo, root / LAYERS / "base", walk, habitat, positions, overlay_dir)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    for png in sorted(overlay_dir.glob("*.png")):
        shutil.copy(png, EVIDENCE / png.name)

    _add_slope_to_site_config()
    print(f"layers written to {root / LAYERS}")


def _source(key: str) -> dict:
    return {"name": SOURCES[key]["name"], "url": SOURCES[key]["url"]}


def _rover_positions(path: Path, walk) -> list[tuple[float, float]]:
    with path.open() as f:
        rows = [(float(r["x"]), float(r["y"])) for r in csv.DictReader(f)]
    return [(x, y) for x, y in rows if walk[0] <= x <= walk[2] and walk[1] <= y <= walk[3]]


def _add_slope_to_site_config() -> None:
    """Name the slope raster in sites/gale.yaml, keeping the rest and its header."""
    text = SITE.read_text()
    header = "".join(line + "\n" for line in text.splitlines() if line.startswith("#"))
    config = yaml.safe_load(text)
    config["files"]["slope"] = SLOPE_RASTER
    SiteConfig.model_validate(config)
    SITE.write_text(header + yaml.safe_dump(config, sort_keys=False, allow_unicode=True))


if __name__ == "__main__":
    main()
