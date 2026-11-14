"""Where the repo and the data folder are.

The data folder never goes into git. Its location comes from one setting,
REDMARK_DATA, so every worktree reads the same copy. When it is unset, the
stub data folder in the repo stands in, so nothing waits for real data.
"""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STUB_DATA = REPO_ROOT / "contracts" / "stubs" / "stub-data"


def data_root() -> Path:
    value = os.environ.get("REDMARK_DATA")
    return Path(value).expanduser() if value else STUB_DATA
