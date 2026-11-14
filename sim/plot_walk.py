"""Overlay image of a simulated walk (P4-05), for checking by eye.

Left: the true and estimated tracks on the base map, with the uncertainty circle every
few minutes. Right: the circle's radius through the walk, with each fix and the 10 m
open-ground fix request line. Run with `uv run python -m sim.plot_walk`; the image goes
to sim/overlays/p4-05-walk.png.
"""

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.image as mpimg  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import yaml  # noqa: E402

from contracts.models.layer import LayerMeta  # noqa: E402
from contracts.models.site import SiteConfig  # noqa: E402
from contracts.paths import REPO_ROOT, data_root  # noqa: E402
from sim.engine import FIX_REQUEST_OPEN_GROUND_M, simulate  # noqa: E402

OUT = REPO_ROOT / "sim" / "overlays"
REQUEST = REPO_ROOT / "contracts" / "stubs" / "simulate" / "request.json"
CIRCLE_EVERY_S = 300


def main() -> None:
    request = json.loads(REQUEST.read_text())
    site = SiteConfig.model_validate(
        yaml.safe_load((REPO_ROOT / "sites" / f"{request['site']}.yaml").read_text())
    )
    run = simulate(request)
    steps = run["steps"]
    fixes = [s for s in steps if any(e["kind"] == "fix" for e in s["events"])]

    fig, (ax, chart) = plt.subplots(1, 2, figsize=(15, 7), gridspec_kw={"width_ratios": [1, 1.2]})
    base, extent = _base_map(data_root() / site.files["base_map"])
    ax.imshow(base, extent=extent)
    true = np.array([[s["true_position"]["x"], s["true_position"]["y"]] for s in steps])
    est = np.array([[s["estimated_position"]["x"], s["estimated_position"]["y"]] for s in steps])
    ax.plot(true[:, 0], true[:, 1], c="white", lw=2, label="true track")
    ax.plot(est[:, 0], est[:, 1], c="cyan", lw=1, label="estimated track")
    next_circle_s = 0.0
    for s in steps:
        if s["t_s"] >= next_circle_s or s in fixes:
            centre = (s["estimated_position"]["x"], s["estimated_position"]["y"])
            ax.add_patch(plt.Circle(centre, s["uncertainty_m"], fill=False, color="yellow"))
            next_circle_s = s["t_s"] + CIRCLE_EVERY_S
    for s in fixes:
        ax.plot(s["true_position"]["x"], s["true_position"]["y"], "m*", ms=14)
    ax.plot([], [], "m*", ms=14, label="fix")
    ax.plot([], [], c="yellow", label="uncertainty circle (to scale)")
    margin = 150
    ax.set_xlim(true[:, 0].min() - margin, true[:, 0].max() + margin)
    ax.set_ylim(true[:, 1].min() - margin, true[:, 1].max() + margin)
    ax.set_xlabel("easting, map metres")
    ax.set_ylabel("northing, map metres")
    ax.legend(loc="upper left")
    ax.set_title("SIMULATED walk on the stub base map")

    t = [s["t_s"] / 60 for s in steps]
    chart.plot(t, [s["uncertainty_m"] for s in steps], c="tab:blue", label="uncertainty circle")
    for s in fixes:
        method = next(e["method"] for e in s["events"] if e["kind"] == "fix")
        chart.axvline(s["t_s"] / 60, c="m", ls=":", label=f"{method} fix")
    chart.axhline(FIX_REQUEST_OPEN_GROUND_M, c="tab:red", ls="--", label="fix request, open ground")
    chart.set_xlabel("minutes into the walk")
    chart.set_ylabel("circle radius, ground metres (95%)")
    chart.set_ylim(0, FIX_REQUEST_OPEN_GROUND_M * 1.2)
    chart.legend(loc="upper left")
    chart.set_title(f"SIMULATED: circle grows between fixes, shrinks at a fix (seed {run['seed']})")
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / "p4-05-walk.png", dpi=110, bbox_inches="tight")
    plt.close(fig)


def _base_map(layer_dir):
    """Every tile at the layer's sharpest zoom, stitched, with its extent in map metres."""
    meta = LayerMeta.model_validate(json.loads((layer_dir / "layer.json").read_text()))
    z, size = meta.tiles.max_zoom, meta.tiles.tile_size
    tiles = {}
    for path in (layer_dir / meta.tiles.path.split("{z}")[0] / str(z)).glob("*/*.png"):
        tiles[int(path.parent.name), int(path.stem)] = mpimg.imread(path)[..., :3]
    nx, ny = max(x for x, _ in tiles) + 1, max(y for _, y in tiles) + 1
    mosaic = np.zeros((ny * size, nx * size, 3))
    for (x, y), tile in tiles.items():
        mosaic[y * size : (y + 1) * size, x * size : (x + 1) * size] = tile
    b, span = meta.bounds, size * meta.resolution_m
    return mosaic, (b.min_x, b.min_x + nx * span, b.max_y - ny * span, b.max_y)


if __name__ == "__main__":
    main()
