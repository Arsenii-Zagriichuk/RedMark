"""Fetch the pinned conditions products into an explicit REDMARK_DATA folder."""

import hashlib
import urllib.request
from pathlib import Path

import yaml

from contracts.paths import STUB_DATA, data_root


def main() -> None:
    root = data_root()
    if root.resolve() == STUB_DATA.resolve():
        raise SystemExit("Set REDMARK_DATA to an external data folder before downloading.")
    manifest = yaml.safe_load(Path(__file__).with_name("data-manifest.yaml").read_text())
    for entry in manifest["files"]:
        path = root / entry["path"]
        if path.exists():
            data = path.read_bytes()
        else:
            with urllib.request.urlopen(entry["source_url"], timeout=120) as response:
                data = response.read()
        if (
            len(data) != entry["size_bytes"]
            or hashlib.sha256(data).hexdigest() != entry["checksum"]
        ):
            raise SystemExit(f"Size/checksum mismatch: {path}; existing files are not overwritten.")
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as destination:
                destination.write(data)
        print(f"Verified {path}")


if __name__ == "__main__":
    main()
