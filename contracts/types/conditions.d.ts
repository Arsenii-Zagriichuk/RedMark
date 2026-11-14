/* Generated from contracts/schemas by tools/gen_contracts.py. Do not edit by hand. */

/**
 * Gale (the walk) or Jezero (the drone test).
 */
export type SiteId = "gale" | "jezero";

/**
 * Conditions on the replayed sol, in conditions/<sol>.json. Producer: Person 4.
 */
export interface Conditions {
  site: SiteId;
  sol: number;
  /**
   * Daily radiation dose from RAD, µGy/day.
   */
  radiation_ugy_per_day: number;
  dust: Dust;
  /**
   * Sunset, local mean solar time, HH:MM.
   */
  sunset_lmst: string;
  /**
   * @minItems 1
   */
  steps: [ConditionsStep, ...ConditionsStep[]];
  provenance: Provenance;
}
/**
 * Dust optical depth, labelled measured or estimated.
 */
export interface Dust {
  /**
   * Atmospheric optical depth (tau).
   */
  optical_depth: number;
  source: "measured" | "estimated";
}
/**
 * Conditions at one local time.
 */
export interface ConditionsStep {
  /**
   * Local mean solar time, HH:MM.
   */
  lmst: string;
  /**
   * Air temperature from REMS.
   */
  temperature_c: number;
  /**
   * Pressure from REMS.
   */
  pressure_pa: number;
  /**
   * Sun direction from map north.
   */
  sun_azimuth_deg: number;
  /**
   * Sun elevation.
   */
  sun_elevation_deg: number;
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
