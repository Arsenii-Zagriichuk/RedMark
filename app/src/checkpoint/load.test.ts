import { describe, expect, it, vi } from "vitest";
import { createClient } from "../api/client";
import { demoCache } from "../api/demoCache";
import { loadCheckpoint } from "./load";

describe("loadCheckpoint in demo mode", () => {
  it("answers from the bundled cache with the network off: a real Curiosity horizon fix and stage 2's results file", async () => {
    const fetchFn = vi.fn(async () => {
      throw new Error("the network is off");
    });
    const client = createClient({ mode: "demo", baseUrl: "http://svc", cache: demoCache, fetchFn });

    const { fix, stage2 } = await loadCheckpoint(client);

    expect({
      method: fix.method,
      simulated: fix.simulated,
      tested: fix.truth !== null,
      stub: fix.provenance.script === "stub",
      stage2: [stage2.method, stage2.test],
    }).toEqual({ method: "horizon", simulated: false, tested: true, stub: false, stage2: ["ground", "ground-gale"] });
    expect(fetchFn).not.toHaveBeenCalled();
  });
});
