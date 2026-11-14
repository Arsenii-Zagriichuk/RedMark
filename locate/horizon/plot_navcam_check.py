"""Check one calculated skyline against a real Navcam panorama (P3-01).

Draws the skyline calculated from the grid's terrain, at the camera position,
on top of Curiosity's 360° cylindrical Navcam mosaic from sol 3655 (site 98,
drive 1520), the stop nearest the stub habitat. The mosaic's columns are
heading from north and its rows elevation above the level site frame, so the
two line up with no fitting. Every number comes from the mosaic's label and
the PLACES positions file.

Run with `uv run python -m locate.horizon.plot_navcam_check`; it writes
results/horizon/overlays/p3-01-navcam-sol3655.png.
"""

import csv
import re

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import yaml  # noqa: E402

from contracts.models.site import SiteConfig  # noqa: E402
from contracts.paths import REPO_ROOT, data_root  # noqa: E402
from locate.horizon.grid import (  # noqa: E402
    AZIMUTH_STEP_DEG,
    FINEST_STEP_M,
    NEAREST_M,
    OBSERVER_HEIGHT_M,
    ray_distances,
)
from locate.horizon.navcam import label_number, label_vector  # noqa: E402
from locate.horizon.render import skyline  # noqa: E402
from locate.horizon.sources import FAR_REACH_M, load_gale_terrain  # noqa: E402

MOSAIC = "navcam/N_R000_3655_ILT098CYL_S_1520_UNCORM1"
PLACES = "places/localized_pos.csv"
OUT = REPO_ROOT / "results" / "horizon" / "overlays" / "p3-01-navcam-sol3655.png"
# Views to look at closely: heading from, heading to, elevation from, elevation to.
ZOOMS = [(30, 140, -1, 15), (250, 360, -2, 6)]


def main() -> None:
    root = data_root()
    label = (root / f"{MOSAIC}.LBL").read_text()
    lines, samples = int(label_number(label, "LINES")), int(label_number(label, "LINE_SAMPLES"))
    record_bytes = int(label_number(label, "RECORD_BYTES"))
    image_record = int(re.search(r"\^IMAGE\s*=\s*\([^,]+,\s*(\d+)\)", label).group(1))
    px_per_deg = label_number(label, "MAP_RESOLUTION")
    zero_line = label_number(label, "ZERO_ELEVATION_LINE")
    start_az = label_number(label, "START_AZIMUTH")
    site = int(label_number(label, "COORDINATE_SYSTEM_INDEX"))
    # Site frame: +X north, +Y east.
    north, east, _ = label_vector(label, "PROJECTION_ORIGIN_VECTOR")

    raw = np.fromfile(root / f"{MOSAIC}.IMG", dtype=">i2", offset=(image_record - 1) * record_bytes)
    image = raw[: lines * samples].reshape(lines, samples).astype(np.float32)
    image[image <= 0] = np.nan

    origin = next(
        row
        for row in csv.DictReader((root / PLACES).open())
        if row["frame"] == "SITE" and int(row["site"]) == site
    )
    cam_x = float(origin["easting"]) + east
    cam_y = float(origin["northing"]) + north

    config = yaml.safe_load((REPO_ROOT / "sites/gale.yaml").read_text())
    walk_area = SiteConfig.model_validate(config).bounds
    gale = load_gale_terrain(root, walk_area, root / "gale" / "horizon" / "cache")
    azimuths = np.arange(0.0, 360.0, AZIMUTH_STEP_DEG)
    calculated = skyline(
        gale.terrain,
        cam_x,
        cam_y,
        observer_height_m=OBSERVER_HEIGHT_M,
        azimuths_deg=azimuths,
        distances_m=ray_distances(NEAREST_M, FAR_REACH_M, FINEST_STEP_M, AZIMUTH_STEP_DEG),
    )

    def column(az: float) -> int:
        return int((az - start_az) * px_per_deg)

    def row(elev: float) -> int:
        return int(zero_line - elev * px_per_deg)

    fig, axes = plt.subplots(3, 1, figsize=(22, 14), height_ratios=(1.2, 1, 1))
    for ax, (az0, az1, el0, el1) in zip(axes, [(0, 360, -8, 18), *ZOOMS], strict=True):
        crop = image[row(el1) : row(el0), column(az0) : column(az1)]
        low, high = np.nanpercentile(crop, [2, 98])  # stretch each view on its own
        ax.imshow(
            np.clip((crop - low) / (high - low), 0, 1) ** 0.6,
            cmap="gray",
            extent=(az0, az1, el0, el1),
            aspect="auto",
        )
        ax.plot(azimuths, calculated, c="red", lw=0.8, label="calculated skyline")
        ax.set_xlim(az0, az1)
        ax.set_ylim(el0, el1)
        ax.set_ylabel("elevation, degrees")
    axes[0].set_xticks(range(0, 361, 45), ["N", "NE", "E", "SE", "S", "SW", "W", "NW", "N"])
    axes[0].legend(loc="upper right")
    axes[1].set_title("Zoom: Mount Sharp behind the near mesas (far terrain and curvature)")
    axes[2].set_title("Zoom: the crater rim to the north-west, faint in dust haze")
    axes[2].set_xlabel("heading from map north, degrees")
    axes[0].set_title(
        f"Navcam mosaic sol 3655 (site {site}) with the calculated skyline at "
        f"({cam_x:.0f}, {cam_y:.0f}), eye {OBSERVER_HEIGHT_M} m above the terrain"
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=110, bbox_inches="tight")
    plt.close(fig)
    print(f"camera at ({cam_x:.1f}, {cam_y:.1f}); wrote {OUT.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
