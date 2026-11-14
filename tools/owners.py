"""Which person owns each path, and the checks that keep work inside one owner's folders.

    uv run python -m tools.owners check [--base origin/main]  # CI: one owner per pull request
    uv run python -m tools.owners guard < hook.json            # Claude Code hook: block edits

The folder table is AGENTS.md's. Anything not listed belongs to Person 1, who owns the
repo root. Shared paths belong to no one owner: any person may change them next to their
own folders, and CODEOWNERS asks for a review. A pull request that changes a schema in
contracts/schemas/ is a contract change, which may touch both sides' folders.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_OWNER = 1
FOLDERS = {
    "app/": 1,
    "service/": 1,
    "pitch/": 1,
    "tools/": 1,
    "tests/": 1,
    "docs/": 1,
    "prep/": 2,
    "sites/": 2,
    "locate/drone/": 2,
    "results/drone/": 2,
    "locate/horizon/": 3,
    "locate/ground/": 3,
    "layers/location_quality/": 3,
    "contracts/scoring/": 3,
    "results/horizon/": 3,
    "results/ground/": 3,
    "route/": 4,
    "sim/": 4,
    "conditions/": 4,
    # Shared: each producer adds files here, and CODEOWNERS asks for the review.
    "contracts/": None,
    "cache/": None,
    "pyproject.toml": None,
    "uv.lock": None,
}
CONTRACT_SCHEMAS = "contracts/schemas/"
PERSON_SETTING = "redmark.person"
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


def owner_of(path: str) -> int | None:
    """The person who owns a repo-relative path, or None for a shared path."""
    matches = [prefix for prefix in FOLDERS if path == prefix or path.startswith(prefix)]
    return FOLDERS[max(matches, key=len)] if matches else REPO_OWNER


def problems(changed: list[str]) -> list[str]:
    """Why a pull request with these changed paths breaks the one-owner rule, if it does."""
    if any(path.startswith(CONTRACT_SCHEMAS) for path in changed):
        return []
    by_owner: dict[int, list[str]] = {}
    for path in sorted(changed):
        owner = owner_of(path)
        if owner is not None:
            by_owner.setdefault(owner, []).append(path)
    if len(by_owner) < 2:
        return []
    return ["this pull request touches more than one owner's folders:"] + [
        f"  Person {owner}: {', '.join(paths)}" for owner, paths in sorted(by_owner.items())
    ]


def _git(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else ""


def check(base: str) -> int:
    changed = _git("diff", "--name-only", "--no-renames", f"{base}...HEAD").splitlines()
    found = problems(changed)
    for line in found:
        print(line)
    if found:
        print("Split it into one pull request per owner, or make it a contract change.")
    else:
        print(f"owners: ok ({len(changed)} changed file(s))")
    return 1 if found else 0


def guard(hook_input: dict) -> str | None:
    """Why a Claude Code edit must be blocked, or None to let it through."""
    tool_input = hook_input.get("tool_input", {})
    if hook_input.get("tool_name") not in EDIT_TOOLS:
        return None
    target = Path(tool_input.get("file_path") or tool_input.get("notebook_path") or "")
    folder = target.parent
    while not folder.exists() and folder != folder.parent:
        folder = folder.parent
    root = _git("rev-parse", "--show-toplevel", cwd=folder)
    if not root or not target.resolve().is_relative_to(Path(root).resolve()):
        return None
    path = target.resolve().relative_to(Path(root).resolve()).as_posix()
    person = _git("config", "--get", PERSON_SETTING, cwd=folder)
    if person not in {"1", "2", "3", "4"}:
        return (
            "Set your person number once for this clone (every worktree reads it): "
            f"git config {PERSON_SETTING} <1-4>. The folder owners are in AGENTS.md."
        )
    owner = owner_of(path)
    if owner is None or owner == int(person):
        return None
    return (
        f"{path} belongs to Person {owner}; you are Person {person}. Stay in your owner's "
        "folders (AGENTS.md). If the change is needed, ask its owner, or make it a contract "
        "change in contracts/."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    check_parser = commands.add_parser("check", help="fail if a change spans two owners")
    check_parser.add_argument("--base", default="origin/main", help="branch the PR merges into")
    commands.add_parser("guard", help="Claude Code PreToolUse hook: block edits outside")
    args = parser.parse_args()
    if args.command == "check":
        return check(args.base)
    reason = guard(json.load(sys.stdin))
    if reason:
        print(reason, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
