"""The route engine's entry point for Person 1's service: POST /route calls plan()."""

from __future__ import annotations

import yaml

from contracts.models.route_request import RouteRequest
from contracts.models.site import SiteConfig
from contracts.paths import REPO_ROOT, data_root
from route.layers import load_grid
from route.planner import NoSafeRoute, plan_on_grid


def load_site(site_id: str) -> SiteConfig:
    return SiteConfig.model_validate(
        yaml.safe_load((REPO_ROOT / "sites" / f"{site_id}.yaml").read_text())
    )


def plan(request: dict) -> dict:
    """The fastest safe route as a RouteResponse dict.

    Raises NoSafeRoute, which the service returns as a 422 with the reason, when every
    path breaks a hard limit.
    """
    route_request = RouteRequest.model_validate(request)
    if route_request.mode != "fastest":
        raise NotImplementedError(f"the {route_request.mode} route comes with P4-04")
    site = load_site(route_request.site)
    if site.habitat is None:
        raise NoSafeRoute(f"the {route_request.site} site has no habitat to walk from")
    response = plan_on_grid(
        load_grid(site, data_root()),
        route_request.start,
        route_request.goal,
        site.habitat,
        route_request.limits,
    )
    return response.model_dump(mode="json")
