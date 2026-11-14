"""Overlay images for the horizon grid (P3-01), for checking by eye.

- p3-01-grid.png: the grid spots and walk area on a hillshade of the Gale terrain.
- p3-01-skyline.png: the calculated 360° skyline at the spot nearest the
  habitat, to hold against a real Navcam panorama from nearby.

Run with `uv run python -m locate.horizon.plot_grid` after locate.horizon.grid.
Images go to results/horizon/overlays/.
"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import yaml  # noqa: E402

from contracts.models.site import SiteConfig  # noqa: E402
from contracts.paths import REPO_ROOT, data_root  # noqa: E402

OUT = REPO_ROOT / "results" / "horizon" / "overlays"
VIEW_MARGIN_M = 6_000.0


def main() -> None:
    site = SiteConfig.model_validate(yaml.safe_load((REPO_ROOT / "sites/gale.yaml").read_text()))
    horizon = data_root() / "gale" / "horizon"
    grid = np.load(horizon / "grid.npz")
    mid = np.load(horizon / "cache" / "gale-10m.npz")
    OUT.mkdir(parents=True, exist_ok=True)
    _grid_overlay(site, grid, mid)
    _skyline(site, grid)


def _grid_overlay(site: SiteConfig, grid, mid) -> None:
    b = site.bounds
    res, left, top = float(mid["res"]), float(mid["left"]), float(mid["top"])
    rows, cols = mid["heights"].shape
    c0 = max(0, int((b.min_x - VIEW_MARGIN_M - left) / res))
    c1 = min(cols, int((b.max_x + VIEW_MARGIN_M - left) / res))
    r0 = max(0, int((top - b.max_y - VIEW_MARGIN_M) / res))
    r1 = min(rows, int((top - b.min_y + VIEW_MARGIN_M) / res))
    heights = mid["heights"][r0:r1, c0:c1]
    dy, dx = np.gradient(np.nan_to_num(heights, nan=np.nanmean(heights)), res)
    shade = (np.cos(np.radians(45)) - dx + dy) / np.sqrt(1 + dx**2 + dy**2)
    extent = (left + c0 * res, left + c1 * res, top - r1 * res, top - r0 * res)
    fig, ax = plt.subplots(figsize=(8, 8))
    ax.imshow(shade, cmap="gray", extent=extent)
    gx, gy = np.meshgrid(grid["xs"], grid["ys"])
    ax.scatter(gx, gy, s=2, c="tab:red", label=f"{gx.size} grid spots")
    ax.plot(
        [b.min_x, b.max_x, b.max_x, b.min_x, b.min_x],
        [b.min_y, b.min_y, b.max_y, b.max_y, b.min_y],
        c="tab:orange",
        label="walk area",
    )
    if site.habitat:
        ax.plot(site.habitat.x, site.habitat.y, "c*", ms=12, label="habitat")
    ax.set_title("P3-01 horizon grid on the Gale 1 m terrain (10 m hillshade)")
    ax.set_xlabel("easting, map metres")
    ax.set_ylabel("northing, map metres")
    ax.legend(loc="upper right")
    fig.savefig(OUT / "p3-01-grid.png", dpi=120, bbox_inches="tight")
    plt.close(fig)


def _skyline(site: SiteConfig, grid) -> None:
    target = site.habitat or site.base_camp
    ix = int(np.abs(grid["xs"] - target.x).argmin())
    iy = int(np.abs(grid["ys"] - target.y).argmin())
    az, elevation = grid["azimuths_deg"], grid["elevation_deg"][iy, ix]
    fig, ax = plt.subplots(figsize=(14, 3.5))
    ax.fill_between(az, elevation, elevation.min() - 1, color="sienna", alpha=0.6)
    ax.plot(az, elevation, c="black", lw=0.8)
    ax.set_xlim(0, 360)
    ax.set_xticks(range(0, 361, 45), ["N", "NE", "E", "SE", "S", "SW", "W", "NW", "N"])
    ax.set_ylabel("elevation, degrees")
    ax.set_title(
        f"Calculated skyline at ({grid['xs'][ix]:.0f}, {grid['ys'][iy]:.0f}), "
        f"ground {grid['ground_m'][iy, ix]:.0f} m; heading from map north"
    )
    ax.grid(alpha=0.3)
    fig.savefig(OUT / "p3-01-skyline.png", dpi=120, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
