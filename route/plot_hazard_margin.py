"""Overlay image of the hazard margin (P4-06), for checking by eye.

The stub map has no slope layer, so no hazards; this draws a made-up 400 x 200 m flat grid
with a band of ground too steep to walk, and the fastest route past it with a 5 m and a
25 m uncertainty circle. The route keeps the whole circle off the hazard, so it moves away
as the circle grows. Run with `uv run python -m route.plot_hazard_margin`; the image goes
to route/overlays/p4-06-hazard-margin.png.
"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from contracts.models.common import Point  # noqa: E402
from contracts.models.route_request import Limits  # noqa: E402
from contracts.paths import REPO_ROOT  # noqa: E402
from route.planner import CostGrid, plan_on_grid  # noqa: E402

OUT = REPO_ROOT / "route" / "overlays"
CELL_M = 2.0
LIMITS = Limits(
    max_slope_deg=20, max_distance_from_habitat_m=2000, planning_speed_kmh=2, max_walk_h=6
)


def main() -> None:
    slope = np.zeros((100, 200))
    slope[55:75, 80:120] = 35  # a steep drop south of the straight line
    blank = np.zeros(slope.shape, dtype=bool)
    grid = CostGrid("gale", 0.0, 200.0, CELL_M, slope, blank, blank)
    start, goal = Point(x=11, y=101), Point(x=389, y=101)

    fig, ax = plt.subplots(figsize=(11, 6))
    ax.imshow(
        np.ma.masked_where(slope <= LIMITS.max_slope_deg, slope),
        extent=(0, 400, 0, 200),
        cmap="Reds",
        vmin=0,
        vmax=40,
    )
    for circle_m, colour in ((5, "tab:blue"), (25, "tab:green")):
        route = plan_on_grid(grid, start, goal, start, LIMITS, uncertainty_m=circle_m)
        margin = next(c for c in route.limit_checks if c.limit == "hazard_margin")
        ax.plot(
            [p.x for p in route.path],
            [p.y for p in route.path],
            c=colour,
            lw=2,
            label=f"{circle_m} m circle: {route.total_distance_m:.0f} m, "
            f"nearest hazard {margin.value:.0f} m",
        )
        middle = route.path[len(route.path) // 2]
        ax.add_patch(plt.Circle((middle.x, middle.y), circle_m, fill=False, color=colour))
    ax.plot([], [], "s", c="tab:red", label="ground too steep to walk (hazard)")
    ax.set_xlim(0, 400)
    ax.set_ylim(0, 200)
    ax.set_xlabel("easting, metres (made-up grid)")
    ax.set_ylabel("northing, metres")
    ax.set_title("P4-06 hazard margin: the route keeps the uncertainty circle off the hazard")
    ax.legend(loc="upper right")
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / "p4-06-hazard-margin.png", dpi=110, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
