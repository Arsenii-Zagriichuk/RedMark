"""Helpers every prep pack shares: checksums, the data manifest and crop files."""

import hashlib
import urllib.request
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import rasterio
import yaml

from contracts.models.data_manifest import DataManifest
from contracts.paths import REPO_ROOT

Bounds = tuple[float, float, float, float]  # min_x, min_y, max_x, max_y
# GeoTIFF tag naming the source version a crop was cut from, so a rerun can skip it.
SOURCE_TAG = "REDMARK_SOURCE"
MANIFEST = REPO_ROOT / "prep" / "data-manifest.yaml"
USER_AGENT = "redmark-prep/0.1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(1 << 24):
            digest.update(block)
    return digest.hexdigest()


def manifest_entry(
    data_root: Path,
    rel_path: str,
    name: str,
    source_url: str,
    credit: str | None = None,
    checksum: str | None = None,
) -> dict:
    """One data-manifest.yaml entry for a file under REDMARK_DATA.

    `checksum` is the file's SHA-256 if already known (the Gale photo map is
    50 GB); otherwise it is computed.
    """
    path = data_root / rel_path
    entry = {
        "name": name,
        "path": rel_path,
        "size_bytes": path.stat().st_size,
        "source_url": source_url,
        "checksum": checksum or sha256(path),
        "checksum_algorithm": "sha256",
    }
    if credit:
        entry["credit"] = credit
    return entry


def merge_manifest(manifest: dict, entries: list[dict], owned: tuple[str, ...]) -> dict:
    """Put `entries` into `manifest` in place of every entry a pack owns.

    A pack owns every path starting with one of `owned`. Other packs' entries
    stay; owned entries a rebuild no longer writes go.
    """
    by_path = {f["path"]: f for f in manifest.get("files") or [] if not f["path"].startswith(owned)}
    by_path.update({e["path"]: e for e in entries})
    return {"files": sorted(by_path.values(), key=lambda f: f["path"])}


def update_manifest(entries: list[dict], owned: tuple[str, ...], path: Path = MANIFEST) -> None:
    """Merge `entries` into prep/data-manifest.yaml, keeping its header comments."""
    text = path.read_text()
    comments = "".join(line + "\n" for line in text.splitlines() if line.startswith("#"))
    merged = merge_manifest(yaml.safe_load(text) or {}, entries, owned)
    DataManifest.model_validate(merged)
    path.write_text(comments + yaml.safe_dump(merged, sort_keys=False, allow_unicode=True))


@contextmanager
def written_atomically(out: Path) -> Iterator[Path]:
    """A temporary path to write; it becomes `out` only if the block finishes.

    One temporary file per writer, so two builds never share it.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    partial = out.with_name(f"{out.name}.{uuid.uuid4().hex}.part")
    try:
        yield partial
        partial.replace(out)
    finally:
        partial.unlink(missing_ok=True)


def source_tag(raster: Path) -> str | None:
    """The source version a crop was cut from, or None if it is missing or untagged."""
    if not raster.exists():
        return None
    with rasterio.open(raster) as src:
        return src.tags().get(SOURCE_TAG)


def download(url: str, dest: Path) -> Path:
    """Fetch `url` to `dest` once; later runs reuse the file."""
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=600) as response, written_atomically(dest) as part:
        with part.open("wb") as f:
            while block := response.read(1 << 20):
                f.write(block)
    return dest
