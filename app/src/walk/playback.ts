// Reading a simulated walk at one step: where the walker is, how sure the position is, how
// much walk is left and where to head next. Steps play in array order: at a fix the
// simulation gives the predicted step and then the corrected one, at the same time.
import type { Point, RouteResponse } from "@contracts/route_response";
import type { Method, SimulateResponse } from "@contracts/simulate_response";
import { distanceAndBearing, formatBearing } from "../map/geo";

/** Sure up to 5 m (interface system); over 10 m the simulation asks for a fix (sim/README.md). */
const SURE_M = 5;
const FIX_REQUEST_M = 10;

export type ConfidenceLevel = "sure" | "check" | "over";

export interface WalkStatus {
  t_s: number;
  position: Point;
  uncertainty_m: number;
  confidence_pct: number;
  level: ConfidenceLevel;
  timeLeft_s: number;
  distanceLeft_m: number;
  instruction: string;
  waypointBearing: number;
  waypointDistance_m: number;
  simulated: boolean;
}

function pathLengths(path: Point[]): number[] {
  const lengths = [0];
  for (let i = 1; i < path.length; i++) {
    const previous = path[i - 1]!;
    const point = path[i]!;
    lengths.push(lengths[i - 1]! + Math.hypot(point.x - previous.x, point.y - previous.y));
  }
  return lengths;
}

/** How far along the path a point lies: the distance walked to its nearest path vertex. */
function alongPath(point: Point, path: Point[], lengths: number[]): number {
  let best = 0;
  path.forEach((vertex, i) => {
    const nearest = path[best]!;
    if (Math.hypot(vertex.x - point.x, vertex.y - point.y) < Math.hypot(nearest.x - point.x, nearest.y - point.y)) {
      best = i;
    }
  });
  return lengths[best]!;
}

export function walkStatus(
  simulation: SimulateResponse,
  index: number,
  route: RouteResponse,
  targetName: string,
): WalkStatus {
  const step = simulation.steps[index]!;
  const end_s = simulation.steps[simulation.steps.length - 1]!.t_s;
  const progress = end_s > 0 ? step.t_s / end_s : 1;
  const lengths = pathLengths(route.path);
  const walked_m = route.total_distance_m * progress;

  // The next checkpoint along the route, else the end of the route (the target).
  const ahead = route.checkpoints.findIndex(
    (checkpoint) => alongPath(checkpoint.position, route.path, lengths) > walked_m,
  );
  const goal = route.path[route.path.length - 1]!;
  const waypoint = ahead >= 0 ? route.checkpoints[ahead]!.position : goal;
  const name = ahead >= 0 ? `checkpoint ${ahead + 1}` : targetName;
  const { metres, bearing } = distanceAndBearing(step.estimated_position, waypoint);

  return {
    t_s: step.t_s,
    position: step.estimated_position,
    uncertainty_m: step.uncertainty_m,
    confidence_pct: step.confidence_pct,
    level:
      step.uncertainty_m <= SURE_M ? "sure" : step.uncertainty_m <= FIX_REQUEST_M ? "check" : "over",
    timeLeft_s: end_s - step.t_s,
    distanceLeft_m: route.total_distance_m - walked_m,
    instruction: `Head ${formatBearing(bearing)} to ${name}`,
    waypointBearing: bearing,
    waypointDistance_m: metres,
    simulated: simulation.simulated,
  };
}

export interface FixEvent {
  index: number;
  t_s: number;
  /** Where on the timeline, from 0 (start) to 1 (end). */
  fraction: number;
  kind: string;
  method: Method | null;
}

/** Every fix and fix request in the walk, for the timeline. */
export function fixEvents(simulation: SimulateResponse): FixEvent[] {
  const end_s = simulation.steps[simulation.steps.length - 1]?.t_s ?? 0;
  return simulation.steps.flatMap((step, index) =>
    step.events
      .filter((event) => event.kind === "fix" || event.kind === "fix_requested")
      .map((event) => ({
        index,
        t_s: step.t_s,
        fraction: end_s > 0 ? step.t_s / end_s : 0,
        kind: event.kind,
        method: event.method ?? null,
      })),
  );
}
