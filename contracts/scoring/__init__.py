"""The shared scorer: the one implementation of the numbers every test reports.

Both test summaries (drone at Jezero, horizon at Gale) and stage 2 go through
here, so "within 5 m" means the same thing for every method. Usage is in
README.md.
"""

import hashlib
import json
import math
import statistics
import subprocess
from collections.abc import Collection, Mapping, Sequence
from pathlib import Path

from contracts.models.common import Point, Provenance, TerrainType
from contracts.models.fix_result import FixResult, Truth
from contracts.models.test_summary import Metrics, TestSummary
from contracts.paths import REPO_ROOT, data_root


def score_fix(fix: FixResult, true_position: Point, true_heading_deg: float) -> FixResult:
    """The fix with its truth filled in from the answer key."""
    truth = Truth(
        position=true_position,
        heading_deg=true_heading_deg,
        # To the millimetre, so floating-point noise at large map coordinates
        # can't push a fix exactly on a limit (5.000000000000068 m) outside it.
        position_error_m=round(
            math.hypot(fix.position.x - true_position.x, fix.position.y - true_position.y), 3
        ),
        heading_error_deg=_heading_error_deg(fix.heading_deg, true_heading_deg),
    )
    return fix.model_copy(update={"truth": truth})


def write_test_summary(
    fixes: Sequence[FixResult],
    *,
    test: str,
    script: Path,
    inputs: Sequence[Path],
    extra_groups: Mapping[str, Collection[str]] | None = None,
    results_dir: Path = REPO_ROOT / "results",
) -> Path:
    """Score a test's fixes and write its summary to results/<method>/<test>.json.

    Every fix must be scored (have truth) and share one site, method and
    simulated flag. `script` is the file that ran the test; `inputs` are every
    file it read, recorded with their checksums. `extra_groups` adds splits
    beyond terrain type (such as hard_mode or hollow), each a name and the
    photo ids in it.
    """
    if not fixes:
        raise ValueError("a test summary needs at least one fix")
    if any(fix.truth is None for fix in fixes):
        raise ValueError("every fix must be scored with score_fix first")
    first = fixes[0]
    for field in ("site", "method", "simulated"):
        if len({getattr(fix, field) for fix in fixes}) > 1:
            raise ValueError(f"fixes in one test summary must share one {field}")

    groups = {}
    for terrain in TerrainType:
        members = [fix for fix in fixes if fix.terrain_type == terrain]
        if not members:
            raise ValueError(f"no {terrain.value} fixes: every test is split by terrain type")
        groups[terrain.value] = _metrics(members)
    by_photo = {fix.photo_id: fix for fix in fixes}
    for name, photo_ids in (extra_groups or {}).items():
        if name in groups:
            raise ValueError(f"{name} is already a terrain-type group")
        unknown = set(photo_ids) - by_photo.keys()
        if unknown or not photo_ids:
            raise ValueError(f"group {name} needs photos from this test; unknown: {unknown}")
        groups[name] = _metrics([by_photo[photo_id] for photo_id in photo_ids])

    summary = TestSummary(
        test=test,
        site=first.site,
        method=first.method,
        simulated=first.simulated,
        overall=_metrics(fixes),
        groups=groups,
        provenance=_provenance(script, inputs),
    )
    path = results_dir / first.method.value / f"{test}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary.model_dump(mode="json"), indent=2) + "\n")
    return path


def _heading_error_deg(estimate_deg: float, truth_deg: float) -> float:
    """Smallest angle between two headings, 0 to 180°."""
    difference = abs(estimate_deg - truth_deg) % 360.0
    return min(difference, 360.0 - difference)


def _metrics(fixes: Sequence[FixResult]) -> Metrics:
    errors = [fix.truth.position_error_m for fix in fixes]
    return Metrics(
        n=len(fixes),
        median_error_m=statistics.median(errors),
        within_1m_pct=_within_pct(errors, 1.0),
        within_5m_pct=_within_pct(errors, 5.0),
        within_10m_pct=_within_pct(errors, 10.0),
        median_heading_error_deg=statistics.median(fix.truth.heading_error_deg for fix in fixes),
        median_time_per_fix_s=(
            None if fixes[0].simulated else statistics.median(fix.time_per_fix_s for fix in fixes)
        ),
    )


def _within_pct(errors: Sequence[float], limit_m: float) -> float:
    """Share of errors at or under the limit; exactly the limit counts as within."""
    return 100.0 * sum(error <= limit_m for error in errors) / len(errors)


def _provenance(script: Path, inputs: Sequence[Path]) -> Provenance:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=REPO_ROOT, check=True
    ).stdout.strip()
    return Provenance(
        script=_recorded_path(script),
        commit=commit,
        inputs=[{"path": _recorded_path(path), "sha256": _sha256(path)} for path in inputs],
    )


def _sha256(path: Path) -> str:
    """Read in chunks, since an input may be a multi-gigabyte terrain file."""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _recorded_path(path: Path) -> str:
    """Repo-relative for repo files, relative to REDMARK_DATA for data files."""
    path = path.resolve()
    for root in (data_root().resolve(), REPO_ROOT):
        if path.is_relative_to(root):
            return path.relative_to(root).as_posix()
    raise ValueError(f"{path} is neither in the repo nor in REDMARK_DATA")
