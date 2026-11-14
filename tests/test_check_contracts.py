"""The contract checker behind the smoke test, run on small made-up repos."""

import json
from pathlib import Path

from tools.check_contracts import check

POINT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {"x": {"type": "number"}, "y": {"type": "number"}},
    "required": ["x", "y"],
    "additionalProperties": False,
}


def make_repo(root: Path, registry: str, schemas: dict[str, dict]) -> Path:
    (root / "contracts" / "schemas").mkdir(parents=True)
    (root / "contracts" / "registry.yaml").write_text(registry)
    for name, schema in schemas.items():
        (root / "contracts" / "schemas" / f"{name}.json").write_text(json.dumps(schema))
    return root


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_a_file_that_matches_its_schema_passes(tmp_path):
    repo = make_repo(tmp_path, 'point: ["points/*.json"]\n', {"point": POINT_SCHEMA})
    write(repo / "points" / "a.json", '{"x": 1, "y": 2}')

    assert check(repo, data_root=repo / "data") == []


def test_a_file_missing_a_required_field_is_reported(tmp_path):
    repo = make_repo(tmp_path, 'point: ["points/*.json"]\n', {"point": POINT_SCHEMA})
    write(repo / "points" / "a.json", '{"x": 1}')

    errors = check(repo, data_root=repo / "data")

    assert len(errors) == 1
    assert "points/a.json" in errors[0]
    assert "'y' is a required property" in errors[0]


def test_a_contract_with_no_files_is_reported(tmp_path):
    repo = make_repo(tmp_path, 'point: ["points/*.json"]\n', {"point": POINT_SCHEMA})

    assert check(repo, data_root=repo / "data") == [
        "point: no files match points/*.json (every contract needs at least a stub)"
    ]


def test_yaml_files_are_checked_like_json(tmp_path):
    repo = make_repo(tmp_path, 'point: ["sites/*.yaml"]\n', {"point": POINT_SCHEMA})
    write(repo / "sites" / "gale.yaml", "x: 1\ny: oops\n")

    errors = check(repo, data_root=repo / "data")

    assert errors == ["sites/gale.yaml: 'oops' is not of type 'number' (point)"]


def test_data_patterns_are_found_under_the_data_root(tmp_path):
    repo = make_repo(
        tmp_path / "repo", 'point: ["$DATA/*/layers/*/layer.json"]\n', {"point": POINT_SCHEMA}
    )
    data = tmp_path / "elsewhere"
    write(data / "gale" / "layers" / "slope" / "layer.json", '{"x": 1}')

    errors = check(repo, data_root=data)

    assert errors == [
        f"{data.as_posix()}/gale/layers/slope/layer.json: 'y' is a required property (point)"
    ]


def test_a_results_or_cache_file_no_contract_claims_is_reported(tmp_path):
    repo = make_repo(tmp_path, 'point: ["results/*/summary.json"]\n', {"point": POINT_SCHEMA})
    write(repo / "results" / "drone" / "summary.json", '{"x": 1, "y": 2}')
    write(repo / "results" / "drone" / "sumary.json", '{"x": 1, "y": 2}')
    write(repo / "cache" / "demo" / "walk.json", "{}")
    write(repo / "results" / "drone" / "overlay.png", "not json, so not a contract file")

    assert check(repo, data_root=repo / "data") == [
        "cache/demo/walk.json: no contract in contracts/registry.yaml claims this file",
        "results/drone/sumary.json: no contract in contracts/registry.yaml claims this file",
    ]


CACHE_ENTRY_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {"contract": {"type": ["string", "null"]}, "response": {}},
    "required": ["contract", "response"],
}


def test_a_cached_response_is_checked_against_the_contract_it_names(tmp_path):
    repo = make_repo(
        tmp_path,
        'point: ["points/*.json"]\ndemo_cache: ["cache/demo/*/*.json"]\n',
        {"point": POINT_SCHEMA, "demo_cache": CACHE_ENTRY_SCHEMA},
    )
    write(repo / "points" / "a.json", '{"x": 1, "y": 2}')
    write(
        repo / "cache" / "demo" / "route" / "good.json",
        '{"contract": "point", "response": {"x": 1, "y": 2}}',
    )
    write(
        repo / "cache" / "demo" / "route" / "bad.json",
        '{"contract": "point", "response": {"x": 1}}',
    )
    write(
        repo / "cache" / "demo" / "route" / "raw.json", '{"contract": null, "response": "anything"}'
    )

    assert check(repo, data_root=repo / "data") == [
        "cache/demo/route/bad.json: response: 'y' is a required property (point)"
    ]


def test_a_file_that_does_not_parse_is_reported(tmp_path):
    repo = make_repo(tmp_path, 'point: ["points/*.json"]\n', {"point": POINT_SCHEMA})
    write(repo / "points" / "a.json", '{"x": 1,')

    errors = check(repo, data_root=repo / "data")

    assert len(errors) == 1
    assert errors[0].startswith("points/a.json: does not parse:")


def test_a_schema_can_refer_to_another_schema_by_file_name(tmp_path):
    common = {"$defs": {"point": POINT_SCHEMA}}
    fix = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {"position": {"$ref": "common.json#/$defs/point"}},
        "required": ["position"],
    }
    repo = make_repo(tmp_path, 'fix: ["fixes/*.json"]\n', {"common": common, "fix": fix})
    write(repo / "fixes" / "a.json", '{"position": {"x": 1}}')

    assert check(repo, data_root=repo / "data") == [
        "fixes/a.json: 'y' is a required property (fix)"
    ]


def test_a_registry_entry_without_a_schema_is_reported(tmp_path):
    repo = make_repo(
        tmp_path, 'point: ["points/*.json"]\npiont: ["points/*.json"]\n', {"point": POINT_SCHEMA}
    )
    write(repo / "points" / "a.json", '{"x": 1, "y": 2}')

    assert check(repo, data_root=repo / "data") == ["piont: no schema contracts/schemas/piont.json"]


def test_a_schema_the_registry_never_mentions_is_reported(tmp_path):
    repo = make_repo(
        tmp_path,
        'point: ["points/*.json"]\n',
        {"point": POINT_SCHEMA, "common": {"$defs": {}}, "orphan": POINT_SCHEMA},
    )
    write(repo / "points" / "a.json", '{"x": 1, "y": 2}')

    assert check(repo, data_root=repo / "data") == [
        "orphan: schema has no entry in contracts/registry.yaml, so no file is checked"
    ]
