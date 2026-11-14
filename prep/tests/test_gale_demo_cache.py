"""Seam: the Plan screen's demo cache steps, recorded through the service,
refusals included."""

from pathlib import Path

from contracts.models.demo_cache import DemoCacheEntry
from contracts.paths import REPO_ROOT
from prep.gale.demo_cache import record_plan_screen
from service.app import Settings

STUB_DATA = REPO_ROOT / "contracts" / "stubs" / "stub-data"
SITE = """\
site: gale
name: Test site
projection: +proj=eqc +lat_ts=0 +lon_0=0 +R=3396190 +units=m +no_defs
bounds: {min_x: 0, min_y: 0, max_x: 4000, max_y: 4000}
habitat: {x: 2000, y: 2000}
base_camp: {x: 1900, y: 1950}
science_targets:
- id: ridge
  name: Ridge
  position: {x: 2500, y: 2600}
- id: hollow
  name: Hollow
  position: {x: 1500, y: 2700}
files: {}
replayed_sol: null
"""


def _record(tmp_path: Path) -> dict[str, DemoCacheEntry]:
    (tmp_path / "sites").mkdir()
    (tmp_path / "sites" / "gale.yaml").write_text(SITE)
    settings = Settings(
        repo_root=tmp_path,
        data_root=STUB_DATA,
        route_engine="prep.tests.refusing_route_engine",
    )
    written = record_plan_screen(settings)
    entries = [DemoCacheEntry.model_validate_json(path.read_text()) for path in written]
    for path, entry in zip(written, entries, strict=True):
        producer = entry.request.path.strip("/").split("/")[0]
        name = f"{entry.step.replace('.', '-')}.json"
        assert path == tmp_path / "cache" / "demo" / producer / name
    return {entry.step: entry for entry in entries}


def test_every_plan_screen_step_is_cached_with_the_apps_request(tmp_path):
    entries = _record(tmp_path)

    assert sorted(entries) == sorted(
        [
            "plan.site",
            "plan.layers",
            "plan.route.cart.20",
            "plan.route.cart.15",
            *(
                f"plan.route.{mode}.{target}.{slope}"
                for mode in ("fastest", "science")
                for target in ("ridge", "hollow")
                for slope in (20, 15)
            ),
        ]
    )
    # What app/src/plan/routes.ts sends for the fastest walk to the ridge at 20°.
    assert entries["plan.route.fastest.ridge.20"].request.body == {
        "site": "gale",
        "start": {"x": 1900, "y": 1950},
        "goal": {"x": 2500, "y": 2600},
        "mode": "fastest",
        "uncertainty_m": 0,
        "limits": {
            "max_slope_deg": 20,
            "max_distance_from_habitat_m": 2000,
            "planning_speed_kmh": 2,
            "max_walk_h": 6,
        },
    }
    assert entries["plan.route.cart.15"].request.body["start"] == {"x": 2000, "y": 2000}
    assert entries["plan.route.cart.15"].request.body["goal"] == {"x": 1900, "y": 1950}
    assert entries["plan.site"].response["base_camp"] == {"x": 1900, "y": 1950}
    planned = entries["plan.route.science.hollow.20"]
    assert (planned.status, planned.contract) == (200, "route_response")


def test_a_refused_route_is_cached_as_the_refusal_not_left_out(tmp_path):
    entries = _record(tmp_path)

    refused = entries["plan.route.fastest.ridge.15"]
    assert refused.status == 422
    assert refused.contract is None
    assert refused.response == {"detail": "no safe route: every path breaks a hard limit"}
    assert refused.request.body["limits"]["max_slope_deg"] == 15
