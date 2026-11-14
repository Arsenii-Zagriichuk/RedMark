import type { FixResult } from "@contracts/fix_result";
import { describe, expect, it, vi } from "vitest";
import { createClient } from "../api/client";
import { demoCache } from "../api/demoCache";
import {
  bundledDroneImages,
  DRONE_FIX_FALLBACK,
  droneFixImages,
  loadDroneFix,
} from "./droneFix";

describe("loadDroneFix", () => {
  it("answers the Gale drone fix from the demo cache, simulated, with no network", async () => {
    const fetchFn = vi.fn(async () => new Response("{}", { status: 500 }));
    const client = createClient({ mode: "demo", baseUrl: "http://svc", cache: demoCache, fetchFn });

    const fix = await loadDroneFix(client);

    expect(fix.photo_id).toBe("gale-sim-drone-0001");
    expect(fix.method).toBe("drone");
    expect(fix.simulated).toBe(true);
    expect(fetchFn).not.toHaveBeenCalled();
  });
});

const fix: FixResult = {
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
  overlay: "results/drone/overlays/gale-sim-drone-0001-loftr-run1.png",
  truth: null,
  provenance: { script: "locate/drone/gale_fix.py", commit: "1839c70", inputs: [] },
};

const bundled = {
  "gale-sim-drone-0001-loftr-run1.png": "/assets/sheet-abc.png",
  "gale-sim-drone-0001-photo-run1.png": "/assets/photo-abc.png",
};

describe("droneFixImages", () => {
  it("in demo mode takes both images from the bundled cache, never the service", () => {
    const fileUrl = vi.fn((path: string) => `http://svc${path}`);

    expect(droneFixImages(fix, "demo", { bundled, fileUrl })).toEqual({
      sheet: "/assets/sheet-abc.png",
      photo: "/assets/photo-abc.png",
    });
    expect(fileUrl).not.toHaveBeenCalled();
  });

  it("in live mode asks the service for the overlay and the photo beside it", () => {
    const fileUrl = (path: string) => `http://svc${path}`;

    expect(droneFixImages(fix, "live", { bundled: {}, fileUrl })).toEqual({
      sheet: "http://svc/overlays/results/drone/overlays/gale-sim-drone-0001-loftr-run1.png",
      photo: "http://svc/overlays/results/drone/overlays/gale-sim-drone-0001-photo-run1.png",
    });
  });

  it("falls back to the static images when the cache lacks them", () => {
    const fileUrl = (path: string) => `http://svc${path}`;

    expect(droneFixImages(fix, "demo", { bundled: {}, fileUrl })).toEqual(DRONE_FIX_FALLBACK);
  });

  it("finds both images of the cached Gale drone fix in the bundle", async () => {
    const client = createClient({ mode: "demo", baseUrl: "http://svc", cache: demoCache });
    const cached = await loadDroneFix(client);
    const fileUrl = (path: string) => `http://svc${path}`;

    const images = droneFixImages(cached, "demo", { bundled: bundledDroneImages, fileUrl });

    expect(images.sheet).not.toBe(DRONE_FIX_FALLBACK.sheet);
    expect(images.photo).not.toBe(DRONE_FIX_FALLBACK.photo);
  });
});
