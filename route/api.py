"""The route engine's entry point for Person 1's service: POST /route calls plan()."""

from __future__ import annotations

import yaml

from contracts.models.route_request import RouteRequest
from contracts.models.route_response import RouteResponse
from contracts.models.site import SiteConfig
from contracts.paths import REPO_ROOT, data_root
from route.engine import NoSafeRoute, plan_on_grid
from route.layers import load_grid


def load_site(site_id: str) -> SiteConfig:
    return SiteConfig.model_validate(
        yaml.safe_load((REPO_ROOT / "sites" / f"{site_id}.yaml").read_text())
    )


def plan(request: RouteRequest) -> RouteResponse:
    """The fastest safe route; raises NoSafeRoute when every path breaks a hard limit."""
    if request.mode != "fastest":
        raise NotImplementedError(f"the {request.mode} route comes with P4-04")
    site = load_site(request.site)
    if site.habitat is None:
        raise NoSafeRoute(f"the {request.site} site has no habitat to walk from")
    grid = load_grid(site, data_root())
    return plan_on_grid(grid, request.start, request.goal, site.habitat, request.limits)
