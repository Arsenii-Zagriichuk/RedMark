"""Overlay image of the three routes on the base map (P4-03, P4-04), for checking by eye.

Draws the base map tiles, the cells the crew may not enter (steeper than the slope limit,
no slope data, or beyond the distance from the habitat), the ridges the cart may not cross,
the fastest route and the science alternative from the base camp, the cart's route from
the habitat to the base camp, the science targets and the habitat's limit circle. Run with
`uv run python -m route.plot_route`; the image goes to route/overlays/p4-04-routes.png.
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
from contracts.models.route_response import RouteResponse  # noqa: E402
from contracts.paths import REPO_ROOT, data_root  # noqa: E402
from route.engine import load_site, plan  # noqa: E402
from route.layers import load_grid  # noqa: E402
from route.planner import blocked_cells  # noqa: E402

OUT = REPO_ROOT / "route" / "overlays"
REQUEST = REPO_ROOT / "contracts" / "stubs" / "route" / "request.json"
VIEW_MARGIN_M = 300
COLOURS = {"fastest": "cyan", "science": "lime", "cart": "orange"}


def main() -> None:
    request = RouteRequest.model_validate(json.loads(REQUEST.read_text()))
    site = load_site(request.site)
    walk = request.model_dump(mode="json")
    habitat = site.habitat.model_dump()
    requests = {
        "fastest": walk,
        "science": walk | {"mode": "science"},
        "cart": walk | {"mode": "cart", "start": habitat, "goal": site.base_camp.model_dump()},
    }
    routes = {mode: RouteResponse.model_validate(plan(body)) for mode, body in requests.items()}
    grid = load_grid(site, data_root())
    limits = request.limits

    fig, ax = plt.subplots(figsize=(9, 9))
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
    ax.imshow(np.ma.masked_where(~grid.ridge, grid.ridge), extent=grid_extent, cmap="Greys_r")
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
    for mode, route in routes.items():
        label = f"{mode}: {route.total_distance_m:.0f} m, {route.total_time_s / 60:.0f} min"
        if route.extra_time_vs_fastest_s is not None:
            label += f" (+{route.extra_time_vs_fastest_s / 60:.0f} min)"
        xs, ys = [p.x for p in route.path], [p.y for p in route.path]
        ax.plot(xs, ys, c=COLOURS[mode], lw=2, label=label)
    for target in site.science_targets:
        ax.plot(target.position.x, target.position.y, "y^", ms=11)
        ax.annotate(
            target.id,
            (target.position.x, target.position.y),
            color="yellow",
            xytext=(6, 6),
            textcoords="offset points",
        )
    ax.plot([], [], "y^", ms=11, label="science target")
    ax.plot(site.habitat.x, site.habitat.y, "w*", ms=14, label="habitat")
    ax.plot(site.base_camp.x, site.base_camp.y, "ms", ms=9, label="base camp")
    points = [p for route in routes.values() for p in route.path]
    ax.set_xlim(min(p.x for p in points) - VIEW_MARGIN_M, max(p.x for p in points) + VIEW_MARGIN_M)
    ax.set_ylim(min(p.y for p in points) - VIEW_MARGIN_M, max(p.y for p in points) + VIEW_MARGIN_M)
    ax.set_title(
        "P4-04 fastest, science and cart routes"
        + (
            ""
            if "slope" in site.files
            else "\n(stub layers: flat ground, no slope or ridge file yet)"
        )
    )
    ax.set_xlabel("easting, map metres")
    ax.set_ylabel("northing, map metres")
    handles, _ = ax.get_legend_handles_labels()
    shaded = Patch(color=plt.get_cmap("autumn")(0.0), alpha=0.6, label="crew may not enter")
    ridge = Patch(color="white", label="ridge (cart may not cross)")
    ax.legend(handles=[*handles, shaded, ridge], loc="upper left", fontsize=8)
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / "p4-04-routes.png", dpi=120, bbox_inches="tight")
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
