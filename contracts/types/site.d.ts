/* Generated from contracts/schemas by tools/gen_contracts.py. Do not edit by hand. */

/**
 * Gale (the walk) or Jezero (the drone test).
 */
export type SiteId = "gale" | "jezero";

/**
 * One site's config, in sites/<site>.yaml. Owner: Person 2 (replayed sol from Person 4).
 */
export interface SiteConfig {
  site: SiteId;
  /**
   * Display name.
   */
  name: string;
  /**
   * The site map's projection as a PROJ string. Jezero is reprojected so map metres are ground metres.
   */
  projection: string;
  bounds: Bounds;
  habitat: null | Point;
  base_camp: null | Point;
  /**
   * Empty at Jezero.
   */
  science_targets: ScienceTarget[];
  /**
   * Empty at Jezero.
   */
  checkpoints: Checkpoint[];
  /**
   * Named data files, each a path relative to REDMARK_DATA.
   */
  files: {
    [k: string]: string;
  };
  /**
   * The real sol whose conditions play during the walk (4600 to 4709 by the team plan); null at Jezero.
   */
  replayed_sol: null | number;
}
/**
 * Walk area bounds (Gale) or crop bounds (Jezero).
 */
export interface Bounds {
  /**
   * West edge.
   */
  min_x: number;
  /**
   * South edge.
   */
  min_y: number;
  /**
   * East edge.
   */
  max_x: number;
  /**
   * North edge.
   */
  max_y: number;
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
 * A spot the crew samples: a ridge centre or a hollow Curiosity did not reach.
 */
export interface ScienceTarget {
  /**
   * Stable id, used in other files.
   */
  id: string;
  position: Point;
  /**
   * Display name.
   */
  name: string;
}
/**
 * A spot on the route where the crew stops to take a fix.
 */
export interface Checkpoint {
  /**
   * Stable id, used in other files.
   */
  id: string;
  position: Point;
}
