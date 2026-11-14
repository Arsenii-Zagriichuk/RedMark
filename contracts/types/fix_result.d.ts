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
 * The class every test result is split by: textured (ridges, rock) or plain (sand).
 */
export type TerrainType = "textured" | "plain";

/**
 * One fix from one method at one moment. Producers: Person 2 (drone), Person 3 (horizon, ground). Path: results/<method>/fixes/<photo_id>.json.
 */
export interface FixResult {
  /**
   * The photo's id in its archive.
   */
  photo_id: string;
  site: SiteId;
  method: Method;
  position: Point;
  /**
   * Estimated heading from map north.
   */
  heading_deg: number;
  /**
   * Uncertainty circle radius in ground metres. PROPOSED, confirm at H0: the 95% radius.
   */
  uncertainty_m: number;
  /**
   * PROPOSED, confirm at H0: the share of tested fixes, for this method and terrain type, whose true position fell inside their circle.
   */
  confidence_pct: number;
  /**
   * Seconds the fix took to compute.
   */
  time_per_fix_s: number;
  terrain_type: TerrainType;
  /**
   * True for any result not measured on real photos. Required, no default; the app shows a label whenever it is true.
   */
  simulated: boolean;
  /**
   * Repo-relative path of the overlay image that draws this fix on the base map.
   */
  overlay: string;
  /**
   * Answer-key values for a tested photo; null for a fix on the demo walk.
   */
  truth: null | Truth;
  provenance: Provenance;
}
/**
 * Estimated position.
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
 * Answer-key values. Only tested photos have them.
 */
export interface Truth {
  position: Point1;
  /**
   * True heading from map north.
   */
  heading_deg: number;
  /**
   * Error in ground metres, from the shared scorer.
   */
  position_error_m: number;
  /**
   * Heading error from the shared scorer; wraps at 360°, so 0 to 180.
   */
  heading_error_deg: number;
}
/**
 * A position in map metres in the site's projection.
 */
export interface Point1 {
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
 * Which script, commit and inputs wrote a results file. Required on every results file. A hand-made stub has script "stub", and nothing may show a stub's numbers as real.
 */
export interface Provenance {
  /**
   * Repo path of the script that wrote the file, or "stub".
   */
  script: string;
  /**
   * Git commit the script ran at.
   */
  commit: string;
  /**
   * Every input file the script read.
   */
  inputs: ProvenanceInput[];
}
/**
 * One input file and its checksum.
 */
export interface ProvenanceInput {
  /**
   * Path of the input file.
   */
  path: string;
  /**
   * SHA-256 of the input file.
   */
  sha256: string;
}
