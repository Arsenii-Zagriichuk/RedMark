"""Which saved route layer 5's landmark directions follow (P3-06)."""

import pytest

from contracts.models.site import SiteConfig
from contracts.paths import REPO_ROOT
from layers.location_quality.build import demo_route


def gale(targets: list[str]) -> SiteConfig:
    return SiteConfig.model_validate(
        {
            "site": "gale",
            "name": "Gale crater boxwork",
            "projection": "+proj=eqc +lat_ts=0 +lon_0=0 +R=3396190 +units=m +no_defs",
            "bounds": {"min_x": 0, "min_y": 0, "max_x": 4000, "max_y": 4000},
            "habitat": {"x": 2000, "y": 2000},
            "base_camp": {"x": 1900, "y": 1900},
            "science_targets": [
                {"id": t, "position": {"x": 1500, "y": 1500}, "name": t} for t in targets
            ],
            "checkpoints": [],
            "files": {},
            "replayed_sol": 4600,
        }
    )


def test_directions_follow_the_demo_walk_the_fastest_route_to_the_first_science_target():
    # The app records it as demo step plan.route.fastest.sw-ridge.20 (its default 20° slope
    # limit), and the service saves a step with its dots as hyphens.
    assert demo_route(gale(["sw-ridge", "sw-hollow"])) == (
        REPO_ROOT / "cache" / "demo" / "route" / "plan-route-fastest-sw-ridge-20.json"
    )


def test_a_site_with_no_science_target_has_no_demo_walk():
    with pytest.raises(ValueError, match="no science target"):
        demo_route(gale([]))
