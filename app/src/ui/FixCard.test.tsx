import type { Method } from "@contracts/fix_result";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { FixCard } from "./FixCard";

const METHODS = ["horizon", "ground", "drone"] as const;

const render = (method: Method, simulated: boolean) =>
  renderToStaticMarkup(
    <FixCard method={method} simulated={simulated} source="Curiosity Navcam frame">
      <span>±100 m</span>
    </FixCard>,
  );

describe("FixCard", () => {
  it("always prints the Simulated label on a simulated fix, whatever its method", () => {
    expect(METHODS.map((method) => render(method, true))).toEqual([
      expect.stringContaining(">Simulated<"),
      expect.stringContaining(">Simulated<"),
      expect.stringContaining(">Simulated<"),
    ]);
  });

  it("labels a fix measured on real photos as measured, never simulated", () => {
    const html = render("horizon", false);

    expect([html.includes(">Measured<"), html.includes("Simulated")]).toEqual([true, false]);
  });
});
