"""What the drone scripts record about how a result was made: input checksums,
paths and the commit, refusing to record a commit that does not hold the code."""

import hashlib
import subprocess
from pathlib import Path

from contracts.models.common import Provenance
from contracts.paths import REPO_ROOT, data_root


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def recorded(path: Path) -> str:
    """Relative to REDMARK_DATA for data files, to the repo for repo files."""
    for root in (data_root().resolve(), REPO_ROOT):
        if path.resolve().is_relative_to(root):
            return path.resolve().relative_to(root).as_posix()
    raise ValueError(f"{path} is neither in the repo nor in REDMARK_DATA")


def provenance(
    script: Path,
    code: list[str],
    inputs: list[Path],
    captured_checksums: dict[Path, str] | None = None,
) -> Provenance:
    """`script`'s provenance; stops if any of `code` (repo paths) is uncommitted."""
    # The commit only traces the numbers if the code that made them is in it.
    changed = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no", "--", *code],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=True,
    ).stdout.strip()
    if changed:
        raise SystemExit(f"commit the code first; uncommitted changes:\n{changed}")
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=REPO_ROOT, check=True
    ).stdout.strip()
    captured = captured_checksums or {}
    return Provenance(
        script=recorded(script),
        commit=commit,
        inputs=[
            {"path": recorded(path), "sha256": captured.get(path) or sha256(path)}
            for path in inputs
        ],
    )
