"""The walk simulation behind POST /simulate: time ticks along a route.

The service calls simulate(request) with a SimulateRequest as a dict and gets a
SimulateResponse back as a dict. Fix ticks contain a prediction then a correction
at the same time, in that order. Every run is simulated and says so.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from pathlib import Path

import numpy as np

from contracts.models.common import Point
from contracts.models.simulate_request import SimulateRequest
from contracts.models.simulate_response import SimulateResponse
from contracts.models.test_summary import TestSummary
from contracts.paths import REPO_ROOT, data_root
from route.engine import load_site
from route.layers import load_grid
from route.planner import NoSafeRoute, hazard_distance_m

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
# With the helmet camera off, the motion sensor, step counting and the sun carry the
# position alone: pedestrian dead reckoning stays under 5% of the distance walked (Jimenez
# et al. 2009, a foot-mounted MEMS IMU).
CAMERA_OFF_DRIFT_PER_M = 0.05
# Fixes that need a camera; with the helmet camera off the buddy's takes them, shared over
# the short-range radio.
PHOTO_METHODS = {"horizon", "ground"}
# The app asks for a fix when the circle passes this on open ground. The 5 m boxwork and
# 3 m near-hazard limits need the ridge and slope layers, which the sim doesn't read yet.
FIX_REQUEST_OPEN_GROUND_M = 10.0
# Near a hazard (one inside the uncertainty circle, the route's hazard margin) the app tells
# the crew to stop and take a fix once the circle passes 3 m (project document).
NEAR_HAZARD_FIX_M = 3.0
# A hazard is ground steeper than the Artemis 20 degree slope limit, the route's default.
HAZARD_SLOPE_DEG = 20.0

# Radio ranging (SIMULATED): signal timing to the habitat, whose position is known, and to the
# buddy. Taken together as one position update every minute with an assumed 5 m error per
# axis, a RedMark assumption, not a measured figure.
RADIO_EVERY_S = 60.0
RADIO_SIGMA_M = 5.0

# No fix is better than a centimetre, so a test summary reporting no error still leaves a circle.
MIN_FIX_SIGMA_M = 0.01

# Radius of the 95% circle for a 2D normal error with standard deviation 1 per axis.
_CIRCLE_PER_SIGMA = math.sqrt(-2 * math.log(1 - CIRCLE_COVERAGE))


def simulate(
    request: dict,
    results_root: Path = REPO_ROOT / "results",
    hazard_distance_m: Callable[[float, float], float] | None = None,
) -> dict:
    """hazard_distance_m(x, y) gives the ground metres to the nearest hazard; by default it
    comes from the site's slope layer."""
    walk = SimulateRequest.model_validate(request)
    to_hazard_m = hazard_distance_m or _site_hazard_distance(walk.site)
    broken = walk.break_it
    drift_per_m = CAMERA_OFF_DRIFT_PER_M if broken.camera_off else DRIFT_PER_M
    tracking = ["motion_sensor", "step_count", "sun"]
    if not broken.camera_off:
        tracking.insert(0, "visual_odometry")
    lost_at_start = [{"kind": name} for name, on in broken.model_dump().items() if on]
    mode = "offline" if broken.radio_off else "normal"
    no_fix_can_reach = not any(_reachable(m, broken) for m in (*PHOTO_METHODS, "drone"))
    corners = np.array([[p.x, p.y] for p in walk.path], dtype=float)
    along_m = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(corners, axis=0), axis=1))])
    speed_m_s = PLANNING_SPEED_KMH / 3.6
    end_s = along_m[-1] / speed_m_s
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
    near = False
    previous_walked_m = 0.0
    for t in ticks:
        walked_m = min(t * speed_m_s, along_m[-1])
        moved_to = np.array([np.interp(walked_m, along_m, corners[:, i]) for i in (0, 1)])
        # Turns can cancel displacement, but not the distance walked.
        step_m = walked_m - previous_walked_m
        previous_walked_m = walked_m
        drift_sigma = drift_per_m * step_m
        estimate = estimate + (moved_to - true) + rng.normal(0.0, drift_sigma, 2)
        variance += drift_sigma**2
        true = moved_to
        sources = list(tracking)
        events = list(lost_at_start) if t == 0 else []
        if not broken.radio_off and t > 0 and t % RADIO_EVERY_S == 0:
            estimate, variance = _update(estimate, variance, true, RADIO_SIGMA_M, rng)
            sources.append("radio")
            if t == RADIO_EVERY_S:
                # Radio ranging is a simulated source: say so where it first shows.
                events.append({"kind": "radio_ranging_simulated"})
        fixes = [f.method.value for f in walk.fix_schedule if f.time_s == t]
        taken = [m for m in fixes if _reachable(m, broken)]
        if taken:
            predicted_circle_m = _CIRCLE_PER_SIGMA * math.sqrt(variance)
            steps.append(_step(t, true, estimate, predicted_circle_m, sources, [], mode))
        for method in fixes:
            if method not in taken:
                events.append({"kind": "fix_unavailable", "method": method})
                continue
            estimate, variance = _update(estimate, variance, true, fix_sigma[method], rng)
            sources.append(method)
            events.append({"kind": "fix", "method": method})
            if broken.camera_off and method in PHOTO_METHODS:
                events.append({"kind": "buddy_camera"})
        previous_circle_m, circle_m = circle_m, _CIRCLE_PER_SIGMA * math.sqrt(variance)
        was_near, near = (
            near,
            (circle_m > NEAR_HAZARD_FIX_M and to_hazard_m(*estimate) <= circle_m),
        )
        if near and not was_near:
            events.append({"kind": "stop_for_fix"})
        if previous_circle_m <= FIX_REQUEST_OPEN_GROUND_M < circle_m:
            if no_fix_can_reach and mode != "lost":
                # Nothing can be trusted any more: stop, and follow the lost-mode directions.
                mode = "lost"
                events.append({"kind": "lost_mode"})
            elif not no_fix_can_reach:
                events.append({"kind": "fix_requested"})
        steps.append(_step(t, true, estimate, circle_m, sources, events, mode))
    response = {"site": walk.site, "simulated": True, "seed": walk.seed, "steps": steps}
    return SimulateResponse.model_validate(response).model_dump(mode="json", exclude_none=True)


