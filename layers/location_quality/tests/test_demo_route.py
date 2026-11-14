"""Which saved route layer 5's landmark directions follow (P3-06): the demo walk, found by its
demo step in the demo cache, and only if it was recorded on the current site config."""

import json
import re

import pytest

from contracts.models.site import SiteConfig
from contracts.paths import REPO_ROOT
from layers.location_quality.build import DEMO_SLOPE_DEG, demo_route

BASE_CAMP = {"x": 1900.0, "y": 1900.0}
RIDGE = {"x": 1500.0, "y": 1500.0}
HOLLOW = {"x": 1500.0, "y": 1450.0}
# Where base camp stood in the stub site config the first demo cache was recorded on.
OLD_BASE_CAMP = {"x": 3300.0, "y": 4600.0}


def gale(targets: list[tuple[str, dict]]) -> SiteConfig:
    return SiteConfig.model_validate(
        {
            "site": "gale",
            "name": "Gale crater boxwork",
            "projection": "+proj=eqc +lat_ts=0 +lon_0=0 +R=3396190 +units=m +no_defs",
            "bounds": {"min_x": 0, "min_y": 0, "max_x": 4000, "max_y": 4000},
            "habitat": {"x": 2000, "y": 2000},
            "base_camp": BASE_CAMP,
            "science_targets": [
                {"id": target, "position": at, "name": target} for target, at in targets
            ],
            "checkpoints": [],
            "files": {},
            "replayed_sol": 4600,
        }
    )


GALE = gale([("sw-ridge", RIDGE), ("sw-hollow", HOLLOW)])


def record(cache, file_name: str, step: str, start: dict, goal: dict, mode: str = "fastest"):
    """A saved POST /route demo cache entry, as the service writes one."""
    body = {"site": "gale", "start": start, "goal": goal, "mode": mode, "uncertainty_m": 0}
    entry = {
        "step": step,
        "request": {"method": "POST", "path": "/route", "body": body},
        "status": 200,
        "contract": "route_response",
        "response": {},
    }
    (cache / file_name).write_text(json.dumps(entry))


def test_directions_follow_the_fastest_walk_from_base_camp_to_the_first_science_target(
    tmp_path,
):
    record(
        tmp_path,
        "plan-route-fastest-sw-ridge-15.json",
        "plan.route.fastest.sw-ridge.15",
        BASE_CAMP,
        RIDGE,
    )
    record(
        tmp_path,
        "plan-route-science-sw-ridge-20.json",
        "plan.route.science.sw-ridge.20",
        BASE_CAMP,
        RIDGE,
        mode="science",
    )
    record(
        tmp_path,
        "plan-route-fastest-sw-hollow-20.json",
        "plan.route.fastest.sw-hollow.20",
        BASE_CAMP,
        HOLLOW,
    )
    record(
        tmp_path,
        "plan-route-fastest-sw-ridge-20.json",
        "plan.route.fastest.sw-ridge.20",
        BASE_CAMP,
        RIDGE,
    )
    assert demo_route(GALE, tmp_path) == tmp_path / "plan-route-fastest-sw-ridge-20.json"


def test_a_demo_walk_to_another_science_target_is_followed_too(tmp_path):
    record(
        tmp_path,
        "plan-route-fastest-sw-hollow-20.json",
        "plan.route.fastest.sw-hollow.20",
        BASE_CAMP,
        HOLLOW,
    )
    assert demo_route(GALE, tmp_path) == tmp_path / "plan-route-fastest-sw-hollow-20.json"


def test_a_walk_recorded_on_an_older_site_config_is_not_followed(tmp_path):
    # Recorded before base camp moved: its legs would lie outside the walk area.
    record(
        tmp_path,
        "plan-route-fastest-sw-ridge-20.json",
        "plan.route.fastest.sw-ridge.20",
        OLD_BASE_CAMP,
        RIDGE,
    )
    with pytest.raises(ValueError, match=r"plan\.route\.fastest\.sw-ridge\.20 .*re-record"):
        demo_route(GALE, tmp_path)


def test_a_site_with_no_science_target_has_no_demo_walk(tmp_path):
    with pytest.raises(ValueError, match="no science target"):
        demo_route(gale([]), tmp_path)


def test_the_demo_walks_slope_limit_is_the_one_the_plan_screen_starts_with():
    # Read from the app's source, so a change of default there fails here.
    screen = (REPO_ROOT / "app" / "src" / "plan" / "PlanScreen.tsx").read_text()
    default = re.search(r"useState<SlopeLimit>\(([0-9]+)\)", screen).group(1)
    assert int(default) == DEMO_SLOPE_DEG
