"""The Jezero pack's outputs: site config, data manifest entries and frame images."""

import hashlib
from pathlib import Path

import numpy as np

from prep.jezero.crop import Bounds
from prep.jezero.frame import SITE_PROJ


def site_config(crops: dict[int, Bounds], files: dict[str, str]) -> dict:
    """sites/jezero.yaml: the site frame and bounds covering every flight crop."""
    boxes = list(crops.values())
    return {
        "site": "jezero",
        "name": "Jezero drone test",
        "projection": SITE_PROJ,
        "bounds": {
            "min_x": min(b[0] for b in boxes),
            "min_y": min(b[1] for b in boxes),
            "max_x": max(b[2] for b in boxes),
            "max_y": max(b[3] for b in boxes),
        },
        "habitat": None,
        "base_camp": None,
        "science_targets": [],
        "checkpoints": [],
        "files": files,
        "replayed_sol": None,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def manifest_entry(
    data_root: Path, rel_path: str, name: str, source_url: str, credit: str | None = None
) -> dict:
    """One data-manifest.yaml entry for a downloaded file under REDMARK_DATA."""
    path = data_root / rel_path
    entry = {
        "name": name,
        "path": rel_path,
        "size_bytes": path.stat().st_size,
        "source_url": source_url,
        "checksum": _sha256(path),
        "checksum_algorithm": "sha256",
    }
    if credit:
        entry["credit"] = credit
    return entry


def merge_manifest(manifest: dict, entries: list[dict]) -> dict:
    """Put `entries` into `manifest`, replacing any entry with the same path."""
    by_path = {f["path"]: f for f in manifest.get("files") or []}
    by_path.update({e["path"]: e for e in entries})
    return {"files": sorted(by_path.values(), key=lambda f: f["path"])}


def stretch_to_8bit(raw: np.ndarray) -> np.ndarray:
    """A viewable 8-bit image: the 1st to 99th percentile spread over 0 to 255."""
    low, high = np.percentile(raw, [1, 99])
    scaled = (raw.astype(np.float64) - low) / max(high - low, 1.0) * 255.0
    return np.clip(np.round(scaled), 0, 255).astype(np.uint8)