def _site_hazard_distance(site_id: str) -> Callable[[float, float], float]:
    """Ground metres to the nearest hazard on the site's slope layer."""
    grid = load_grid(load_site(site_id), data_root())
    field = hazard_distance_m(grid, HAZARD_SLOPE_DEG)

    def at(x: float, y: float) -> float:
        try:
            return float(field[grid.cell(Point(x=x, y=y))])
        except NoSafeRoute:  # off the map
            return math.inf

    return at


def _reachable(method: str, broken) -> bool:
    """Whether a fix by this method can reach the crew's tablet."""
    if method in PHOTO_METHODS:
        return not (broken.camera_off and broken.radio_off)
    return not broken.drone_grounded


def _update(estimate, variance: float, true, sigma: float, rng) -> tuple[np.ndarray, float]:
    """One Kalman update from a position measurement with a per-axis error of sigma."""
    gain = variance / (variance + sigma**2)
    estimate = estimate + gain * (true + rng.normal(0.0, sigma, 2) - estimate)
    return estimate, variance * (1 - gain)


def _fix_sigma_m(summary: Path) -> float:
    """Per-axis error of one fix: a 2D normal error's median radius is sigma * sqrt(2 ln 2)."""
    median_m = TestSummary.model_validate(json.loads(summary.read_text())).overall.median_error_m
    return max(median_m / math.sqrt(2 * math.log(2)), MIN_FIX_SIGMA_M)


def _point(p: np.ndarray) -> dict:
    return {"x": float(p[0]), "y": float(p[1])}


def _step(
    t_s: float,
    true: np.ndarray,
    estimate: np.ndarray,
    circle_m: float,
    sources: list[str],
    events: list[dict],
    mode: str,
) -> dict:
    """Snapshot the state so later corrections cannot mutate a prediction sample."""
    return {
        "t_s": float(t_s),
        "true_position": _point(true),
        "estimated_position": _point(estimate),
        "uncertainty_m": circle_m,
        "confidence_pct": CIRCLE_COVERAGE * 100,
        "sources": list(dict.fromkeys(sources)),
        "events": list(events),
        "mode": mode,
    }
