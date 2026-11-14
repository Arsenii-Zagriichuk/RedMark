"""layer5-gale.json must still describe the code and landmarks in the repo."""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from contracts.paths import REPO_ROOT
from layers.location_quality.build import _provenance
from locate.horizon.base_map import LayerImage
from locate.horizon.fix import PLACES
from locate.horizon.sources import FAR_DEM, GALE_DEM

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


def test_a_data_file_linked_from_elsewhere_is_recorded_by_its_path_in_the_data_folder(tmp_path):
    # A big terrain file is often a symlink into another disk or folder. Provenance must
    # name it where the build read it, under REDMARK_DATA, not wherever the link points.
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "dem.tif").write_bytes(b"terrain")
    root = tmp_path / "data"
    for name in (FAR_DEM, PLACES, "gale/layers/base/layer.json"):
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(name.encode())
    (root / GALE_DEM).symlink_to(elsewhere / "dem.tif")
    base_map = LayerImage("Base", None, (0, 1, 0, 1), (root / "gale/layers/base/layer.json",))
    route = REPO_ROOT / "cache/demo/route/plan-route-fastest-sw-ridge-20.json"

    inputs = _provenance(root, base_map, "abc1234", route).inputs

    recorded = {i.path: i.sha256 for i in inputs}
    assert recorded[GALE_DEM] == hashlib.sha256(b"terrain").hexdigest()
    assert list(recorded)[:4] == [GALE_DEM, FAR_DEM, PLACES, "gale/layers/base/layer.json"]
