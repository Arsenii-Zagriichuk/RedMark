// Planning: the three route requests for a walk to one science target, and the walk limits
// of a route as rows that each say pass, fail or not checked.
import type { RouteMode, RouteRequest } from "@contracts/route_request";
import type { LimitCheck, RouteResponse } from "@contracts/route_response";
import type { ScienceTarget, SiteConfig } from "@contracts/site";
import { ApiError } from "../api/client";
import { formatDistance } from "../map/geo";

/** The slope limit options: 20° by default (Artemis planning), 15° as the cautious one. */
export const SLOPE_LIMITS = [20, 15] as const;
export type SlopeLimit = (typeof SLOPE_LIMITS)[number];

// The other hard limits, from Artemis planning (contracts/schemas/route_request.json).
const MAX_DISTANCE_FROM_HABITAT_M = 2000;
const PLANNING_SPEED_KMH = 2;
const MAX_WALK_H = 6;

export const ROUTE_MODES: readonly RouteMode[] = ["fastest", "science", "cart"];

/**
 * The fastest and science routes walk from base camp (or the habitat, if there is none) to
 * the target; the cart drives from the habitat to base camp. Planning happens at the
 * habitat, whose position is known exactly, so the uncertainty circle is 0 m.
 */
export function routeRequests(
  site: SiteConfig,
  target: ScienceTarget,
  slopeLimit: SlopeLimit,
): Record<RouteMode, RouteRequest | null> {
  const limits = {
    max_slope_deg: slopeLimit,
    max_distance_from_habitat_m: MAX_DISTANCE_FROM_HABITAT_M,
    planning_speed_kmh: PLANNING_SPEED_KMH,
    max_walk_h: MAX_WALK_H,
  };
  const walkFrom = site.base_camp ?? site.habitat;
  const request = (mode: RouteMode, start: RouteRequest["start"], goal: RouteRequest["goal"]) =>
    ({ site: site.site, start, goal, mode, uncertainty_m: 0, limits }) satisfies RouteRequest;
  return {
    fastest: walkFrom && request("fastest", walkFrom, target.position),
    science: walkFrom && request("science", walkFrom, target.position),
    cart: site.habitat && site.base_camp && request("cart", site.habitat, site.base_camp),
  };
}

/** Why the service refused a route: the engine's reason when it gave one. */
export function refusal(reason: unknown): string {
  if (reason instanceof ApiError && reason.body && typeof reason.body === "object") {
    const detail = (reason.body as { detail?: unknown }).detail;
    // The screen already says "No safe route:", so drop the engine's own prefix.
    if (typeof detail === "string") return detail.replace(/^no safe route:\s*/i, "");
    // A request that breaks the route_request contract: FastAPI lists what is wrong.
    if (Array.isArray(detail)) {
      return detail.map((item: { msg?: string }) => item.msg ?? JSON.stringify(item)).join("; ");
    }
  }
  return reason instanceof Error ? reason.message : String(reason);
}

export function formatDuration(seconds: number): string {
  if (seconds < 0) return `-${formatDuration(-seconds)}`;
  const minutes = Math.round(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (!hours) return `${rest} min`;
  return rest ? `${hours} h ${rest} min` : `${hours} h`;
}

type Limit = LimitCheck["limit"];

const LIMITS: { limit: Limit; label: string; kind: "max" | "min" | "" }[] = [
  { limit: "slope", label: "Slope", kind: "max" },
  { limit: "distance_from_habitat", label: "From habitat", kind: "" },
  { limit: "planning_speed", label: "Planning speed", kind: "" },
  { limit: "walk_time", label: "Walk time", kind: "" },
  { limit: "walk_back", label: "Walk-back margin", kind: "" },
  { limit: "daylight", label: "Daylight", kind: "" },
  { limit: "hazard_margin", label: "Hazard margin", kind: "min" },
];

export interface LimitRow {
  limit: Limit;
  label: string;
  text: string;
  status: "pass" | "fail" | "not-checked";
}

function describe(check: LimitCheck, kind: string): string {
  const suffix = kind ? ` ${kind}` : "";
  const round = (value: number) => String(Number(value.toFixed(1)));
  switch (check.units) {
    case "deg":
      return `${Math.round(check.value)}° / ${Math.round(check.threshold)}°${suffix}`;
    case "m":
      return `${formatDistance(check.value)} / ${formatDistance(check.threshold)}${suffix}`;
    case "km/h":
      return `${round(check.value)} km/h / ${round(check.threshold)} km/h${suffix}`;
    case "h":
      return `${formatDuration(check.value * 3600)} / ${round(check.threshold)} h${suffix}`;
    case "s":
      // walk-back and daylight: spare time, which must stay at or above zero
      return check.value < 0
        ? `${formatDuration(-check.value)} short`
        : `${formatDuration(check.value)} spare`;
    default:
      return `${round(check.value)} ${check.units} / ${round(check.threshold)} ${check.units}`;
  }
}

/** Every hard limit, in the screen's order; one the route didn't check says so. */
export function limitRows(route: RouteResponse): LimitRow[] {
  return LIMITS.map(({ limit, label, kind }) => {
    const check = route.limit_checks.find((candidate) => candidate.limit === limit);
    if (!check) return { limit, label, text: "not checked", status: "not-checked" };
    return { limit, label, text: describe(check, kind), status: check.passed ? "pass" : "fail" };
  });
}
