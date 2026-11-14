"""Re-records the Plan screen's steps of the demo cache from today's Gale site
config, layers and route engine, so the cached map, routes and the simulated
Gale drone fix (locate/drone/gale_fix.py) all sit on the same ground.

    REDMARK_DATA=~/redmark-data uv run python -m prep.gale.demo_cache

Goes through the service the app talks to, with its recorder on, and sends
what the Plan screen sends (app/src/plan/PlanScreen.tsx and routes.ts):
plan.site, plan.layers, and at both slope limits the fastest and science
walks from base camp to every science target and the cart route from the
habitat to base camp. The recorder saves answers that succeed. A route the
engine refuses (422, "no safe route") is saved here in the recorder's format
with its status, so demo mode shows the refusal, as live mode does, instead
of a cache miss.
"""

import json
import os
import sys
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

from service.app import Settings, create_app

SITE = "gale"
# The Plan screen's limits (app/src/plan/routes.ts): the two slope options and
# the other hard limits from Artemis planning.
SLOPE_LIMITS = (20, 15)
OTHER_LIMITS = {"max_distance_from_habitat_m": 2000, "planning_speed_kmh": 2, "max_walk_h": 6}
REFUSED = 422


def _entry_path(repo_root: Path, path: str, step: str) -> Path:
    """Where the service's recorder saves `step`: cache/demo/<first path segment>/."""
    producer = path.strip("/").split("/")[0]
    return repo_root / "cache" / "demo" / producer / f"{step.replace('.', '-')}.json"


def route_requests(site: dict) -> list[tuple[str, dict]]:
    """Each Plan screen route step and the body the app sends for it."""
    walk_from = site.get("base_camp") or site.get("habitat")
    steps = []
    for slope in SLOPE_LIMITS:
        limits = {"max_slope_deg": slope, **OTHER_LIMITS}

        def body(mode: str, start: dict, goal: dict, limits: dict = limits) -> dict:
            return {
                "site": site["site"],
                "start": start,
                "goal": goal,
                "mode": mode,
                "uncertainty_m": 0,
                "limits": limits,
            }

        if walk_from:
            for target in site["science_targets"]:
                for mode in ("fastest", "science"):
                    step = f"plan.route.{mode}.{target['id']}.{slope}"
                    steps.append((step, body(mode, walk_from, target["position"])))
        if site.get("habitat") and site.get("base_camp"):
            steps.append(
                (f"plan.route.cart.{slope}", body("cart", site["habitat"], site["base_camp"]))
            )
    return steps


def record_plan_screen(settings: Settings) -> list[Path]:
    """Records every Plan screen step; returns the cache files written."""
    client = TestClient(create_app(replace(settings, record=True)))
    written = []
    answers = {}
    for step, path in (("plan.site", f"/sites/{SITE}"), ("plan.layers", f"/layers/{SITE}")):
        answer = client.get(path, headers={"X-Demo-Step": step})
        if answer.status_code != 200:
            raise SystemExit(f"{step}: the service answered {answer.status_code}: {answer.text}")
        answers[step] = answer.json()
        written.append(_entry_path(settings.repo_root, path, step))
    for step, body in route_requests(answers["plan.site"]):
        answer = client.post("/route", json=body, headers={"X-Demo-Step": step})
        target = _entry_path(settings.repo_root, "/route", step)
        if answer.status_code == REFUSED:
            entry = {
                "step": step,
                "request": {"method": "POST", "path": "/route", "body": body},
                "status": REFUSED,
                "contract": None,
                "response": answer.json(),
            }
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(entry, indent=2) + "\n")
        elif answer.status_code != 200:
            raise SystemExit(f"{step}: the service answered {answer.status_code}: {answer.text}")
        written.append(target)
    return written


if __name__ == "__main__":
    if not os.environ.get("REDMARK_DATA"):
        sys.exit("set REDMARK_DATA to the shared data folder with the Gale layers")
    settings = Settings()
    for path in record_plan_screen(settings):
        entry = json.loads(path.read_text())
        print(f"{entry['status']} {path.relative_to(settings.repo_root)}")
