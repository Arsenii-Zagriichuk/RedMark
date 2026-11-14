"""The service shell: it serves the contract files, plugs in Person 4's engines and
records live responses into the demo cache."""

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from contracts.paths import REPO_ROOT
from service.app import Settings, create_app

ROUTE_REQUEST = json.loads((REPO_ROOT / "contracts/stubs/route/request.json").read_text())
ROUTE_STUB = json.loads((REPO_ROOT / "contracts/stubs/route/response.json").read_text())
SIMULATE_REQUEST = json.loads((REPO_ROOT / "contracts/stubs/simulate/request.json").read_text())
SIMULATE_STUB = json.loads((REPO_ROOT / "contracts/stubs/simulate/response.json").read_text())
NO_ENGINE = "redmark_test_no_such_package.engine"


def write(path: Path, content: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content)


@pytest.fixture
def repo(tmp_path):
    """A small repo and data folder with one file of each kind the service serves."""
    root, data = tmp_path / "repo", tmp_path / "data"
    write(root / "conditions/4600.json", '{"sol": 4600}')
    write(root / "results/horizon/fixes/navcam-0002.json", '{"photo_id": "navcam-0002"}')
    write(root / "results/horizon/fixes/navcam-0001.json", '{"photo_id": "navcam-0001"}')
    write(root / "results/horizon/horizon-gale.json", '{"test": "horizon-gale"}')
    write(root / "results/drone/drone-jezero.json", '{"test": "drone-jezero"}')
    write(root / "results/horizon/overlays/navcam-0001.png", b"\x89PNG overlay")
    write(data / "gale/layers/slope/layer.json", '{"name": "slope", "group": 1}')
    write(data / "gale/layers/base/layer.json", '{"name": "base", "group": 1}')
    write(data / "gale/layers/base/tiles/0/0/0.png", b"\x89PNG tile")
    return root, data


def client_for(repo, **settings) -> TestClient:
    root, data = repo
    return TestClient(create_app(Settings(repo_root=root, data_root=data, **settings)))


# Endpoints serve files


def test_conditions_come_from_the_sol_file(repo):
    assert client_for(repo).get("/conditions/4600").json() == {"sol": 4600}


def test_fix_results_are_listed_by_photo_id_and_served_one_by_one(repo):
    client = client_for(repo)

    assert client.get("/fixes/horizon").json() == [
        {"photo_id": "navcam-0001"},
        {"photo_id": "navcam-0002"},
    ]
    assert client.get("/fixes/horizon/navcam-0002").json() == {"photo_id": "navcam-0002"}


def test_test_summaries_are_listed_across_methods_and_served_one_by_one(repo):
    client = client_for(repo)

    assert client.get("/summaries").json() == [
        {"test": "drone-jezero"},
        {"test": "horizon-gale"},
    ]
    assert client.get("/summaries/drone/drone-jezero").json() == {"test": "drone-jezero"}


def test_layers_are_listed_from_the_data_folder_and_their_tiles_served(repo):
    client = client_for(repo)

    assert client.get("/layers/gale").json() == [
        {"name": "base", "group": 1},
        {"name": "slope", "group": 1},
    ]
    assert client.get("/layers/gale/base/tiles/0/0/0.png").content == b"\x89PNG tile"


def test_overlay_images_are_served_by_their_repo_path(repo):
    response = client_for(repo).get("/overlays/results/horizon/overlays/navcam-0001.png")

    assert response.content == b"\x89PNG overlay"


@pytest.mark.parametrize(
    "path",
    [
        "/conditions/4601",
        "/fixes/horizon/navcam-9999",
        "/fixes/hidden",
        "/summaries/horizon/nope",
        "/layers/jezero",
        "/layers/gale/base/tiles/9/9/9.png",
        "/overlays/conditions/4600.json",
        "/overlays/results/horizon/overlays/missing.png",
    ],
)
def test_a_missing_file_is_404(repo, path):
    assert client_for(repo).get(path).status_code == 404


@pytest.mark.parametrize(
    "path",
    ["/layers/gale/base/..%2F..%2F..%2Frepo%2Fconditions%2F4600.json", "/conditions/..%2F4600"],
)
def test_paths_cannot_climb_out_of_their_folder(repo, path):
    assert client_for(repo).get(path).status_code in {400, 404}


