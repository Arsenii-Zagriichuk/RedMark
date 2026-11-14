"""Seam: the helpers every pack shares write a valid data manifest and whole crop files."""

from pathlib import Path

import pytest
import yaml

from contracts.models.data_manifest import DataManifest
from prep.common import (
    download,
    manifest_entry,
    merge_manifest,
    update_manifest,
    written_atomically,
)

# The SHA-256 of "abc", from FIPS 180-2's worked example.
SHA256_ABC = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def _entry(path: str, name: str = "x") -> dict:
    return {
        "name": name,
        "path": path,
        "size_bytes": 1,
        "source_url": "https://x.org",
        "checksum": "1",
        "checksum_algorithm": "sha256",
    }


def test_manifest_entry_records_size_and_sha256(tmp_path: Path):
    (tmp_path / "jezero").mkdir()
    (tmp_path / "jezero" / "abc.txt").write_bytes(b"abc")

    entry = manifest_entry(
        tmp_path, "jezero/abc.txt", name="Test file", source_url="https://example.org/abc.txt"
    )

    assert entry["size_bytes"] == 3
    assert entry["checksum"] == SHA256_ABC
    assert entry["checksum_algorithm"] == "sha256"
    DataManifest.model_validate({"files": [entry]})


def test_manifest_entry_takes_a_known_checksum_without_reading_the_file(tmp_path: Path):
    (tmp_path / "big.tif").write_bytes(b"abc")

    entry = manifest_entry(tmp_path, "big.tif", "Big", "https://x.org", checksum="cached")

    assert entry["checksum"] == "cached"


def test_merge_replaces_the_owned_entries_and_keeps_the_rest():
    old = {
        "files": [
            _entry("gale/a.tif", "Gale"),
            _entry("jezero/b.json", "Old"),
            _entry("jezero/c.json", "Dropped flight"),
        ]
    }

    merged = merge_manifest(old, [_entry("jezero/b.json", "New")], owned=("jezero/",))

    assert [(f["path"], f["name"]) for f in merged["files"]] == [
        ("gale/a.tif", "Gale"),
        ("jezero/b.json", "New"),
    ]


def test_merge_drops_a_stale_source_at_the_data_root_that_a_pack_owns():
    # The Gale sources sit at the data root, next to other packs' folders.
    old = {
        "files": [
            _entry("MSL_Gale_DEM_Mosaic_1m_v2.tif", "Old terrain"),
            _entry("gale/crops/old.tif", "Old crop"),
            _entry("jezero/b.json", "Jezero"),
        ]
    }
    new = [_entry("MSL_Gale_DEM_Mosaic_1m_v3.tif", "Terrain")]

    merged = merge_manifest(old, new, owned=("gale/", "MSL_Gale_"))

    assert [f["name"] for f in merged["files"]] == ["Terrain", "Jezero"]


def test_update_manifest_keeps_the_header_comments(tmp_path: Path):
    path = tmp_path / "data-manifest.yaml"
    path.write_text("# Header line one\n# Header line two\nfiles: []\n")

    update_manifest([_entry("gale/a.tif")], owned=("gale/",), path=path)

    assert path.read_text().startswith("# Header line one\n# Header line two\n")
    assert yaml.safe_load(path.read_text())["files"] == [_entry("gale/a.tif")]


def test_a_write_that_fails_leaves_no_file_behind(tmp_path: Path):
    out = tmp_path / "crop.tif"

    with pytest.raises(RuntimeError), written_atomically(out) as partial:
        partial.write_bytes(b"half")
        raise RuntimeError("interrupted")

    assert list(tmp_path.iterdir()) == []


def test_a_finished_write_appears_at_its_path(tmp_path: Path):
    out = tmp_path / "sub" / "crop.tif"

    with written_atomically(out) as partial:
        partial.write_bytes(b"whole")

    assert out.read_bytes() == b"whole"
    assert list(out.parent.iterdir()) == [out]


def test_a_download_is_fetched_once_and_then_reused(tmp_path: Path):
    source = tmp_path / "published.csv"
    source.write_bytes(b"sol,target\n")
    dest = tmp_path / "data" / "copy.csv"

    download(source.as_uri(), dest)
    source.write_bytes(b"changed")
    download(source.as_uri(), dest)

    assert dest.read_bytes() == b"sol,target\n"
    assert list(dest.parent.iterdir()) == [dest]
