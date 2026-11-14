"""The TypeScript types and Python models are generated from the schemas, never by hand."""

import json
import subprocess
import sys

import pytest
from pydantic import ValidationError

from contracts.models.fix_result import FixResult
from contracts.models.test_summary import TestSummary as Summary
from contracts.paths import REPO_ROOT


def test_generated_models_and_types_match_the_schemas():
    result = subprocess.run(
        [sys.executable, "-m", "tools.gen_contracts", "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_the_generated_models_load_a_stub():
    stub = REPO_ROOT / "results" / "horizon" / "fixes" / "stub-navcam-0001.json"

    fix = FixResult.model_validate(json.loads(stub.read_text()))

    assert fix.simulated is False
    assert fix.provenance.script == "stub"


def test_a_test_summary_must_split_by_both_terrain_types():
    stub = REPO_ROOT / "results" / "horizon" / "horizon-gale.json"
    summary = json.loads(stub.read_text())
    del summary["groups"]["plain"]

    with pytest.raises(ValidationError, match="plain"):
        Summary.model_validate(summary)
