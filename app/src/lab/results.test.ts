import type { FixResult } from "@contracts/fix_result";
import type { TestMetrics, TestSummary } from "@contracts/test_summary";
import { describe, expect, it } from "vitest";
import { chartTests, photoList } from "./results";

const metrics = (n: number, median: number, w1: number, w5: number, w10: number): TestMetrics => ({
  n,
  median_error_m: median,
  within_1m_pct: w1,
  within_5m_pct: w5,
  within_10m_pct: w10,
  median_heading_error_deg: 1.5,
  median_time_per_fix_s: 4,
});

const measured = (script: string) => ({ script, commit: "abc123", inputs: [] });

const horizon: TestSummary = {
  test: "horizon-gale",
  site: "gale",
  method: "horizon",
  simulated: false,
  overall: metrics(20, 83, 0, 5, 15),
  groups: {
    textured: metrics(12, 60, 0, 8, 25),
    plain: metrics(8, 120, 0, 0, 0),
    hollow: metrics(4, 140, 0, 0, 0),
  },
  provenance: measured("locate/horizon/hidden_test.py"),
};
const droneStub: TestSummary = {
  ...horizon,
  test: "drone-jezero",
  site: "jezero",
  method: "drone",
  provenance: measured("stub"),
};
const groundSimulated: TestSummary = {
  ...horizon,
  test: "ground-gale",
  method: "ground",
  simulated: true,
  provenance: measured("locate/ground/test.py"),
};

describe("chartTests", () => {
  it("charts a measured test overall and by terrain type, marks a stub pending, and drops a simulated one", () => {
    expect(chartTests([groundSimulated, droneStub, horizon])).toEqual([
      { test: "drone-jezero", method: "drone", site: "jezero", status: "pending" },
      {
        test: "horizon-gale",
        method: "horizon",
        site: "gale",
        status: "measured",
        script: "locate/horizon/hidden_test.py",
        groups: [
          { group: "overall", n: 20, median_error_m: 83, within_1m_pct: 0, within_5m_pct: 5, within_10m_pct: 15 },
          { group: "textured", n: 12, median_error_m: 60, within_1m_pct: 0, within_5m_pct: 8, within_10m_pct: 25 },
          { group: "plain", n: 8, median_error_m: 120, within_1m_pct: 0, within_5m_pct: 0, within_10m_pct: 0 },
        ],
      },
    ]);
  });
});

function fix(photo_id: string, overrides: Partial<FixResult>): FixResult {
  return {
    photo_id,
    site: "gale",
    method: "horizon",
    position: { x: 100, y: 200 },
    heading_deg: 132.8,
    uncertainty_m: 40,
    confidence_pct: 60,
    time_per_fix_s: 6.3,
    terrain_type: "textured",
    simulated: false,
    overlay: `results/horizon/overlays/${photo_id}.png`,
    truth: { position: { x: 127, y: 153 }, heading_deg: 130.1, position_error_m: 54.6, heading_error_deg: 2.7 },
    provenance: measured("locate/horizon/hidden_test.py"),
    ...overrides,
  };
}

describe("photoList", () => {
  it("lists only tested photos with measured results, horizon ones with their heading error", () => {
    const fixes = [
      fix("NLB_002", {}),
      fix("HNM_001", {
        site: "jezero",
        method: "drone",
        overlay: "results/drone/overlays/HNM_001.png",
        truth: { position: { x: 3, y: 4 }, heading_deg: 90, position_error_m: 4.2, heading_error_deg: 1 },
        provenance: measured("locate/drone/drone_test.py"),
      }),
      fix("HNM_untested", { method: "drone", truth: null }),
      fix("stub-navcam", { provenance: measured("stub") }),
      fix("SIM_001", { simulated: true }),
    ];

    expect(photoList(fixes)).toEqual([
      {
        photo_id: "HNM_001",
        method: "drone",
        site: "jezero",
        terrain_type: "textured",
        position_error_m: 4.2,
        heading_error_deg: null,
        predicted: { x: 100, y: 200 },
        truth: { x: 3, y: 4 },
        overlay: "results/drone/overlays/HNM_001.png",
      },
      {
        photo_id: "NLB_002",
        method: "horizon",
        site: "gale",
        terrain_type: "textured",
        position_error_m: 54.6,
        heading_error_deg: 2.7,
        predicted: { x: 100, y: 200 },
        truth: { x: 127, y: 153 },
        overlay: "results/horizon/overlays/NLB_002.png",
      },
    ]);
  });
});
