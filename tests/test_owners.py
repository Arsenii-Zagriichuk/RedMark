"""The owner check behind CI: a pull request stays inside one owner's folders."""

import pytest

from tools.owners import owner_of, problems


@pytest.mark.parametrize(
    ("path", "person"),
    [
        ("app/src/App.tsx", 1),
        ("service/app.py", 1),
        ("tests/smoke/test_smoke.py", 1),
        ("AGENTS.md", 1),
        (".github/workflows/ci.yml", 1),
        (".claude/settings.json", 1),
        ("prep/jezero/crop.py", 2),
        ("sites/gale.yaml", 2),
        ("locate/drone/match.py", 2),
        ("results/drone/drone-jezero.json", 2),
        ("locate/horizon/grid.py", 3),
        ("locate/ground/overhead.py", 3),
        ("layers/location_quality/visibility.py", 3),
        ("contracts/scoring/__init__.py", 3),
        ("results/horizon/fixes/stub-navcam-0001.json", 3),
        ("results/ground/ground-gale.json", 3),
        ("route/engine.py", 4),
        ("sim/kalman.py", 4),
        ("conditions/4600.json", 4),
    ],
)
def test_each_folder_belongs_to_its_owner(path, person):
    assert owner_of(path) == person


@pytest.mark.parametrize(
    "path",
    [
        "contracts/schemas/fix_result.json",
        "contracts/stubs/route/request.json",
        "cache/demo/route/planning-route-fastest.json",
        "pyproject.toml",
        "uv.lock",
    ],
)
def test_shared_paths_belong_to_no_one_owner(path):
    assert owner_of(path) is None


def test_a_change_inside_one_owners_folders_passes():
    assert problems(["locate/horizon/grid.py", "results/horizon/overlays/grid.png"]) == []


def test_dependency_files_and_stubs_may_come_with_one_owners_change():
    changed = ["prep/jezero/pack.py", "pyproject.toml", "uv.lock", "contracts/stubs/x.csv"]

    assert problems(changed) == []


def test_a_change_across_two_owners_fails_and_names_both():
    changed = ["conditions/mars24.py", "tests/test_p4_02_conditions.py", "conditions/4600.json"]

    assert problems(changed) == [
        "this pull request touches more than one owner's folders:",
        "  Person 1: tests/test_p4_02_conditions.py",
        "  Person 4: conditions/4600.json, conditions/mars24.py",
    ]


def test_a_contract_change_may_touch_both_sides():
    changed = ["contracts/schemas/route_response.json", "route/engine.py", "app/src/api.ts"]

    assert problems(changed) == []


def test_no_changes_pass():
    assert problems([]) == []
