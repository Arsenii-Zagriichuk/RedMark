"""Write the demo cache's break-it runs (P4-06): one simulated walk per scenario.

Run with `uv run python -m sim.cache_runs`. Each run is the stub route's walk, seed 1, with
a horizon, a drone and a ground fix scheduled, and goes to
cache/demo/simulate/walk-simulate-<scenario>.json under step id walk.simulate.<scenario>,
the shape the service's recorder writes, so the app's demo mode plays it with the network
off. Every run is simulated and says so.
"""

from __future__ import annotations

import json
from pathlib import Path

from contracts.paths import REPO_ROOT
from sim.engine import simulate

OUT = REPO_ROOT / "cache" / "demo" / "simulate"
STUB_REQUEST = REPO_ROOT / "contracts" / "stubs" / "simulate" / "request.json"
FIX_SCHEDULE = [
    {"time_s": 900, "method": "horizon"},
    {"time_s": 1800, "method": "drone"},
    {"time_s": 2400, "method": "ground"},
]
SCENARIOS = {
    "normal": {},
    "camera-off": {"camera_off": True},
    "radio-off": {"radio_off": True},
    "drone-grounded": {"drone_grounded": True},
    "everything": {"camera_off": True, "radio_off": True, "drone_grounded": True},
}


def write_cached_runs(out: Path = OUT) -> list[Path]:
    stub = json.loads(STUB_REQUEST.read_text())
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for scenario, broken in SCENARIOS.items():
        body = {
            "site": stub["site"],
            "path": stub["path"],
            "fix_schedule": FIX_SCHEDULE,
            "break_it": {"camera_off": False, "radio_off": False, "drone_grounded": False} | broken,
            "seed": 1,
        }
        step = f"walk.simulate.{scenario}"
        entry = {
            "step": step,
            "request": {"method": "POST", "path": "/simulate", "body": body},
            "status": 200,
            "contract": "simulate_response",
            "response": simulate(body),
        }
        path = out / f"{step.replace('.', '-')}.json"
        path.write_text(json.dumps(entry, indent=2) + "\n")
        written.append(path)
    return written


if __name__ == "__main__":
    for path in write_cached_runs():
        print(path.relative_to(REPO_ROOT))
