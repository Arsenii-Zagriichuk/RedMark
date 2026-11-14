"""The Jezero pack's outputs: site config, label index and frame images."""

import hashlib
from pathlib import Path

import numpy as np

from prep.common import Bounds, sha256
from prep.jezero.site_frame import SITE_PROJ


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


_MIB = 1024 * 1024


def multipart_part_size(size: int, parts: int) -> int:
    """The whole-MiB part size that splits `size` bytes into exactly `parts` parts."""
    for mib in range(1, 5 * 1024 + 1):  # S3 allows parts up to 5 GiB
        if -(-size // (mib * _MIB)) == parts:
            return mib * _MIB
    raise ValueError(f"no whole-MiB part size splits {size} bytes into {parts} parts")


def s3_multipart_etag(path: Path, part_size: int) -> str:
    """S3's ETag for `path` uploaded in `part_size` parts: MD5 of the parts' MD5s."""
    digests = []
    with path.open("rb") as f:
        for part in iter(lambda: f.read(part_size), b""):
            digests.append(hashlib.md5(part).digest())
    return f"{hashlib.md5(b''.join(digests)).hexdigest()}-{len(digests)}"


def label_index(data_root: Path, labels: list[Path]) -> list[dict]:
    """One row per label read: path under REDMARK_DATA, size and SHA-256."""
    return [
        {
            "path": label.relative_to(data_root).as_posix(),
            "size_bytes": label.stat().st_size,
            "sha256": sha256(label),
        }
        for label in sorted(labels)
    ]


def stretch_to_8bit(raw: np.ndarray) -> np.ndarray:
    """A viewable 8-bit image: the 1st to 99th percentile spread over 0 to 255."""
    low, high = np.percentile(raw, [1, 99])
    scaled = (raw.astype(np.float64) - low) / max(high - low, 1.0) * 255.0
    return np.clip(np.round(scaled), 0, 255).astype(np.uint8)
