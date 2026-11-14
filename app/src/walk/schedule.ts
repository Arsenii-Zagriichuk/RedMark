// What the Walk view asks the walk simulation for: the chosen route, with a horizon fix a
// third of the way in, a ground fix halfway and a drone fix at two thirds, as in the demo
// script (a real horizon fix, then a ground and a drone fix tighten it).
import type { RouteResponse } from "@contracts/route_response";
import type { ScheduledFix, SimulateRequest } from "@contracts/simulate_request";

/** The simulation walks at the 2 km/h planning speed (sim/README.md). */
const PLANNING_SPEED_M_PER_S = 2000 / 3600;
const SEED = 1;

export function fixSchedule(route: RouteResponse): ScheduledFix[] {
  const walk_s = route.total_distance_m / PLANNING_SPEED_M_PER_S;
  return [
    { time_s: Math.round(walk_s / 3), method: "horizon" },
    { time_s: Math.round(walk_s / 2), method: "ground" },
    { time_s: Math.round((walk_s * 2) / 3), method: "drone" },
  ];
}

export function simulateRequest(route: RouteResponse): SimulateRequest {
  return {
    site: route.site,
    path: route.path,
    fix_schedule: fixSchedule(route),
    break_it: { camera_off: false, radio_off: false, drone_grounded: false },
    seed: SEED,
  };
}
