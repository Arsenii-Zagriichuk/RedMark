"""A stand-in route engine for the demo cache test: refuses every walk below
20°, as Person 4's engine refuses the Gale targets at 15°, and answers the
rest with the route stub."""

import json

from fastapi import HTTPException

from contracts.paths import REPO_ROOT


def plan(request: dict) -> dict:
    if request["limits"]["max_slope_deg"] < 20:
        raise HTTPException(422, "no safe route: every path breaks a hard limit")
    return json.loads((REPO_ROOT / "contracts" / "stubs" / "route" / "response.json").read_text())
