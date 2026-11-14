"""The hidden pile for the stage 2 attempt (P3-07): top-down mosaics kept apart
from tuning.

Every walk-area stop with a VRT mosaic may go in, except stops whose
view (a 24 m north-up square) would share ground with a tuning stop's.
From those, HELD_OUT_STOPS are taken evenly along the traverse (by sol), so the
pile is chosen before any of it is matched.

`uv run python -m locate.ground.hidden_pile` fetches it into HIDDEN_PILE.
Only this script and locate/ground/hidden_test.py name that folder.
"""

from contracts.paths import data_root
from locate.ground.pile import Stop, fetch_pile, walk_area_stops
from locate.ground.tune import TUNING_CLEARANCE_M, TUNING_STOPS
from locate.horizon.fix import PLACES, read_site_config

HIDDEN_PILE = "hidden/ground"
HELD_OUT_STOPS = 40


def held_out(stops: list[Stop]) -> list[Stop]:
    tuning = [stop for stop in stops if (stop.site, stop.drive) in TUNING_STOPS]
    clear = [stop for stop in stops if not any(_views_overlap(stop, t) for t in tuning)]
    if len(clear) <= HELD_OUT_STOPS:
        return clear
    step = (len(clear) - 1) / (HELD_OUT_STOPS - 1)
    return [clear[round(i * step)] for i in range(HELD_OUT_STOPS)]


def _views_overlap(a: Stop, b: Stop) -> bool:
    """Whether two stops' north-up 24 m views share ground: they overlap only
    when they are closer than TUNING_CLEARANCE_M both east-west and north-south."""
    return abs(a.x - b.x) < TUNING_CLEARANCE_M and abs(a.y - b.y) < TUNING_CLEARANCE_M


def main() -> None:
    root = data_root()
    site = read_site_config()
    stops = walk_area_stops(root, root / PLACES, site)
    pile = held_out(stops)
    print(f"{len(stops)} walk-area stops with a top-down mosaic; {len(pile)} held out")
    fetch_pile(pile, root / HIDDEN_PILE, root / site.files["photo_map"])
    print(f"fetched into {HIDDEN_PILE}")


if __name__ == "__main__":
    main()
