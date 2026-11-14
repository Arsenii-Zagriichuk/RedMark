/* Generated from contracts/schemas by tools/gen_contracts.py. Do not edit by hand. */

/**
 * Gale (the walk) or Jezero (the drone test).
 */
export type SiteId = "gale" | "jezero";
/**
 * fastest safe route, science alternative, or the cart's route to base camp.
 */
export type RouteMode = "fastest" | "science" | "cart";

/**
 * Response of POST /route.
 */
export interface RouteResponse {
  site: SiteId;
  mode: RouteMode;
  /**
   * Ordered positions along the path.
   *
   * @minItems 2
   */
  path: [Point, Point, ...Point[]];
  /**
   * @minItems 1
   */
  legs: [RouteLeg, ...RouteLeg[]];
  /**
   * Ground metres.
   */
  total_distance_m: number;
  /**
   * Walking time.
   */
  total_time_s: number;
  /**
   * Spare time under the walk-back rule at the worst point; negative means the rule fails.
   */
  walk_back_margin_s: number;
  /**
   * For the science route: extra time compared with the fastest route. Null for other modes.
   */
  extra_time_vs_fastest_s: null | number;
  /**
   * Every hard limit, each pass or fail.
   *
   * @minItems 1
   */
  limit_checks: [LimitCheck, ...LimitCheck[]];
  /**
   * Checkpoints along the route, in walking order.
   */
  checkpoints: RouteCheckpoint[];
}
/**
 * A position in map metres in the site's projection.
 */
export interface Point {
  /**
   * Easting, map metres.
   */
  x: number;
  /**
   * Northing, map metres.
   */
  y: number;
}
/**
 * One leg of the path, between two path indexes.
 */
export interface RouteLeg {
  start_index: number;
  end_index: number;
  /**
   * Ground metres.
   */
  distance_m: number;
  /**
   * Walking time.
   */
  time_s: number;
}
/**
 * One hard limit, checked against this route.
 */
export interface LimitCheck {
  limit:
    "slope" | "distance_from_habitat" | "planning_speed" | "walk_time" | "walk_back" | "daylight" | "hazard_margin";
  passed: boolean;
  /**
   * The route's value for this limit.
   */
  value: number;
  /**
   * The limit it was checked against.
   */
  threshold: number;
  /**
   * Units of value and threshold.
   */
  units: string;
}
/**
 * A checkpoint on this route.
 */
export interface RouteCheckpoint {
  /**
   * Stable id, used in other files.
   */
  id: string;
  position: Point;
}
