"""Fail if any file in git is over 5 MB, so crops and terrain never get committed.

Run it with `uv run python -m tools.check_file_sizes`. Map data lives under REDMARK_DATA.
"""

import subprocess
import sys

from contracts.paths import REPO_ROOT

LIMIT_BYTES = 5 * 1024 * 1024


def main() -> int:
    tracked = subprocess.run(
        ["git", "ls-files", "-z"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout.split("\0")
    paths = [REPO_ROOT / name for name in tracked if name]
    too_big = [path for path in paths if path.is_file() and path.stat().st_size > LIMIT_BYTES]
    for path in too_big:
        size_mb = path.stat().st_size / 1024 / 1024
        print(f"{path.relative_to(REPO_ROOT)}: {size_mb:.1f} MB is over the 5 MB limit")
    print("file sizes: ok" if not too_big else "Move big files to REDMARK_DATA instead.")
    return 1 if too_big else 0


if __name__ == "__main__":
    sys.exit(main())
