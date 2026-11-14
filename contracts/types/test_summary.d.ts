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
 * The measured results of one test, written only through the shared scorer in contracts/scoring/. Path: results/<method>/<test>.json.
 */
export interface TestSummary {
  /**
   * Test id, e.g. drone-jezero or horizon-gale.
   */
  test: string;
  site: SiteId;
  method: Method;
  /**
   * True for a simulated error model (e.g. stage 2 if the real attempt fails). The Test lab never shows these.
   */
  simulated: boolean;
  overall: TestMetrics;
  /**
   * The same numbers split by terrain type (textured, plain), plus any extra split such as hard_mode.
   */
  groups: {
    textured: TestMetrics;
    plain: TestMetrics;
    [k: string]: TestMetrics;
  };
  provenance: Provenance;
}
/**
 * Measured numbers for one group of fixes, all from the shared scorer.
 */
export interface TestMetrics {
  /**
   * Number of fixes.
   */
  n: number;
  /**
   * Median position error, ground metres.
   */
  median_error_m: number;
  /**
   * Share of fixes with error ≤ 1 m.
   */
  within_1m_pct: number;
  /**
   * Share of fixes with error ≤ 5 m.
   */
  within_5m_pct: number;
  /**
   * Share of fixes with error ≤ 10 m.
   */
  within_10m_pct: number;
  /**
   * Median heading error; null when the method gives no heading to score.
   */
  median_heading_error_deg: null | number;
  /**
   * Median seconds per fix; null for a simulated error model.
   */
  median_time_per_fix_s: null | number;
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
