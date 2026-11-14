import type { FixResult } from "@contracts/fix_result";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { FixCard } from "./FixCard";

const galeDroneFix: FixResult = {
  photo_id: "gale-sim-drone-0001",
  site: "gale",
  method: "drone",
  position: { x: 8142346.07, y: -285502.04 },
  heading_deg: 162.2,
  uncertainty_m: 10,
  confidence_pct: 0,
  time_per_fix_s: 10.03,
  terrain_type: "textured",
  simulated: true,
  overlay: "results/drone/overlays/gale-sim-drone-0001-loftr-run.png",
  truth: null,
  provenance: { script: "locate/drone/gale_fix.py", commit: "1839c70", inputs: [] },
};

const text = (fix: FixResult) => renderToStaticMarkup(<FixCard fix={fix} />);

describe("FixCard", () => {
  it("labels a simulated fix Simulated", () => {
    expect(text(galeDroneFix)).toContain("Simulated");
  });

  it("does not label a measured fix Simulated", () => {
    expect(text({ ...galeDroneFix, simulated: false })).not.toContain("Simulated");
  });

  it("shows a measured fix's circle, heading, confidence and time", () => {
    const html = text({ ...galeDroneFix, simulated: false, confidence_pct: 72 });
    expect(html).toContain("±10 m");
    expect(html).toContain("162°");
    expect(html).toContain("72%");
    expect(html).toContain("10.0 s");
  });

  it("reports no numbers from a simulated fix", () => {
    const html = text(galeDroneFix);
    for (const number of ["±10 m", "162°", "0%", "10.0 s"]) expect(html).not.toContain(number);
  });
});
