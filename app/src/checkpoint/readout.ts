// What a Photo checkpoint shows (P1-08), straight from the results files: the horizon fix in
// ±m with its confidence %, its heading and position each with its error against the answer
// key, and whether to ask for photos facing other directions; and stage 2 (the ground fix),
// with the label Person 3's stage 2 results file gives it. A stub is pending, never a result.
import type { FixResult, Method } from "@contracts/fix_result";
import type { TestSummary } from "@contracts/test_summary";
import { formatBearing, formatDistance, formatLatLon } from "../map/geo";

/** The circle is the 95% radius (contracts/schemas/fix_result.json), so a fix is as sure as
 * its circle claims only when its confidence reaches 95%. */
const CONFIDENT_PCT = 95;
const STUB = "stub";

export interface FixReadout {
  method: Method;
  photoId: string;
  simulated: boolean;
  circle: string;
  confidence: string;
  /** Confidence below the circle's 95%: the app asks for photos facing other directions. */
  low: boolean;
  heading: string;
  /** Errors come from the answer key, so only a tested photo has them. */
  headingError: string | null;
  position: string;
  positionError: string | null;
}

export function fixReadout(fix: FixResult, projection: string): FixReadout {
  const { truth } = fix;
  return {
    method: fix.method,
    photoId: fix.photo_id,
    simulated: fix.simulated,
    circle: `±${formatDistance(fix.uncertainty_m)}`,
    confidence: `${Number(fix.confidence_pct.toFixed(1))}%`,
    low: fix.confidence_pct < CONFIDENT_PCT,
    heading: formatBearing(fix.heading_deg),
    headingError: truth && `${Number(truth.heading_error_deg.toFixed(1))}°`,
    position:
      formatLatLon(fix.position, projection) ??
      `${Math.round(fix.position.x)}, ${Math.round(fix.position.y)} m`,
    positionError: truth && formatDistance(truth.position_error_m),
  };
}

export type Stage2Readout =
  | { status: "pending" }
  | { status: "ready"; simulated: boolean; medianError: string; stops: number };

/** Two significant figures below 10 m, where stage 2 works: "0.34 m". */
const formatMetres = (metres: number) =>
  metres < 10 ? `${Number(metres.toPrecision(2))} m` : formatDistance(metres);

export function stage2Readout(summary: TestSummary): Stage2Readout {
  if (summary.provenance.script === STUB) return { status: "pending" };
  return {
    status: "ready",
    simulated: summary.simulated,
    medianError: formatMetres(summary.overall.median_error_m),
    stops: summary.overall.n,
  };
}
