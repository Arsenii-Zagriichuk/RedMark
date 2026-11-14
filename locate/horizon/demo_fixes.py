"""Demo fixes (P3-04): the tested horizon fixes the demo shows, saved in the demo cache.

The frames come from the horizon test's own fix results (P3-03,
results/horizon/fixes/), one per tested stop, picked by a fixed rule so no
one chooses a flattering frame by eye:

- **Photo checkpoint, strong:** the stop on a ridge top or open ground with the
  smallest uncertainty circle that holds its true position.
- **Photo checkpoint, weak:** the hollow stop with the largest position error,
  where nearby ridges hide the skyline. This is the honest weak case.
- **Test lab:** those two, plus the stop on a ridge top or open ground with
  the smallest position error for each terrain type (textured, plain).

Hollow or not comes from the 1 m terrain at the stop's true position, the same
way the horizon test splits its numbers (locate.horizon.stop_terrain).

Each pick becomes one demo cache entry, cache/demo/fixes/<step>.json, holding
the request GET /fixes/horizon/<photo id> and the fix result file as its
response, exactly as the service's recorder would save it. The fix result
names its overlay image in results/horizon/overlays/.

Run with `uv run python -m locate.horizon.demo_fixes`.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from contracts.models.common import TerrainType
from contracts.models.fix_result import FixResult
from contracts.models.test_summary import TestSummary
from contracts.paths import REPO_ROOT, data_root
from locate.horizon.sources import GALE_DEM
from locate.horizon.stop_terrain import classify_stop

CHECKPOINT_STRONG = "checkpoint.fix.horizon"
CHECKPOINT_WEAK = "checkpoint.fix.horizon.weak"
TEST_LAB = "testlab.fix.horizon"
FIXES = "results/horizon/fixes"
TEST_SUMMARY = "results/horizon/horizon-gale.json"
DEMO_CACHE = "cache/demo/fixes"
"""Where the service's recorder saves GET /fixes/... calls: the path's first segment."""
OURS = ("checkpoint-fix-horizon*.json", "testlab-fix-horizon-*.json")


@dataclass(frozen=True)
class ScoredStop:
    """One tested stop: its fix result, scored against PLACES, and whether it is a hollow."""

    fix: FixResult
    hollow: bool


def demo_steps(stops: list[ScoredStop]) -> dict[str, FixResult]:
    """The fix result for each demo step, by demo step id."""
    open_ground = [stop.fix for stop in stops if not stop.hollow]
    hollows = [stop.fix for stop in stops if stop.hollow]
    if not hollows:
        raise ValueError("no hollow stop among the tested stops, so no weak case for the demo")
    holding_truth = [fix for fix in open_ground if fix.truth.position_error_m <= fix.uncertainty_m]
    if not holding_truth:
        raise ValueError("no ridge-top or open stop whose circle holds its true position")
    strong = min(holding_truth, key=lambda fix: fix.uncertainty_m)
    weak = max(hollows, key=lambda fix: fix.truth.position_error_m)
    lab = [strong, weak]
    for kind in TerrainType:
        of_kind = [fix for fix in open_ground if fix.terrain_type == kind and fix not in lab]
        if not of_kind:
            raise ValueError(f"no {kind.value} stop on a ridge top or open ground for the Test lab")
        lab.append(min(of_kind, key=lambda fix: fix.truth.position_error_m))
    return {
        CHECKPOINT_STRONG: strong,
        CHECKPOINT_WEAK: weak,
        **{f"{TEST_LAB}.{fix.photo_id}": fix for fix in lab},
    }


def write_demo_cache(steps: dict[str, FixResult], root: Path) -> list[Path]:
    """Save each step's demo cache entry under root, replacing the demo fixes of an earlier run.

    The response is the fix result file the service serves for that photo, as it is on disk.
    """
    for fix in steps.values():
        if not (root / fix.overlay).is_file():
            raise FileNotFoundError(f"{fix.photo_id} has no overlay image at {fix.overlay}")
    cache = root / DEMO_CACHE
    cache.mkdir(parents=True, exist_ok=True)
    for pattern in OURS:
        for stale in cache.glob(pattern):
            stale.unlink()
    written = []
    for step, fix in steps.items():
        served = root / FIXES / f"{fix.photo_id}.json"
        entry = {
            "step": step,
            "request": {"method": "GET", "path": f"/fixes/horizon/{fix.photo_id}", "body": None},
            "status": 200,
            "contract": "fix_result",
            "response": json.loads(served.read_text()),
        }
        path = cache / f"{step.replace('.', '-')}.json"
        path.write_text(json.dumps(entry, indent=2) + "\n")
        written.append(path)
    return written


def tested_stops(root: Path, dem: Path) -> list[ScoredStop]:
    """Every stop the horizon test scored: the fix results its run wrote with their own overlay.

    The ring's other frames share the stop's overlay, so they are left out.
    """
    summary = TestSummary.model_validate_json((root / TEST_SUMMARY).read_text())
    test_run = (summary.provenance.script, summary.provenance.commit)
    stops = []
    for path in sorted((root / FIXES).glob("*.json")):
        fix = FixResult.model_validate_json(path.read_text())
        same_run = (fix.provenance.script, fix.provenance.commit) == test_run
        if same_run and Path(fix.overlay).stem.endswith(fix.photo_id):
            stop = classify_stop(dem, fix.truth.position.x, fix.truth.position.y)
            stops.append(ScoredStop(fix=fix, hollow=stop.hollow))
    if len(stops) != summary.overall.n:
        raise SystemExit(
            f"found {len(stops)} tested stops, the test summary counts {summary.overall.n}"
        )
    return stops


def main() -> None:
    stops = tested_stops(REPO_ROOT, data_root() / GALE_DEM)
    for path in write_demo_cache(demo_steps(stops), REPO_ROOT):
        entry = json.loads(path.read_text())
        fix = FixResult.model_validate(entry["response"])
        print(
            f"{entry['step']}: {fix.photo_id}, {fix.truth.position_error_m:.0f} m off, "
            f"circle {fix.uncertainty_m:.0f} m, heading {fix.truth.heading_error_deg:.2f}° off"
        )


if __name__ == "__main__":
    main()
