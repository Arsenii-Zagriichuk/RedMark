"""Horizon test on the hidden pile (P3-03): the horizon matcher's measured numbers at Gale.

Every stop in the hidden pile (locate.horizon.hidden_pile) gets one fix from
its horizon ring, made exactly as the first fix (P3-02) makes one, with no
setting changed after looking at these frames. Each fix is scored against
PLACES through the shared scorer and written with its overlay, and the test
summary (results/horizon/horizon-gale.json) is written through the scorer
too: median position error, heading error and time per fix, overall, by
terrain type, and for hollows against ridge tops and open ground. Both labels
come from the 1 m terrain at the rover's position (locate.horizon.terrain_labels).

Only this script and the one that fetches the pile read the hidden pile.
Run with `uv run python -m locate.horizon.hidden_test`.
"""

import csv
from pathlib import Path

import yaml

from contracts.models.site import SiteConfig
from contracts.paths import data_root
from contracts.scoring import write_test_summary
from locate.horizon.base_map import read_layer_image
from locate.horizon.fix import (
    BASE_MAP_PIXELS,
    GRID,
    PLACES,
    SITE_CONFIG,
    horizon_fix,
    load_grid,
    rover_position,
)
from locate.horizon.hidden_pile import HIDDEN_PILE
from locate.horizon.sources import GALE_DEM
from locate.horizon.terrain_labels import label_stop

TEST = "horizon-gale"
INDEX = f"{HIDDEN_PILE}/index.csv"


def main() -> None:
    root = data_root()
    grid = load_grid(root)
    site = SiteConfig.model_validate(yaml.safe_load(SITE_CONFIG.read_text()))
    base_map = read_layer_image(root / site.files["base_map"], pixels_across=BASE_MAP_PIXELS)

    fixes, hollow, open_ground, frames = [], [], [], []
    for (site_index, drive), labels in stops(root / INDEX).items():
        rover_x, rover_y = rover_position(root / PLACES, site_index, drive)
        stop = label_stop(root / GALE_DEM, rover_x, rover_y)
        fix = horizon_fix(
            labels, grid, root, base_map, terrain=stop.terrain_type, overlay_prefix="p3-03"
        )
        fixes.append(fix)
        (hollow if stop.hollow else open_ground).append(fix.photo_id)
        frames += [path for label in labels for path in (label, label.with_suffix(".IMG"))]
        print(
            f"site {site_index} drive {drive}: {fix.truth.position_error_m:.0f} m, "
            f"heading {fix.truth.heading_error_deg:.2f}°, {stop.terrain_type.value}, "
            f"{'hollow' if stop.hollow else 'ridge top or open'}"
        )

    groups = {"hollow": hollow, "ridge_top_or_open": open_ground}
    for name in [name for name, members in groups.items() if not members]:
        print(f"no {name} stops in the hidden pile: that group is left out")
        del groups[name]
    summary = write_test_summary(
        fixes,
        test=TEST,
        script=Path(__file__),
        inputs=[
            root / GRID,
            root / PLACES,
            root / GALE_DEM,
            root / INDEX,
            SITE_CONFIG,
            *base_map.files,
            *frames,
        ],
        extra_groups=groups,
    )
    print(f"wrote {summary}")


def stops(index: Path) -> dict[tuple[int, int], list[Path]]:
    """Each hidden stop's ring labels, in the order they were taken, from the pile's index."""
    rings: dict[tuple[int, int], list[Path]] = {}
    with index.open() as f:
        for row in csv.DictReader(f):
            if row["file"].endswith(".LBL"):
                rings.setdefault((int(row["site"]), int(row["drive"])), []).append(
                    index.parent / row["file"]
                )
    return {stop: sorted(labels) for stop, labels in rings.items()}


if __name__ == "__main__":
    main()
