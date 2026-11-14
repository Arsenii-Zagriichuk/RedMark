"""The shared scorer, from worked examples. Expected values are worked by hand."""

import json
from pathlib import Path

from contracts.models import test_summary
from contracts.models.common import Point
from contracts.models.fix_result import FixResult
from contracts.paths import REPO_ROOT
from contracts.scoring import score_fix, write_test_summary

SCRIPT = REPO_ROOT / "locate/horizon/test_gale.py"


def fix(
    x: float = 0.0,
    y: float = 0.0,
    heading_deg: float = 0.0,
    terrain_type: str = "textured",
    photo_id: str = "NLB_0001",
) -> FixResult:
    """An untested horizon fix at (x, y) facing heading_deg."""
    return FixResult(
        photo_id=photo_id,
        site="gale",
        method="horizon",
        position=Point(x=x, y=y),
        heading_deg=heading_deg,
        uncertainty_m=50.0,
        confidence_pct=80.0,
        time_per_fix_s=2.0,
        terrain_type=terrain_type,
        simulated=False,
        overlay="results/horizon/overlays/NLB_0001.png",
        truth=None,
        provenance={"script": "locate/horizon/fix.py", "commit": "abc", "inputs": []},
    )


def test_heading_error_wraps_at_360_degrees():
    # 359° against 1° is 2° apart across north, not 358°.
    scored = score_fix(fix(heading_deg=359.0), Point(x=0.0, y=0.0), true_heading_deg=1.0)
    assert scored.truth.heading_error_deg == 2.0


def test_position_error_is_the_horizontal_distance_in_ground_metres():
    # 3 m east and 4 m north of the true spot: a 3-4-5 triangle, so 5 m.
    scored = score_fix(fix(x=1003.0, y=2004.0), Point(x=1000.0, y=2000.0), true_heading_deg=0.0)
    assert scored.truth.position_error_m == 5.0


def scored_fix(error_m: float, terrain_type: str = "textured") -> FixResult:
    """A tested fix whose position is error_m east of the truth at (0, 0)."""
    return score_fix(
        fix(x=error_m, terrain_type=terrain_type, photo_id=f"{terrain_type}_{error_m}"),
        Point(x=0.0, y=0.0),
        true_heading_deg=0.0,
    )


def summary_of(fixes: list[FixResult], tmp_path: Path, **options) -> test_summary.TestSummary:
    """Write the fixes' test summary and read it back."""
    path = write_test_summary(
        fixes, test="horizon-gale", script=SCRIPT, inputs=[], results_dir=tmp_path, **options
    )
    return test_summary.TestSummary.model_validate(json.loads(path.read_text()))


def test_median_error_overall_and_by_terrain_type(tmp_path):
    # Textured errors 1, 3, 10 m: median 3. Plain errors 2, 20 m: median 11.
    # All five together, 1, 2, 3, 10, 20 m: median 3.
    fixes = [
        scored_fix(1),
        scored_fix(3),
        scored_fix(10),
        scored_fix(2, "plain"),
        scored_fix(20, "plain"),
    ]
    summary = summary_of(fixes, tmp_path)
    assert summary.overall.n == 5
    assert summary.overall.median_error_m == 3.0
    assert summary.groups.textured.n == 3
    assert summary.groups.textured.median_error_m == 3.0
    assert summary.groups.plain.n == 2
    assert summary.groups.plain.median_error_m == 11.0


def test_an_extra_group_gets_the_same_numbers_for_its_photos(tmp_path):
    # A "hollow" split of the textured fixes with errors 3 and 10 m:
    # median 6.5 m, half within 5 m.
    fixes = [scored_fix(1), scored_fix(3), scored_fix(10), scored_fix(2, "plain")]
    summary = summary_of(fixes, tmp_path, extra_groups={"hollow": ["textured_3", "textured_10"]})
    hollow = summary.groups.model_extra["hollow"]
    assert hollow.n == 2
    assert hollow.median_error_m == 6.5
    assert hollow.within_5m_pct == 50.0


def test_exactly_the_limit_counts_as_within_for_1_5_and_10_m(tmp_path):
    # Errors 1, 5, 10, 12 and 30 m: one in five is within 1 m, two within
    # 5 m, three within 10 m, because a fix exactly on the limit counts.
    fixes = [scored_fix(e) for e in (1, 5, 10, 12)] + [scored_fix(30, "plain")]
    summary = summary_of(fixes, tmp_path)
    assert summary.overall.within_1m_pct == 20.0
    assert summary.overall.within_5m_pct == 40.0
    assert summary.overall.within_10m_pct == 60.0


def test_exactly_5_m_counts_as_within_at_real_map_coordinates(tmp_path):
    # 3 m east and 4 m north of a true spot at (1022.9, 160829.8) is exactly
    # 5 m, though floating point puts the raw distance a hair over 5 m.
    on_the_limit = score_fix(
        fix(x=1025.9, y=160833.8), Point(x=1022.9, y=160829.8), true_heading_deg=0.0
    )
    summary = summary_of([on_the_limit, scored_fix(30, "plain")], tmp_path)
    assert summary.overall.within_5m_pct == 50.0


def test_summary_records_the_script_commit_and_input_checksums(tmp_path, monkeypatch):
    data = tmp_path / "data"
    monkeypatch.setenv("REDMARK_DATA", str(data))
    answer_key = data / "gale" / "answer-key.csv"
    answer_key.parent.mkdir(parents=True)
    answer_key.write_bytes(b"abc")
    fixes = [scored_fix(1), scored_fix(2, "plain")]

    path = write_test_summary(
        fixes, test="horizon-gale", script=SCRIPT, inputs=[answer_key], results_dir=tmp_path
    )

    assert path == tmp_path / "horizon" / "horizon-gale.json"
    provenance = json.loads(path.read_text())["provenance"]
    assert provenance["script"] == "locate/horizon/test_gale.py"
    assert len(provenance["commit"]) == 40
    # SHA-256 of "abc", the FIPS 180-2 test vector.
    assert provenance["inputs"] == [
        {
            "path": "gale/answer-key.csv",
            "sha256": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        }
    ]