# Engine plug-in


def test_without_an_engine_the_route_and_simulation_answer_from_their_stubs(repo):
    client = client_for(repo, route_engine=NO_ENGINE, sim_engine=NO_ENGINE)

    assert client.post("/route", json=ROUTE_REQUEST).json() == ROUTE_STUB
    assert client.post("/simulate", json=SIMULATE_REQUEST).json() == SIMULATE_STUB


@pytest.fixture
def engines(tmp_path, monkeypatch):
    """Person 4's engines, as modules dropped next to the repo: no change to the service."""
    package = tmp_path / "engines" / "redmark_test_engines"
    route_answer = {**ROUTE_STUB, "total_time_s": 1234.5}
    simulate_answer = {**SIMULATE_STUB, "seed": 7}
    write(package / "route_engine.py", f"def plan(request):\n    return {route_answer!r}\n")
    write(package / "sim_engine.py", f"def simulate(request):\n    return {simulate_answer!r}\n")
    write(package / "broken_engine.py", "def plan(request):\n    return {'site': 'gale'}\n")
    monkeypatch.syspath_prepend(str(package.parent))
    yield route_answer, simulate_answer
    for name in [m for m in sys.modules if m.startswith("redmark_test_engines")]:
        del sys.modules[name]


def test_an_engine_module_answers_once_it_exists(repo, engines):
    route_answer, simulate_answer = engines
    client = client_for(
        repo,
        route_engine="redmark_test_engines.route_engine",
        sim_engine="redmark_test_engines.sim_engine",
    )

    assert client.post("/route", json=ROUTE_REQUEST).json() == route_answer
    assert client.post("/simulate", json=SIMULATE_REQUEST).json() == simulate_answer


def test_an_engine_answer_that_breaks_its_contract_is_an_error(repo, engines):
    client = client_for(repo, route_engine="redmark_test_engines.broken_engine")

    response = client.post("/route", json=ROUTE_REQUEST)

    assert response.status_code == 502
    assert "route_response" in response.json()["detail"]


def test_a_request_that_breaks_its_contract_is_rejected(repo):
    client = client_for(repo, route_engine=NO_ENGINE)

    assert client.post("/route", json={"site": "gale"}).status_code == 422


# Service recorder


def test_a_tagged_live_call_in_record_mode_is_saved_to_the_demo_cache(repo):
    root, _ = repo
    client = client_for(repo, record=True, route_engine=NO_ENGINE)

    client.post("/route", json=ROUTE_REQUEST, headers={"X-Demo-Step": "planning.route.fastest"})

    saved = json.loads((root / "cache/demo/route/planning-route-fastest.json").read_text())
    assert saved == {
        "step": "planning.route.fastest",
        "request": {"method": "POST", "path": "/route", "body": ROUTE_REQUEST},
        "status": 200,
        "contract": "route_response",
        "response": ROUTE_STUB,
    }


def test_a_recorded_get_names_its_contract_and_has_no_body(repo):
    root, _ = repo
    client = client_for(repo, record=True)

    client.get("/conditions/4600", headers={"X-Demo-Step": "walk.conditions"})

    saved = json.loads((root / "cache/demo/conditions/walk-conditions.json").read_text())
    assert saved == {
        "step": "walk.conditions",
        "request": {"method": "GET", "path": "/conditions/4600", "body": None},
        "status": 200,
        "contract": "conditions",
        "response": {"sol": 4600},
    }


def test_a_list_has_no_contract_of_its_own(repo):
    root, _ = repo
    client_for(repo, record=True).get("/fixes/horizon", headers={"X-Demo-Step": "lab.photos"})

    saved = json.loads((root / "cache/demo/fixes/lab-photos.json").read_text())
    assert saved["contract"] is None


def test_nothing_is_recorded_without_record_mode_or_without_a_step(repo):
    root, _ = repo
    client_for(repo).get("/conditions/4600", headers={"X-Demo-Step": "walk.conditions"})
    client_for(repo, record=True).get("/conditions/4600")

    assert not (root / "cache").exists()


def test_a_step_id_that_is_not_a_plain_name_is_rejected(repo):
    response = client_for(repo, record=True).get(
        "/conditions/4600", headers={"X-Demo-Step": "../../etc"}
    )

    assert response.status_code == 400
