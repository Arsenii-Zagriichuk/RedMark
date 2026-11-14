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
 * Body of POST /route. Engine: Person 4; served by Person 1's service.
 */
export interface RouteRequest {
  site: SiteId;
  start: Point;
  goal: Point;
  mode: RouteMode;
  /**
   * Current uncertainty circle radius in ground metres; the hazard margin grows with it.
   */
  uncertainty_m: number;
  limits: RouteLimits;
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
 * The hard limits for this request. Defaults from Artemis planning: 20° slope (15° as an option), 2 km from the habitat, 2 km/h planning speed, about 6 h walk.
 */
export interface RouteLimits {
  /**
   * Steepest slope allowed.
   */
  max_slope_deg: number;
  /**
   * Distance from the habitat no point may exceed.
   */
  max_distance_from_habitat_m: number;
  /**
   * Planning walk speed.
   */
  planning_speed_kmh: number;
  /**
   * Longest walk, exit to re-entry.
   */
  max_walk_h: number;
}
