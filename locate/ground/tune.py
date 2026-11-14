"""Tune the ground match on the tuning pile: which high-pass scale makes the
overhead views land on the rover's PLACES position.

The tuning pile is seven stops spread over the walk area's traverse (sites 105
to 119), picked for the first look at whether stage 2 can work at all. No stop
within TUNING_CLEARANCE_M of one of them is ever scored.

`uv run python -m locate.ground.tune` fetches the pile into
REDMARK_DATA/gale/ground/tuning, prints each stop's error for every candidate
scale and writes locate/ground/overlays/p3-07-tuning.png at the chosen
HIGHPASS_M.
"""

import numpy as np

from contracts.paths import REPO_ROOT, data_root
from locate.ground.match import HIGHPASS_M, ground_match
from locate.ground.overlay import draw_matches
from locate.ground.pile import fetch_pile, read_pile, walk_area_stops
from locate.horizon.fix import PLACES, read_site_config, rover_position

TUNING_PILE = "gale/ground/tuning"
TUNING_STOPS = {
    (105, 1108),
    (111, 2386),
    (114, 534),
    (116, 408),
    (117, 2370),
    (117, 2730),
    (119, 486),
}
TUNING_CLEARANCE_M = 24.0
"""A mosaic is 24 m across, so stops at least this far apart share no ground in their views."""
CANDIDATE_HIGHPASS_M = (0.5, 1.0, 2.0, 4.0, 8.0)
OVERLAY = REPO_ROOT / "locate" / "ground" / "overlays" / "p3-07-tuning.png"


def main() -> None:
    root = data_root()
    site = read_site_config()
    stops = [
        stop
        for stop in walk_area_stops(root, root / PLACES, site)
        if (stop.site, stop.drive) in TUNING_STOPS
    ]
    if len(stops) != len(TUNING_STOPS):
        raise SystemExit(f"found {len(stops)} of the {len(TUNING_STOPS)} tuning stops")
    photo_map = root / site.files["photo_map"]
    fetch_pile(stops, root / TUNING_PILE, photo_map)
    pile = read_pile(root / TUNING_PILE)

    truth = {stop.photo_id: rover_position(root / PLACES, stop.site, stop.drive) for stop in pile}
    print("stop".ljust(16) + "".join(f"{f'{scale:g} m':>8}" for scale in CANDIDATE_HIGHPASS_M))
    within_5 = dict.fromkeys(CANDIDATE_HIGHPASS_M, 0)
    for stop in pile:
        true_x, true_y = truth[stop.photo_id]
        errors = []
        for scale in CANDIDATE_HIGHPASS_M:
            match = ground_match(stop.window, stop.view, scale)
            error = float(np.hypot(match.x - true_x, match.y - true_y))
            within_5[scale] += error <= 5.0
            errors.append(error)
        print(f"{stop.site} {stop.drive}".ljust(16) + "".join(f"{error:8.1f}" for error in errors))
    counts = "".join(f"{within_5[scale]:>6}/{len(pile)}" for scale in CANDIDATE_HIGHPASS_M)
    print("within 5 m".ljust(16) + counts)

    rows = [(stop, ground_match(stop.window, stop.view), *truth[stop.photo_id]) for stop in pile]
    draw_matches(OVERLAY, f"P3-07 tuning pile, high-pass {HIGHPASS_M:g} m", rows)
    print(f"wrote {OVERLAY.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
