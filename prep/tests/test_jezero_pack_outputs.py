"""Seam: the pack's contract files validate, and its frame images are viewable."""

from pathlib import Path

import numpy as np
import pytest

from contracts.models.data_manifest import DataManifest
from contracts.models.site import SiteConfig
from prep.jezero.pack import (
    label_index,
    manifest_entry,
    merge_manifest,
    multipart_part_size,
    s3_multipart_etag,
    site_config,
    stretch_to_8bit,
)
from prep.jezero.site_frame import SITE_PROJ


def test_site_config_covers_every_crop_and_validates():
    crops = {
        10: (4353900.0, 1092100.0, 4354400.0, 1092600.0),
        11: (4353000.0, 1092000.0, 4353800.0, 1092500.0),
    }
    files = {"crop_flight_10": "jezero/pack/crops/flight-10.tif"}

    config = site_config(crops, files)

    SiteConfig.model_validate(config)
    assert config["site"] == "jezero"
    assert config["projection"] == SITE_PROJ
    assert config["bounds"] == {
        "min_x": 4353000.0,
        "min_y": 1092000.0,
        "max_x": 4354400.0,
        "max_y": 1092600.0,
    }
    assert config["files"] == files
    assert config["habitat"] is None and config["replayed_sol"] is None


def test_manifest_entry_records_size_and_sha256(tmp_path: Path):
    (tmp_path / "jezero").mkdir()
    (tmp_path / "jezero" / "abc.txt").write_bytes(b"abc")

    entry = manifest_entry(
        tmp_path, "jezero/abc.txt", name="Test file", source_url="https://example.org/abc.txt"
    )

    assert entry["size_bytes"] == 3
    # The SHA-256 of "abc", from FIPS 180-2's worked example.
    assert entry["checksum"] == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert entry["checksum_algorithm"] == "sha256"
    DataManifest.model_validate({"files": [entry]})


def test_merge_manifest_replaces_the_jezero_entries_and_keeps_the_rest():
    old = {
        "files": [
            {
                "name": "Gale",
                "path": "gale/a.tif",
                "size_bytes": 1,
                "source_url": "https://x.org",
                "checksum": "1",
                "checksum_algorithm": "sha256",
            },
            {
                "name": "Old",
                "path": "jezero/b.json",
                "size_bytes": 1,
                "source_url": "https://x.org",
                "checksum": "1",
                "checksum_algorithm": "sha256",
            },
        ]
    }
    new = [
        {
            "name": "New",
            "path": "jezero/b.json",
            "size_bytes": 2,
            "source_url": "https://x.org",
            "checksum": "2",
            "checksum_algorithm": "sha256",
        },
    ]

    old["files"].append(dict(old["files"][1], name="Dropped flight", path="jezero/c.json"))

    merged = merge_manifest(old, new, replace_prefix="jezero/")

    assert [(f["path"], f["name"]) for f in merged["files"]] == [
        ("gale/a.tif", "Gale"),
        ("jezero/b.json", "New"),
    ]


def test_stretch_maps_the_1st_and_99th_percentiles_to_black_and_white():
    raw = np.arange(1000, 2000, dtype=np.int16).reshape(10, 100)

    image = stretch_to_8bit(raw)

    assert image.dtype == np.uint8
    assert image.min() == 0 and image.max() == 255
    # The middle value sits in the middle of the range.
    assert image[5, 0] == pytest.approx(128, abs=2)


def test_s3_multipart_etag_of_a_small_file(tmp_path: Path):
    # S3's multipart ETag: MD5 of the parts' MD5s, then "-<part count>".
    # "0123456789" in 4-byte parts is "0123", "4567", "89".
    path = tmp_path / "digits.bin"
    path.write_bytes(b"0123456789")

    assert s3_multipart_etag(path, part_size=4) == "61e3716e3a7767581863b67c4e785584-3"


def test_part_size_from_the_jezero_map_etag():
    # USGS's Jezero map: 7,358,523,457 bytes, ETag "...-878". 878 parts of
    # 8 MiB (the AWS CLI default) is the only whole-MiB size that fits.
    assert multipart_part_size(7_358_523_457, parts=878) == 8 * 1024 * 1024


def test_label_index_lists_each_label_with_its_sha256(tmp_path: Path):
    (tmp_path / "jezero").mkdir()
    (tmp_path / "jezero" / "a.xml").write_bytes(b"abc")

    rows = label_index(tmp_path, [tmp_path / "jezero" / "a.xml"])

    assert rows == [
        {
            "path": "jezero/a.xml",
            "size_bytes": 3,
            "sha256": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        }
    ]
