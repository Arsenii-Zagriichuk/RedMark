"""The route engine through Person 1's service: POST /route calls route.engine.plan."""

import json
import time

from fastapi.testclient import TestClient

from contracts.paths import REPO_ROOT
from service.app import Settings, create_app

STUB_REQUEST = json.loads((REPO_ROOT / "contracts/stubs/route/request.json").read_text())
STUB_RESPONSE = json.loads((REPO_ROOT / "contracts/stubs/route/response.json").read_text())


def post_route(body: dict):
    return TestClient(create_app(Settings())).post("/route", json=body)


def test_the_service_answers_the_stub_request_with_a_planned_route_within_a_few_seconds():
    began = time.perf_counter()
    reply = post_route(STUB_REQUEST)
    elapsed = time.perf_counter() - began

    assert reply.status_code == 200, reply.text
    route = reply.json()
    assert route != STUB_RESPONSE
    assert route["mode"] == "fastest" and route["site"] == "gale"
    assert all(check["passed"] for check in route["limit_checks"])
    assert elapsed < 5


def test_a_goal_beyond_the_distance_limit_is_refused_with_the_reason():
    body = STUB_REQUEST | {"goal": {"x": 8145600, "y": -280200}}

    reply = post_route(body)

    assert reply.status_code == 422
    assert "no safe route" in reply.json()["detail"]


def test_the_science_and_cart_routes_say_they_are_not_built_yet():
    for mode in ("science", "cart"):
        reply = post_route(STUB_REQUEST | {"mode": mode})

        assert reply.status_code == 501
        assert "P4-04" in reply.json()["detail"]


def test_start_and_goal_in_the_same_spot_is_refused_with_the_reason():
    reply = post_route(STUB_REQUEST | {"goal": STUB_REQUEST["start"]})

    assert reply.status_code == 422
    assert "same planning cell" in reply.json()["detail"]


def test_a_site_without_a_habitat_is_refused_with_the_reason():
    reply = post_route(STUB_REQUEST | {"site": "jezero"})

    assert reply.status_code == 422
    assert "no habitat" in reply.json()["detail"]
