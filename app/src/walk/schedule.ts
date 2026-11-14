// What the Walk view asks the walk simulation for: the chosen route, with a horizon fix a
// third of the way in, a ground fix halfway and a drone fix at two thirds, as in the demo
// script (a real horizon fix, then a ground and a drone fix tighten it). A break-it
// scenario (P1-07) re-runs the same walk with sources switched off.
import type { RouteResponse } from "@contracts/route_response";
import type { BreakIt, ScheduledFix, SimulateRequest } from "@contracts/simulate_request";

/** The simulation walks at the 2 km/h planning speed (sim/README.md). */
const PLANNING_SPEED_M_PER_S = 2000 / 3600;
const SEED = 1;

/** The normal walk and the four break-it scenarios, as sim/cache_runs.py names them. */
export type Scenario = "normal" | "camera-off" | "radio-off" | "drone-grounded" | "everything";

const BREAK_IT: Record<Scenario, BreakIt> = {
  normal: { camera_off: false, radio_off: false, drone_grounded: false },
  "camera-off": { camera_off: true, radio_off: false, drone_grounded: false },
  "radio-off": { camera_off: false, radio_off: true, drone_grounded: false },
  "drone-grounded": { camera_off: false, radio_off: false, drone_grounded: true },
  everything: { camera_off: true, radio_off: true, drone_grounded: true },
};

export function fixSchedule(route: RouteResponse): ScheduledFix[] {
  const walk_s = route.total_distance_m / PLANNING_SPEED_M_PER_S;
  return [
    { time_s: Math.round(walk_s / 3), method: "horizon" },
    { time_s: Math.round(walk_s / 2), method: "ground" },
    { time_s: Math.round((walk_s * 2) / 3), method: "drone" },
  ];
}

export function simulateRequest(route: RouteResponse, scenario: Scenario = "normal"): SimulateRequest {
  return {
    site: route.site,
    path: route.path,
    fix_schedule: fixSchedule(route),
    break_it: BREAK_IT[scenario],
    seed: SEED,
  };
}
