"""P1-09: the Target preview's Curiosity pictures, as tools/target_pictures.py wrote them."""

import hashlib
import json

import yaml

from contracts.paths import REPO_ROOT

PICTURES = REPO_ROOT / "app" / "src" / "target" / "curiosity-pictures.json"
PUBLIC = REPO_ROOT / "app" / "public"


def _pictures() -> dict:
    return json.loads(PICTURES.read_text(encoding="utf-8"))


def _sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_every_picture_file_matches_its_checksum():
    listed = [*_pictures()["pictures"], _pictures()["fallback"]]
    for picture in listed:
        path = PUBLIC / picture["file"].lstrip("/")
        assert path.is_file(), picture["file"]
        assert _sha256(path) == picture["sha256"], picture["file"]


def test_every_gale_science_target_has_a_picture():
    site = yaml.safe_load((REPO_ROOT / "sites" / "gale.yaml").read_text(encoding="utf-8"))
    pictured = {picture["target"] for picture in _pictures()["pictures"]}
    assert {target["id"] for target in site["science_targets"]} <= pictured


def test_every_picture_credits_curiosity_and_names_its_source():
    for picture in [*_pictures()["pictures"], _pictures()["fallback"]]:
        assert picture["credit"].startswith("NASA/JPL-Caltech")
        assert picture["source_url"].startswith("https://mars.nasa.gov/msl-raw-images/")
