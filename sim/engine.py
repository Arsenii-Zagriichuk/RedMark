"""The walk simulation behind POST /simulate: one step per time tick along a route.

The service calls simulate(request) with a SimulateRequest as a dict and gets a
SimulateResponse back as a dict. Every run is simulated and says so.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from contracts.models.simulate_request import SimulateRequest
from contracts.models.simulate_response import SimulateResponse
from contracts.models.test_summary import TestSummary
from contracts.paths import REPO_ROOT

# Each fix method's error size comes from its test summary: horizon from Person 3's test,
# ground from Person 3's stage 2 result, drone from Person 2's Jezero test.
TEST_SUMMARIES = {
    "horizon": "horizon/horizon-gale.json",
    "ground": "ground/ground-gale.json",
    "drone": "drone/drone-jezero.json",
}

# The Artemis planning walk speed, the same default as the route's hard limits.
PLANNING_SPEED_KMH = 2.0
TICK_S = 10.0
# The walk starts at a surveyed spot by the habitat, so its position is known closely.
START_CIRCLE_M = 0.5
# The uncertainty circle is the 95% radius, so the filter is 95% sure at every step.
CIRCLE_COVERAGE = 0.95
# Between fixes visual odometry, step counting and the sun carry the position. MER visual
# odometry stayed under 2.5% of distance driven (Maimone, Cheng & Matthies 2007).
DRIFT_PER_M = 0.025
# The app asks for a fix when the circle passes this on open ground. The 5 m boxwork and
# 3 m near-hazard limits need the ridge and slope layers, which the sim doesn't read yet.
FIX_REQUEST_OPEN_GROUND_M = 10.0

# Radius of the 95% circle for a 2D normal error with standard deviation 1 per axis.
_CIRCLE_PER_SIGMA = math.sqrt(-2 * math.log(1 - CIRCLE_COVERAGE))


def simulate(request: dict, results_root: Path = REPO_ROOT / "results") -> dict:
    walk = SimulateRequest.model_validate(request)
    broken = [name for name, on in walk.break_it.model_dump().items() if on]
    if broken:
        raise NotImplementedError(f"break-it scenarios ({', '.join(broken)}) come with P4-06")
    corners = np.array([[p.x, p.y] for p in walk.path], dtype=float)
    along = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(corners, axis=0), axis=1))])
    speed_m_s = PLANNING_SPEED_KMH / 3.6
    end_s = along[-1] / speed_m_s
    late = [f.time_s for f in walk.fix_schedule if f.time_s > end_s]
    if late:
        raise ValueError(f"a fix at {late[0]:.0f} s is after the walk ends at {end_s:.0f} s")
    fix_sigma = {
        m: _fix_sigma_m(results_root / TEST_SUMMARIES[m])
        for m in {f.method.value for f in walk.fix_schedule}
    }
    ticks = sorted({*np.arange(0.0, end_s, TICK_S), end_s, *(f.time_s for f in walk.fix_schedule)})
    rng = np.random.default_rng(walk.seed)
    true = corners[0].copy()
    estimate = true.copy()
    variance = (START_CIRCLE_M / _CIRCLE_PER_SIGMA) ** 2  # per axis, square metres
    steps = []
    circle_m = START_CIRCLE_M
    for t in ticks:
        d = min(t * speed_m_s, along[-1])
        moved_to = np.array(
            [np.interp(d, along, corners[:, 0]), np.interp(d, along, corners[:, 1])]
        )
        step_m = float(np.linalg.norm(moved_to - true))
        drift_sigma = DRIFT_PER_M * step_m
        estimate = estimate + (moved_to - true) + rng.normal(0.0, drift_sigma, 2)
        variance += drift_sigma**2
        true = moved_to
        sources = ["visual_odometry", "motion_sensor", "step_count", "sun"]
        events = []
        for fix in (f for f in walk.fix_schedule if f.time_s == t):
            method, sigma = fix.method.value, fix_sigma[fix.method.value]
            gain = variance / (variance + sigma**2)
            estimate = estimate + gain * (true + rng.normal(0.0, sigma, 2) - estimate)
            variance *= 1 - gain
            sources.append(method)
            events.append({"kind": "fix", "method": method})
        was_m, circle_m = circle_m, _CIRCLE_PER_SIGMA * math.sqrt(variance)
        if was_m <= FIX_REQUEST_OPEN_GROUND_M < circle_m:
            events.append({"kind": "fix_requested"})
        steps.append(
            {
                "t_s": float(t),
                "true_position": _point(true),
                "estimated_position": _point(estimate),
                "uncertainty_m": circle_m,
                "confidence_pct": CIRCLE_COVERAGE * 100,
                "sources": list(dict.fromkeys(sources)),
                "events": events,
                "mode": "normal",
            }
        )
    response = {"site": walk.site, "simulated": True, "seed": walk.seed, "steps": steps}
    return SimulateResponse.model_validate(response).model_dump(mode="json", exclude_none=True)


def _fix_sigma_m(summary: Path) -> float:
    """Per-axis error of one fix: a 2D normal error's median radius is sigma * sqrt(2 ln 2)."""
    median_m = TestSummary.model_validate(json.loads(summary.read_text())).overall.median_error_m
    return median_m / math.sqrt(2 * math.log(2))


def _point(p: np.ndarray) -> dict:
    return {"x": float(p[0]), "y": float(p[1])}
