/* Generated from contracts/schemas by tools/gen_contracts.py. Do not edit by hand. */

/**
 * Gale (the walk) or Jezero (the drone test).
 */
export type SiteId = "gale" | "jezero";
/**
 * How a fix was made.
 */
export type Method = "horizon" | "ground" | "drone";

/**
 * Body of POST /simulate. Engine: Person 4.
 */
export interface SimulateRequest {
  site: SiteId;
  /**
   * Ordered positions along the path.
   *
   * @minItems 2
   */
  path: [Point, Point, ...Point[]];
  fix_schedule: ScheduledFix[];
  break_it: BreakIt;
  /**
   * The same seed and inputs replay the same walk.
   */
  seed: number;
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
 * A fix planned at a time into the walk.
 */
export interface ScheduledFix {
  /**
   * Seconds from the start.
   */
  time_s: number;
  method: Method;
}
/**
 * Break-it scenario flags; all true is everything at once (lost mode).
 */
export interface BreakIt {
  camera_off: boolean;
  radio_off: boolean;
  drone_grounded: boolean;
}
