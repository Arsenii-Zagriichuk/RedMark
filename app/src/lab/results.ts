// What the Test lab shows, straight from the results files: each test's share of fixes
// within 1, 5 and 10 m, overall and by terrain type, and the tested photos. A simulated
// result never appears; a stub (provenance.script "stub") is a test still pending, never a
// real number (AGENTS.md rules 5 and 8).
import type { FixResult, Method, Point } from "@contracts/fix_result";
import type { TestMetrics, TestSummary } from "@contracts/test_summary";

const STUB = "stub";
const GROUPS = ["textured", "plain"] as const;

export interface ChartGroup {
  group: "overall" | (typeof GROUPS)[number];
  n: number;
  median_error_m: number;
  within_1m_pct: number;
  within_5m_pct: number;
  within_10m_pct: number;
}

export type ChartTest =
  | { test: string; method: Method; site: string; status: "pending" }
  | {
      test: string;
      method: Method;
      site: string;
      status: "measured";
      script: string;
      groups: ChartGroup[];
    };

const row = (group: ChartGroup["group"], m: TestMetrics): ChartGroup => ({
  group,
  n: m.n,
  median_error_m: m.median_error_m,
  within_1m_pct: m.within_1m_pct,
  within_5m_pct: m.within_5m_pct,
  within_10m_pct: m.within_10m_pct,
});

export function chartTests(summaries: TestSummary[]): ChartTest[] {
  return summaries
    .filter((summary) => !summary.simulated)
    .sort((a, b) => a.test.localeCompare(b.test))
    .map((summary) => {
      const { test, method, site } = summary;
      if (summary.provenance.script === STUB) return { test, method, site, status: "pending" };
      return {
        test,
        method,
        site,
        status: "measured",
        script: summary.provenance.script,
        groups: [
          row("overall", summary.overall),
          ...GROUPS.map((group) => row(group, summary.groups[group])),
        ],
      };
    });
}

export interface TestedPhoto {
  photo_id: string;
  method: Method;
  site: string;
  terrain_type: FixResult["terrain_type"];
  position_error_m: number;
  /** Heading error is shown for horizon fixes only. */
  heading_error_deg: number | null;
  predicted: Point;
  truth: Point;
  overlay: string;
}

/** Tested photos (with an answer key) whose fix is measured: not simulated, not a stub. */
export function photoList(fixes: FixResult[]): TestedPhoto[] {
  return fixes
    .filter((fix) => fix.truth !== null && !fix.simulated && fix.provenance.script !== STUB)
    .map((fix) => {
      const truth = fix.truth!;
      return {
        photo_id: fix.photo_id,
        method: fix.method,
        site: fix.site,
        terrain_type: fix.terrain_type,
        position_error_m: truth.position_error_m,
        heading_error_deg: fix.method === "horizon" ? truth.heading_error_deg : null,
        predicted: fix.position,
        truth: truth.position,
        overlay: fix.overlay,
      };
    })
    .sort((a, b) => a.photo_id.localeCompare(b.photo_id));
}
