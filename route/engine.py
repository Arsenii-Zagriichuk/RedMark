"""The route engine's entry point for Person 1's service: POST /route calls plan()."""

from __future__ import annotations

import json

import yaml

from contracts.models.common import Point
from contracts.models.conditions import Conditions
from contracts.models.route_request import Mode, RouteRequest
from contracts.models.site import SiteConfig
from contracts.paths import REPO_ROOT, data_root
from route.layers import load_grid
from route.planner import CheckpointCandidate, NoSafeRoute, plan_on_grid

# One Mars solar day in SI seconds (Allison & McEwen 2000); an LMST hour is 1/24 of it.
SOL_S = 88775.244


def daylight_s(conditions: dict) -> float:
    """Seconds from first light (the first step with the sun above the horizon) to sunset;
    0 when the sun never rises."""
    replayed = Conditions.model_validate(conditions)
    first_light = next((s.lmst for s in replayed.steps if s.sun_elevation_deg > 0), None)
    if first_light is None:
        return 0.0
    return max(_lmst_h(replayed.sunset_lmst) - _lmst_h(first_light), 0.0) * SOL_S / 24


def _lmst_h(lmst: str) -> float:
    hours, minutes = lmst.split(":")
    return int(hours) + int(minutes) / 60


def checkpoint_candidates(site_id: str) -> list[CheckpointCandidate]:
    """Person 3's checkpoint candidates for a site, from layer 5; none if it has no layer 5."""
    path = REPO_ROOT / "layers" / "location_quality" / f"layer5-{site_id}.json"
    if not path.is_file():
        return []
    return [
        CheckpointCandidate(c["id"], Point.model_validate(c["position"]), c["score"])
        for c in json.loads(path.read_text())["checkpoint_candidates"]
    ]


def load_site(site_id: str) -> SiteConfig:
    return SiteConfig.model_validate(
        yaml.safe_load((REPO_ROOT / "sites" / f"{site_id}.yaml").read_text())
    )


def plan(request: dict) -> dict:
    """The fastest, science or cart route as a RouteResponse dict.

    Raises NoSafeRoute, which the service returns as a 422 with the reason, when every
    path breaks a hard limit. Daylight comes from the replayed sol's conditions file and
    the science targets from the site config.
    """
    route_request = RouteRequest.model_validate(request)
    site = load_site(route_request.site)
    if site.habitat is None:
        raise NoSafeRoute(f"the {route_request.site} site has no habitat to walk from")
    daylight = None
    if site.replayed_sol is not None:
        conditions = REPO_ROOT / "conditions" / f"{site.replayed_sol}.json"
        daylight = daylight_s(json.loads(conditions.read_text()))
    mode = route_request.mode
    response = plan_on_grid(
        load_grid(site, data_root()),
        route_request.start,
        route_request.goal,
        site.habitat,
        route_request.limits,
        mode=mode,
        daylight_s=daylight,
        uncertainty_m=route_request.uncertainty_m,
        targets=[t.position for t in site.science_targets] if mode == Mode.science else (),
        checkpoint_candidates=checkpoint_candidates(route_request.site),
    )
    return response.model_dump(mode="json")
