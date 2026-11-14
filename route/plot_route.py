"""Overlay image of the fastest safe route on the base map (P4-03), for checking by eye.

Draws the base map tiles, the cells the route may not enter (steeper than the slope
limit or beyond the distance from the habitat), the route, the habitat and its limit
circle. Run with `uv run python -m route.plot_route`; the image goes to
route/overlays/p4-03-fastest.png.
"""

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.image as mpimg  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

from contracts.models.layer import LayerMeta  # noqa: E402
from contracts.models.route_request import RouteRequest  # noqa: E402
from contracts.paths import REPO_ROOT, data_root  # noqa: E402
from route.api import load_site, plan  # noqa: E402
from route.engine import blocked_cells  # noqa: E402
from route.layers import load_grid  # noqa: E402

OUT = REPO_ROOT / "route" / "overlays"
REQUEST = REPO_ROOT / "contracts" / "stubs" / "route" / "request.json"


def main() -> None:
    request = RouteRequest.model_validate(json.loads(REQUEST.read_text()))
    site = load_site(request.site)
    route = plan(request)
    grid = load_grid(site, data_root())
    limits = request.limits

    fig, ax = plt.subplots(figsize=(8, 8))
    base, extent = _base_map(data_root() / site.files["base_map"])
    ax.imshow(base, extent=extent)
    rows, cols = grid.slope_deg.shape
    grid_extent = (
        grid.min_x,
        grid.min_x + cols * grid.cell_m,
        grid.max_y - rows * grid.cell_m,
        grid.max_y,
    )
    blocked = blocked_cells(grid, site.habitat, limits)
    ax.imshow(np.ma.masked_where(~blocked, blocked), extent=grid_extent, cmap="autumn", alpha=0.6)
    ax.add_patch(
        plt.Circle(
            (site.habitat.x, site.habitat.y),
            limits.max_distance_from_habitat_m,
            fill=False,
            ls="--",
            color="white",
            label=f"{limits.max_distance_from_habitat_m:g} m from the habitat",
        )
    )
    ax.plot([p.x for p in route.path], [p.y for p in route.path], c="cyan", lw=2, label="route")
    ax.plot(site.habitat.x, site.habitat.y, "w*", ms=14, label="habitat")
    ax.plot(request.start.x, request.start.y, "go", ms=8, label="start")
    ax.plot(request.goal.x, request.goal.y, "ms", ms=8, label="goal")
    ax.set_xlim(grid_extent[0], grid_extent[1])
    ax.set_ylim(grid_extent[2], grid_extent[3])
    ax.set_title(
        f"P4-03 fastest safe route: {route.total_distance_m:.0f} m, "
        f"{route.total_time_s / 3600:.2f} h, "
        f"walk-back margin {route.walk_back_margin_s / 3600:.1f} h"
        + ("" if "slope" in site.files else "\n(stub layers: flat ground, no slope file yet)")
    )
    ax.set_xlabel("easting, map metres")
    ax.set_ylabel("northing, map metres")
    handles, _ = ax.get_legend_handles_labels()
    shaded = Patch(color=plt.get_cmap("autumn")(0.0), alpha=0.6, label="no route may enter")
    ax.legend(handles=[*handles, shaded], loc="upper right")
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / "p4-03-fastest.png", dpi=120, bbox_inches="tight")
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
