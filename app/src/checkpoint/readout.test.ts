import type { FixResult } from "@contracts/fix_result";
import type { TestMetrics, TestSummary } from "@contracts/test_summary";
import { describe, expect, it } from "vitest";
import { fixReadout, stage2Readout } from "./readout";

const GALE = "+proj=eqc +lat_ts=0 +lon_0=0 +R=3396190 +units=m +no_defs";

// On Gale's map a degree is 3396190 m × π / 180 = 59274.70 m, so this fix sits at
// 4.5000° S 137.4000° E.
const horizonFix: FixResult = {
  photo_id: "NLB_000000001ILT_S0000000NCAM00001M1",
  site: "gale",
  method: "horizon",
  position: { x: 8144343.44, y: -266736.14 },
  heading_deg: 81.25,
  uncertainty_m: 100,
  confidence_pct: 0,
  time_per_fix_s: 6.32,
  terrain_type: "plain",
  simulated: false,
  overlay: "results/horizon/overlays/example.png",
  truth: {
    position: { x: 8144330, y: -266760 },
    heading_deg: 80.159,
    position_error_m: 26.818,
    heading_error_deg: 1.090999999999994,
  },
  provenance: { script: "locate/horizon/hidden_test.py", commit: "abc123", inputs: [] },
};

describe("fixReadout", () => {
  it("reads a measured horizon fix: the circle in ±m, the confidence %, heading and position each with its error", () => {
    expect(fixReadout(horizonFix, GALE)).toEqual({
      method: "horizon",
      photoId: "NLB_000000001ILT_S0000000NCAM00001M1",
      simulated: false,
      circle: "±100 m",
      confidence: "0%",
      low: true,
      heading: "081°",
      headingError: "1.1°",
      position: "4.5000° S 137.4000° E",
      positionError: "27 m",
    });
  });

  it("asks for photos facing other directions only while confidence is below the circle's 95%", () => {
    const at = (confidence_pct: number) => fixReadout({ ...horizonFix, confidence_pct }, GALE);

    expect([at(94.6), at(95), at(100)].map(({ confidence, low }) => [confidence, low])).toEqual([
      ["94.6%", true],
      ["95%", false],
      ["100%", false],
    ]);
  });

  it("shows no errors for a fix without an answer key", () => {
    const { headingError, positionError } = fixReadout({ ...horizonFix, truth: null }, GALE);

    expect([headingError, positionError]).toEqual([null, null]);
  });

  it("gives the position in map metres when the site map has no latitudes", () => {
    const utm = "+proj=utm +zone=45 +ellps=WGS84 +units=m +no_defs";

    expect(fixReadout(horizonFix, utm).position).toBe("8144343, -266736 m");
  });
});

const metrics = (median_error_m: number, n: number): TestMetrics => ({
  n,
  median_error_m,
  within_1m_pct: 100,
  within_5m_pct: 100,
  within_10m_pct: 100,
  median_heading_error_deg: 0,
  median_time_per_fix_s: null,
});

// Stage 2 as Person 3 left it at H12: a no-go, so its results file is an error model.
const stage2: TestSummary = {
  test: "ground-gale",
  site: "gale",
  method: "ground",
  simulated: true,
  overall: metrics(0.338, 40),
  groups: { textured: metrics(0.338, 27), plain: metrics(0.338, 13) },
  provenance: { script: "locate/ground/stage2_result.py", commit: "def456", inputs: [] },
};

describe("stage2Readout", () => {
  it("carries the simulated label the stage 2 results file gives, with its median error", () => {
    expect(stage2Readout(stage2)).toEqual({
      status: "ready",
      simulated: true,
      medianError: "0.34 m",
      stops: 40,
    });
  });

  it("drops the simulated label when stage 2 goes real and its results file is measured", () => {
    const measured = { ...stage2, simulated: false, overall: metrics(3.2, 40) };

    expect(stage2Readout(measured)).toEqual({ status: "ready", simulated: false, medianError: "3.2 m", stops: 40 });
  });

  it("shows a stub stage 2 file as pending, never as a result", () => {
    const stub = { ...stage2, provenance: { script: "stub", commit: "stub", inputs: [] } };

    expect(stage2Readout(stub)).toEqual({ status: "pending" });
  });
});
