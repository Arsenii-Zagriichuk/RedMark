"""The route engine through Person 1's service: POST /route calls route.engine.plan."""

import json
import time

import pytest
from fastapi.testclient import TestClient

from contracts.paths import REPO_ROOT
from route.engine import daylight_s
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


CREW_CHECKS = [
    "slope",
    "distance_from_habitat",
    "planning_speed",
    "walk_time",
    "hazard_margin",
    "walk_back",
    "daylight",
]


def test_all_three_route_modes_come_back_with_their_limit_checks():
    routes = {}
    for mode in ("fastest", "science", "cart"):
        reply = post_route(STUB_REQUEST | {"mode": mode})
        assert reply.status_code == 200, reply.text
        routes[mode] = reply.json()

    assert [c["limit"] for c in routes["fastest"]["limit_checks"]] == CREW_CHECKS
    assert [c["limit"] for c in routes["science"]["limit_checks"]] == CREW_CHECKS
    assert [c["limit"] for c in routes["cart"]["limit_checks"]] == CREW_CHECKS[:5]
    assert {r["mode"] for r in routes.values()} == {"fastest", "science", "cart"}
    assert routes["fastest"]["extra_time_vs_fastest_s"] is None
    assert routes["science"]["extra_time_vs_fastest_s"] >= 0


def test_start_and_goal_in_the_same_spot_is_refused_with_the_reason():
    reply = post_route(STUB_REQUEST | {"goal": STUB_REQUEST["start"]})

    assert reply.status_code == 422
    assert "same planning cell" in reply.json()["detail"]


def test_a_site_without_a_habitat_is_refused_with_the_reason():
    reply = post_route(STUB_REQUEST | {"site": "jezero"})

    assert reply.status_code == 422
    assert "no habitat" in reply.json()["detail"]


def test_daylight_runs_from_first_light_to_sunset_on_the_replayed_sol():
    conditions = json.loads((REPO_ROOT / "conditions/4600.json").read_text())
    assert conditions["steps"][0]["lmst"] == "06:00" and conditions["sunset_lmst"] == "17:30"

    # 11.5 Mars hours of 88775.244 s / 24 = 3698.97 s each.
    assert daylight_s(conditions) == pytest.approx(42538.1, abs=0.1)
    conditions["steps"][0]["sun_elevation_deg"] = -1.0
    assert daylight_s(conditions) == pytest.approx(38839.2, abs=0.1)


def test_a_sol_whose_sun_never_rises_has_no_daylight():
    conditions = json.loads((REPO_ROOT / "conditions/4600.json").read_text())
    for step in conditions["steps"]:
        step["sun_elevation_deg"] = -5.0

    assert daylight_s(conditions) == 0
