"""Check every contract file in the repo against its JSON Schema.

contracts/registry.yaml maps each contract to the glob patterns where its files
live. A pattern starting with "$DATA/" is looked up under the data root
(REDMARK_DATA); every other pattern is from the repo root. A demo cache entry's
saved response is also checked against the contract the entry names. This
module is the core of the smoke test.

Run it directly with `uv run python -m tools.check_contracts`.
"""

import json
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

DATA_PREFIX = "$DATA/"
# Every JSON file in these folders must belong to some contract.
CLAIMED_FOLDERS = ("cache", "results")
DEMO_CACHE = "demo_cache"
# Schemas that only hold shared definitions; no file is checked against them.
DEFINITIONS_ONLY = {"common"}


def check(repo_root: Path, data_root: Path) -> list[str]:
    """Return one readable message per problem; an empty list means all good."""
    contracts_dir = repo_root / "contracts"
    registry = yaml.safe_load((contracts_dir / "registry.yaml").read_text())
    validators = _validators(contracts_dir / "schemas")
    errors: list[str] = [
        f"{name}: schema has no entry in contracts/registry.yaml, so no file is checked"
        for name in sorted(validators)
        if name not in registry and name not in DEFINITIONS_ONLY
    ]
    claimed: set[Path] = set()
    for contract, patterns in registry.items():
        if contract not in validators:
            errors.append(f"{contract}: no schema contracts/schemas/{contract}.json")
            continue
        paths = [path for pattern in patterns for path in _find(pattern, repo_root, data_root)]
        if not paths:
            errors.append(
                f"{contract}: no files match {', '.join(patterns)}"
                " (every contract needs at least a stub)"
            )
        claimed.update(paths)
        for path in paths:
            errors.extend(_check_file(path, contract, validators, _show(path, repo_root)))
    for folder in CLAIMED_FOLDERS:
        for path in sorted((repo_root / folder).rglob("*.json")):
            if path not in claimed:
                errors.append(
                    f"{_show(path, repo_root)}: no contract in contracts/registry.yaml"
                    " claims this file"
                )
    return errors


def _check_file(
    path: Path, contract: str, validators: dict[str, Draft202012Validator], shown: str
) -> list[str]:
    try:
        document = _load(path)
    except (ValueError, yaml.YAMLError) as error:
        return [f"{shown}: does not parse: {error}"]
    errors = [
        f"{shown}: {error.message} ({contract})"
        for error in validators[contract].iter_errors(document)
    ]
    if contract == DEMO_CACHE and not errors and document["contract"] is not None:
        named = document["contract"]
        if named not in validators:
            return [f"{shown}: names unknown contract {named!r}"]
        errors.extend(
            f"{shown}: response: {error.message} ({named})"
            for error in validators[named].iter_errors(document["response"])
        )
    return errors


def _validators(schemas_dir: Path) -> dict[str, Draft202012Validator]:
    """One validator per schema file; schemas may $ref each other by file name."""
    schemas = {path.stem: json.loads(path.read_text()) for path in schemas_dir.glob("*.json")}
    resources = Registry().with_resources(
        (f"{name}.json", Resource.from_contents(schema, default_specification=DRAFT202012))
        for name, schema in schemas.items()
    )
    return {
        name: Draft202012Validator(schema, registry=resources) for name, schema in schemas.items()
    }


def _find(pattern: str, repo_root: Path, data_root: Path) -> list[Path]:
    if pattern.startswith(DATA_PREFIX):
        return sorted(data_root.glob(pattern.removeprefix(DATA_PREFIX)))
    return sorted(repo_root.glob(pattern))


def _load(path: Path) -> Any:
    text = path.read_text()
    if path.suffix in {".yaml", ".yml"}:
        return yaml.safe_load(text)
    return json.loads(text)


def _show(path: Path, repo_root: Path) -> str:
    if path.is_relative_to(repo_root):
        return path.relative_to(repo_root).as_posix()
    return path.as_posix()


def main() -> int:
    from contracts.paths import REPO_ROOT, data_root

    errors = check(REPO_ROOT, data_root())
    for error in errors:
        print(error)
    print("contracts: ok" if not errors else f"contracts: {len(errors)} problem(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
