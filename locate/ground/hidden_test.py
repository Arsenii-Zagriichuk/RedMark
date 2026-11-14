"""The stage 2 test on the hidden pile (P3-07): one ground fix per held-out stop,
scored against PLACES through the shared scorer.

`uv run python -m locate.ground.hidden_test` (after locate.ground.hidden_pile)
writes a fix result per stop to results/ground/fixes/, its overlay to
results/ground/overlays/, all of them on one sheet for the pull request, and the
test summary to results/ground/ground-gale-attempt.json. It ends with the go or
no-go call: go when at least GO_WITHIN_5M_PCT of the fixes are within 5 m.

The summary is the attempt's, not stage 2's result for the app: ground-gale.json
stays as it is until P3-08 decides what stage 2 hands on.
"""

import csv
import json
import time
from pathlib import Path

from contracts.models.common import Method, Point, Provenance, SiteId
from contracts.models.fix_result import FixResult
from contracts.paths import REPO_ROOT, data_root
from contracts.scoring import score_fix, write_test_summary
from locate.ground.hidden_pile import HIDDEN_PILE
from locate.ground.match import HIGHPASS_M, ground_match
from locate.ground.overlay import draw_matches
from locate.ground.pile import SEARCH_HALF_M, PileStop, read_pile
from locate.horizon.fix import PLACES, SITE_CONFIG
from locate.horizon.sources import GALE_DEM, git_commit, sha256_file
from locate.horizon.stop_terrain import classify_stop

TEST = "ground-gale-attempt"
INDEX = f"{HIDDEN_PILE}/index.csv"
SCRIPT = "locate/ground/hidden_test.py"
GO_WITHIN_5M_PCT = 50.0
FIXES = REPO_ROOT / "results" / "ground" / "fixes"
OVERLAYS = REPO_ROOT / "results" / "ground" / "overlays"
SHEET = OVERLAYS / "p3-07-held-out.png"


def main() -> None:
    root = data_root()
    commit = git_commit(
        "locate/ground/*.py", "locate/horizon/*.py", "contracts/scoring", SITE_CONFIG
    )
    pile = read_pile(root / HIDDEN_PILE)
    answer_key = places_poses(root / PLACES)
    fixes, rows = [], []
    for stop in pile:
        started = time.perf_counter()
        match = ground_match(stop.window, stop.view)
        elapsed = time.perf_counter() - started
        true_x, true_y, true_heading = answer_key[stop.site, stop.drive]
        overlay = OVERLAYS / f"p3-07-{stop.photo_id}.png"
        fix = FixResult(
            photo_id=stop.photo_id,
            site=SiteId.gale,
            method=Method.ground,
            position=Point(x=match.x, y=match.y),
            # The overhead view is north-up by the rover's own attitude, so the
            # ground fix carries the rover's onboard heading rather than measuring one.
            heading_deg=stop.heading_deg % 360.0,
            # The match promises nothing tighter than the area it searched.
            uncertainty_m=SEARCH_HALF_M,
            confidence_pct=0.0,  # what confidence measures is still open in the contracts
            time_per_fix_s=round(elapsed, 2),
            terrain_type=classify_stop(root / GALE_DEM, true_x, true_y).terrain_type,
            simulated=False,
            overlay=overlay.relative_to(REPO_ROOT).as_posix(),
            truth=None,
            provenance=_provenance(stop, root, commit),
        )
        fix = score_fix(fix, Point(x=true_x, y=true_y), true_heading)
        draw_matches(
            overlay, f"P3-07 ground fix, {fix.terrain_type.value}", [(stop, match, true_x, true_y)]
        )
        FIXES.mkdir(parents=True, exist_ok=True)
        (FIXES / f"{fix.photo_id}.json").write_text(
            json.dumps(fix.model_dump(mode="json"), indent=2) + "\n"
        )
        fixes.append(fix)
        rows.append((stop, match, true_x, true_y))
        print(
            f"site {stop.site} drive {stop.drive}: {fix.truth.position_error_m:6.1f} m, "
            f"{fix.terrain_type.value}, peak {match.peak:.2f} vs {match.runner_up:.2f}"
        )

    draw_matches(
        SHEET,
        f"P3-07 held-out stops, high-pass {HIGHPASS_M:g} m, search ±{SEARCH_HALF_M:g} m",
        rows,
    )
    summary = write_test_summary(
        fixes,
        test=TEST,
        script=Path(__file__),
        inputs=[
            root / PLACES,
            root / GALE_DEM,
            root / INDEX,
            SITE_CONFIG,
            *[path for stop in pile for path in stop.files],
        ],
    )
    within_5m = json.loads(summary.read_text())["overall"]["within_5m_pct"]
    print(f"wrote {summary.relative_to(REPO_ROOT)}")
    call = "GO" if within_5m >= GO_WITHIN_5M_PCT else "NO-GO"
    print(
        f"{call}: {within_5m:.0f}% of {len(fixes)} held-out fixes within 5 m "
        f"(go needs {GO_WITHIN_5M_PCT:.0f}%)"
    )


def places_poses(places: Path) -> dict[tuple[int, int], tuple[float, float, float]]:
    """Every rover stop's (easting, northing, heading from north) in PLACES."""
    with places.open() as f:
        return {
            (int(row["site"]), int(row["drive"])): (
                float(row["easting"]),
                float(row["northing"]),
                float(row["yaw"]) % 360.0,
            )
            for row in csv.DictReader(f)
            if row["frame"] == "ROVER"
        }


def _provenance(stop: PileStop, root: Path, commit: str) -> Provenance:
    inputs = [root / PLACES, root / GALE_DEM, root / INDEX, SITE_CONFIG, *stop.files]
    return Provenance(
        script=SCRIPT,
        commit=commit,
        inputs=[{"path": _recorded(path, root), "sha256": sha256_file(path)} for path in inputs],
    )


def _recorded(path: Path, root: Path) -> str:
    path = path.resolve()
    for base in (root.resolve(), REPO_ROOT):
        if path.is_relative_to(base):
            return path.relative_to(base).as_posix()
    raise ValueError(f"{path} is neither in REDMARK_DATA nor in the repo")


if __name__ == "__main__":
    main()
