"""Horizon test on the hidden pile (P3-03): the horizon matcher's measured numbers at Gale.

Every stop in the hidden pile (locate.horizon.hidden_pile) gets one fix from
its horizon ring, made exactly as the first fix (P3-02) makes one, with no
setting changed after looking at these frames. That is one fix per stop, not
per frame: one 45° frame alone is too little skyline, as the first fix showed.
Each fix is scored against PLACES through the shared scorer and written with
its overlay. Every other frame of the ring gets a fix result too (frame_fix:
the ring's fix, turned to that frame's pointing, sharing its overlay), so the
Test lab can look up any hidden frame; the run fails if one has none. The
test summary (results/horizon/horizon-gale.json) still counts one fix per
stop, written through the scorer: median position error, heading error and time per fix, overall, by
terrain type, and for hollows against ridge tops and open ground. Both splits
come from the 1 m terrain at the rover's position (locate.horizon.stop_terrain).

Only this script and the one that fetches the pile read the hidden pile.
Run with `uv run python -m locate.horizon.hidden_test`.
"""

import csv
from pathlib import Path

from contracts.models.common import TerrainType
from contracts.paths import data_root
from contracts.scoring import write_test_summary
from locate.horizon.fix import (
    FIXES,
    GRID,
    PLACES,
    SITE_CONFIG,
    frame_fix,
    horizon_commit,
    horizon_fix,
    load_grid,
    read_base_map,
    rover_position,
    write_fix,
)
from locate.horizon.hidden_pile import HIDDEN_PILE
from locate.horizon.navcam import label_pointing
from locate.horizon.sources import GALE_DEM
from locate.horizon.stop_terrain import classify_stop

TEST = "horizon-gale"
INDEX = f"{HIDDEN_PILE}/index.csv"
SCRIPT = "locate/horizon/hidden_test.py"


def main() -> None:
    commit = horizon_commit()
    root = data_root()
    rings = hidden_rings(root / INDEX)
    terrain = {}
    for site_number, drive in rings:
        rover_x, rover_y = rover_position(root / PLACES, site_number, drive)
        terrain[site_number, drive] = classify_stop(root / GALE_DEM, rover_x, rover_y)
    # The scorer splits every test by terrain type; find out before any fix is run.
    for kind in TerrainType:
        if not any(stop.terrain_type == kind for stop in terrain.values()):
            raise SystemExit(f"no {kind.value} stop in the hidden pile, so no test summary")

    grid = load_grid(root)
    base_map = read_base_map(root)
    fixes, hollow, open_ground, frames = [], [], [], []
    for (site_number, drive), labels in rings.items():
        stop = terrain[site_number, drive]
        fix = horizon_fix(
            labels,
            grid,
            root,
            base_map,
            commit=commit,
            terrain=stop.terrain_type,
            overlay_prefix="p3-03",
            script=SCRIPT,
            extra_inputs=(root / GALE_DEM, root / INDEX),
        )
        if fix.photo_id != labels[0].stem:
            raise SystemExit(f"{labels[0].name} names photo {fix.photo_id}")
        for label in labels[1:]:
            heading, _ = label_pointing(label.read_text(errors="ignore"))
            write_fix(frame_fix(fix, label.stem, heading))
        fixes.append(fix)
        (hollow if stop.hollow else open_ground).append(fix.photo_id)
        frames += [path for label in labels for path in (label, label.with_suffix(".IMG"))]
        print(
            f"site {site_number} drive {drive}: {fix.truth.position_error_m:.0f} m, "
            f"heading {fix.truth.heading_error_deg:.2f}°, circle {fix.uncertainty_m:.0f} m, "
            f"{stop.terrain_type.value}, {'hollow' if stop.hollow else 'ridge top or open'}"
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
    missing = frames_without_fix([label for labels in rings.values() for label in labels], FIXES)
    if missing:
        raise SystemExit(f"{len(missing)} hidden frames have no fix result: {missing[:3]}")
    print(f"every one of the {sum(map(len, rings.values()))} hidden frames has its fix result")


def frames_without_fix(labels: list[Path], fixes: Path) -> list[str]:
    """The frames the service would answer 404 for: no results/horizon/fixes/<photo id>.json."""
    return [label.stem for label in labels if not (fixes / f"{label.stem}.json").exists()]


def hidden_rings(index: Path) -> dict[tuple[int, int], list[Path]]:
    """Each hidden stop's ring labels by (site, drive), in the order taken, from the index."""
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
