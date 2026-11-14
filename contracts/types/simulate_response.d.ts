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
 * Response of POST /simulate: one step per time tick.
 */
export interface SimulateResponse {
  site: SiteId;
  /**
   * A walk simulation is always simulated; the app labels it.
   */
  simulated: true;
  seed: number;
  /**
   * @minItems 1
   */
  steps: [SimStep, ...SimStep[]];
}
/**
 * The walk at one time tick.
 */
export interface SimStep {
  /**
   * Seconds from the start.
   */
  t_s: number;
  true_position: Point;
  estimated_position: Point;
  /**
   * Uncertainty circle radius, ground metres.
   */
  uncertainty_m: number;
  /**
   * Confidence shown with the estimate.
   */
  confidence_pct: number;
  /**
   * Sources active at this tick.
   */
  sources: ("visual_odometry" | "motion_sensor" | "step_count" | "sun" | "horizon" | "ground" | "drone" | "radio")[];
  events: SimEvent[];
  mode: "normal" | "offline" | "lost";
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
 * Something that happened at this tick, e.g. a fix, a fix request, a source lost.
 */
export interface SimEvent {
  /**
   * What happened.
   */
  kind: string;
  method?: Method;
}
