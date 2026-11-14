// Lost mode (P1-07): when no source can be trusted, the app shows the last known position,
// a return direction and landmark directions. The way back is planned by the route engine
// with the uncertainty circle as its hazard margin, so it keeps further from steep ground
// the less sure the position is. The landmark directions come from layer 5 (Person 3's
// layers/location_quality/directions.py), never written here.
import type { RouteRequest } from "@contracts/route_request";
import type { Point, RouteResponse } from "@contracts/route_response";
import type { SimulateResponse } from "@contracts/simulate_response";
import { distanceAndBearing } from "../map/geo";

/** The return direction looks past the route grid's first few steps, to where the path goes. */
const LOOK_AHEAD_M = 20;

export interface LastKnown {
  index: number;
  t_s: number;
  position: Point;
  uncertainty_m: number;
}

/** Where lost mode began in a run: the last position the crew can trust, or null if never. */
export function lostModeStart(simulation: SimulateResponse): LastKnown | null {
  const index = simulation.steps.findIndex((step) => step.mode === "lost");
  if (index === -1) return null;
  const step = simulation.steps[index]!;
  return { index, t_s: step.t_s, position: step.estimated_position, uncertainty_m: step.uncertainty_m };
}

/** The contract wants a walk-time limit above 0; a spent one leaves 1 s, which no walk fits. */
const SPENT_WALK_H = 1 / 3600;

/**
 * The walk back: the fastest safe route from the last known position to where the walk
 * began. The walk-time limit runs from exit to re-entry, so the time already walked comes
 * off it.
 */
export function returnRequest(planned: RouteRequest, from: LastKnown): RouteRequest {
  const left_h = planned.limits.max_walk_h - from.t_s / 3600;
  return {
    ...planned,
    mode: "fastest",
    start: from.position,
    goal: planned.start,
    uncertainty_m: from.uncertainty_m,
    limits: { ...planned.limits, max_walk_h: Math.max(left_h, SPENT_WALK_H) },
  };
}

/** The heading to set off on: towards the first point of the path at least 20 m away. */
export function returnHeading(path: Point[]): number {
  const start = path[0]!;
  const ahead =
    path.find((point) => distanceAndBearing(start, point).metres >= LOOK_AHEAD_M) ?? path[path.length - 1]!;
  return distanceAndBearing(start, ahead).bearing;
}

/** Layer 5's directions: the path its legs follow, and each leg's text (null: none in view). */
export interface LandmarkDirections {
  path: Point[];
  legs: { leg: number; start_index: number; end_index: number; text: string | null }[];
}

export type LostDirection =
  | { kind: "landmark"; leg: number; legs: number; text: string }
  | { kind: "none-in-view"; leg: number; legs: number }
  | { kind: "not-this-route" };

export const samePoint = (a: Point, b: Point | null | undefined) => !!b && a.x === b.x && a.y === b.y;

function samePath(a: Point[], b: Point[]): boolean {
  return a.length === b.length && a.every((point, i) => samePoint(point, b[i]));
}

function toSegment(point: Point, a: Point, b: Point): number {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const length2 = dx * dx + dy * dy;
  const t = length2 ? Math.min(1, Math.max(0, ((point.x - a.x) * dx + (point.y - a.y) * dy) / length2)) : 0;
  return Math.hypot(point.x - (a.x + t * dx), point.y - (a.y + t * dy));
}

/** Layer 5's direction for the leg of the walked route nearest a position. */
export function landmarkDirection(
  directions: LandmarkDirections | null,
  route: RouteResponse,
  position: Point,
): LostDirection {
  if (!directions?.legs.length || !samePath(directions.path, route.path)) return { kind: "not-this-route" };
  const distance = (leg: LandmarkDirections["legs"][number]) => {
    let nearest = Infinity;
    for (let i = leg.start_index; i < leg.end_index; i++) {
      nearest = Math.min(nearest, toSegment(position, route.path[i]!, route.path[i + 1]!));
    }
    return nearest;
  };
  const leg = directions.legs.reduce((best, candidate) => (distance(candidate) < distance(best) ? candidate : best));
  const legs = directions.legs.length;
  return leg.text === null
    ? { kind: "none-in-view", leg: leg.leg, legs }
    : { kind: "landmark", leg: leg.leg, legs, text: leg.text };
}
