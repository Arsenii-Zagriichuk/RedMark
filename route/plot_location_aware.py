"""Overlay image of location-aware routing (P4-07), for checking by eye.

The stub map has no location-quality raster, so this draws a made-up 2 x 1 km flat grid:
a quality score from 0 to 1 with a broad patch of poor ground across the straight line,
three checkpoint candidates, and the fastest route with and without location-aware
routing. Run with `uv run python -m route.plot_location_aware`; the image goes to
route/overlays/p4-07-location-aware.png.
"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from contracts.models.common import Point  # noqa: E402
from contracts.models.route_request import Limits  # noqa: E402
from contracts.paths import REPO_ROOT  # noqa: E402
from route.planner import LOCATION_WEIGHT, CheckpointCandidate, CostGrid, plan_on_grid  # noqa: E402

OUT = REPO_ROOT / "route" / "overlays"
CELL_M = 10.0
LIMITS = Limits(
    max_slope_deg=20, max_distance_from_habitat_m=2000, planning_speed_kmh=2, max_walk_h=6
)


def main() -> None:
    rows, cols = 100, 200
    y, x = np.mgrid[0:rows, 0:cols]
    quality = np.clip(1 - np.exp(-(((x - 100) / 35) ** 2 + ((y - 55) / 25) ** 2)), 0, 1)
    flat = np.zeros((rows, cols))
    blank = np.zeros((rows, cols), dtype=bool)
    grid = CostGrid("gale", 0.0, rows * CELL_M, CELL_M, flat, blank, blank, quality)
    start, goal = Point(x=55, y=455), Point(x=1945, y=455)
    candidates = [
        CheckpointCandidate("candidate-a", Point(x=455, y=655), 0.9),
        CheckpointCandidate("candidate-b", Point(x=1005, y=855), 0.95),
        CheckpointCandidate("candidate-c", Point(x=1555, y=655), 0.9),
    ]

    fig, ax = plt.subplots(figsize=(12, 6.5))
    image = ax.imshow(
        quality, extent=(0, cols * CELL_M, 0, rows * CELL_M), cmap="RdYlGn", vmin=0, vmax=1
    )
    fig.colorbar(image, ax=ax, label="location quality (made-up)", shrink=0.8)
    for weight, colour, label in ((0.0, "black", "without"), (LOCATION_WEIGHT, "blue", "with")):
        route = plan_on_grid(
            grid,
            start,
            goal,
            start,
            LIMITS,
            location_weight=weight,
            checkpoint_candidates=candidates,
        )
        ax.plot(
            [p.x for p in route.path],
            [p.y for p in route.path],
            c=colour,
            lw=2,
            label=f"{label} location-aware routing: {route.total_time_s / 60:.0f} min, "
            f"checkpoints {', '.join(c.id[-1] for c in route.checkpoints) or 'none'}",
        )
    for c in candidates:
        ax.plot(c.position.x, c.position.y, "w^", ms=11, mec="black")
        ax.annotate(c.id, (c.position.x, c.position.y), xytext=(6, 6), textcoords="offset points")
    ax.plot([], [], "w^", ms=11, mec="black", label="checkpoint candidate")
    ax.set_xlabel("easting, metres (made-up grid)")
    ax.set_ylabel("northing, metres")
    ax.set_title(
        f"P4-07 location-aware routing, weight {LOCATION_WEIGHT:g}: "
        "the route prefers ground where fixes work"
    )
    ax.legend(loc="lower left", fontsize=8)
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / "p4-07-location-aware.png", dpi=110, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
