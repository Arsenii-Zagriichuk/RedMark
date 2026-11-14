import { describe, expect, it } from "vitest";
import { captureStep } from "./capture";

describe("captureStep", () => {
  it("starts the skyline round facing the skyline with an empty ring", () => {
    expect(captureStep("skyline", 0)).toEqual({ prompt: "Face the skyline", progress: 0 });
  });

  it("turns the crew left a quarter at a time, a full circle in four photos", () => {
    expect([1, 2, 3, 4].map((captured) => captureStep("skyline", captured))).toEqual([
      { prompt: "Turn left 90°", progress: 0.25 },
      { prompt: "Turn left 90°", progress: 0.5 },
      { prompt: "Turn left 90°", progress: 0.75 },
      { prompt: null, progress: 1 },
    ]);
  });
});

describe("captureStep, photos facing other directions", () => {
  it("turns half a quarter first, so the four new photos face between the first four", () => {
    expect([0, 1, 2, 3, 4].map((captured) => captureStep("other-directions", captured))).toEqual([
      { prompt: "Turn left 45°", progress: 0 },
      { prompt: "Turn left 90°", progress: 0.25 },
      { prompt: "Turn left 90°", progress: 0.5 },
      { prompt: "Turn left 90°", progress: 0.75 },
      { prompt: null, progress: 1 },
    ]);
  });
});
