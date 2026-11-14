"""layer5-gale.json must still describe the code and landmarks in the repo."""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from contracts.paths import REPO_ROOT

SUMMARY = REPO_ROOT / "layers" / "location_quality" / "layer5-gale.json"
OWN_FOLDER = "layers/location_quality/"


def provenance() -> dict:
    return json.loads(SUMMARY.read_text())["provenance"]


def git_ok(*args: str) -> bool:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True).returncode == 0


def test_the_landmarks_the_layer_was_built_from_are_the_ones_in_the_repo():
    # A changed landmarks.yaml without a rebuild would leave layer 5 describing old landmarks.
    own = [i for i in provenance()["inputs"] if i["path"].startswith(OWN_FOLDER)]
    assert own, "layer5-gale.json records no input from layers/location_quality/"
    for item in own:
        current = hashlib.sha256((REPO_ROOT / item["path"]).read_bytes()).hexdigest()
        assert current == item["sha256"], f"{item['path']} changed since layer 5 was built: rerun"


def test_the_recorded_commit_holds_the_build_script():
    p = provenance()
    if not git_ok("cat-file", "-e", f"{p['commit']}^{{commit}}"):
        pytest.skip(f"commit {p['commit'][:7]} is not in this clone (a shallow CI checkout)")
    assert git_ok("cat-file", "-e", f"{p['commit']}:{p['script']}"), (
        f"{p['script']} is not in the recorded commit {p['commit'][:7]}, so it can't reproduce"
        " the layer: commit the code, then rebuild"
    )
    assert Path(REPO_ROOT / p["script"]).exists()
