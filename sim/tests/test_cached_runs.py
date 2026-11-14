"""The cached break-it runs for the demo: one demo cache entry per scenario."""

import json

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from contracts.paths import REPO_ROOT
from sim.cache_runs import write_cached_runs
from sim.engine import simulate


def validator(name: str) -> Draft202012Validator:
    schemas = REPO_ROOT / "contracts" / "schemas"
    registry = Registry().with_resources(
        (
            p.name,
            Resource.from_contents(json.loads(p.read_text()), default_specification=DRAFT202012),
        )
        for p in schemas.glob("*.json")
    )
    return Draft202012Validator(
        json.loads((schemas / f"{name}.json").read_text()), registry=registry
    )


def kinds(entry: dict) -> set[str]:
    return {e["kind"] for s in entry["response"]["steps"] for e in s["events"]}


def test_every_break_it_scenario_has_a_cached_run_that_replays_the_simulation(tmp_path):
    paths = write_cached_runs(tmp_path)

    entries = {json.loads(p.read_text())["step"]: json.loads(p.read_text()) for p in paths}
    assert sorted(entries) == [
        "walk.simulate.camera-off",
        "walk.simulate.drone-grounded",
        "walk.simulate.everything",
        "walk.simulate.normal",
        "walk.simulate.radio-off",
    ]
    for entry in entries.values():
        validator("demo_cache").validate(entry)
        validator("simulate_response").validate(entry["response"])
        assert entry["request"]["path"] == "/simulate" and entry["status"] == 200
        assert entry["response"] == simulate(entry["request"]["body"])

    assert "radio_ranging_simulated" in kinds(entries["walk.simulate.normal"])
    assert "buddy_camera" in kinds(entries["walk.simulate.camera-off"])
    assert "offline" in {s["mode"] for s in entries["walk.simulate.radio-off"]["response"]["steps"]}
    assert "fix_unavailable" in kinds(entries["walk.simulate.drone-grounded"])
    assert "lost_mode" in kinds(entries["walk.simulate.everything"])
