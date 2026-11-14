"""Generate the Python models and TypeScript types from contracts/schemas/.

    uv run python -m tools.gen_contracts          # rewrite contracts/models and contracts/types
    uv run python -m tools.gen_contracts --check  # fail if they are out of date

The schemas are the single source; never edit the generated files by hand.
The TypeScript side needs `npm ci` in app/ first (it uses json-schema-to-typescript).
"""

import argparse
import filecmp
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from contracts.paths import REPO_ROOT

SCHEMAS = REPO_ROOT / "contracts" / "schemas"
OUTPUTS = {"models": REPO_ROOT / "contracts" / "models", "types": REPO_ROOT / "contracts" / "types"}
IGNORED = ["__pycache__", ".ruff_cache"]
BANNER = "Generated from contracts/schemas by tools/gen_contracts.py. Do not edit by hand."


def generate(out: Path) -> None:
    """Write models/ (Python) and types/ (TypeScript) under out."""
    subprocess.run(
        [
            sys.executable, "-m", "datamodel_code_generator",
            "--input", str(SCHEMAS),
            "--input-file-type", "jsonschema",
            "--output", str(out / "models"),
            "--output-model-type", "pydantic_v2.BaseModel",
            "--target-python-version", "3.11",
            "--use-standard-collections",
            "--use-union-operator",
            "--disable-timestamp",
            "--formatters", "ruff-format",
            "--custom-file-header", f"# {BANNER}",
        ],
        check=True,
        cwd=REPO_ROOT,
    )  # fmt: skip
    npm = shutil.which("npm")
    if npm is None:
        sys.exit("npm not found: install Node 22 LTS")
    subprocess.run(
        [
            npm, "exec", "--prefix", str(REPO_ROOT / "app"), "--no", "--",
            "json2ts",
            "--cwd", str(SCHEMAS),
            "-i", str(SCHEMAS / "*.json"),
            "-o", str(out / "types"),
            "--bannerComment", f"/* {BANNER} */",
        ],
        check=True,
        cwd=REPO_ROOT / "app",
    )  # fmt: skip


def stale(fresh: Path, current: Path) -> list[str]:
    """Files that differ between a fresh generation and what is committed."""
    if not current.is_dir():
        return [f"{current.relative_to(REPO_ROOT)} is missing"]
    problems: list[str] = []

    def walk(cmp: filecmp.dircmp, prefix: str) -> None:
        for name in cmp.left_only + cmp.right_only + cmp.diff_files + cmp.funny_files:
            problems.append(f"{prefix}{name}")
        for sub, child in cmp.subdirs.items():
            walk(child, f"{prefix}{sub}/")

    walk(filecmp.dircmp(fresh, current, ignore=IGNORED), f"{current.relative_to(REPO_ROOT)}/")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if generated files are stale")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        fresh = Path(tmp)
        generate(fresh)
        if args.check:
            problems = [p for name, dest in OUTPUTS.items() for p in stale(fresh / name, dest)]
            for problem in problems:
                print(f"out of date: {problem}")
            if problems:
                print("run: uv run python -m tools.gen_contracts")
            return 1 if problems else 0
        for name, dest in OUTPUTS.items():
            shutil.rmtree(dest, ignore_errors=True)
            shutil.copytree(fresh / name, dest, ignore=shutil.ignore_patterns(*IGNORED))
    print("contracts: generated models and types")
    return 0


if __name__ == "__main__":
    sys.exit(main())
