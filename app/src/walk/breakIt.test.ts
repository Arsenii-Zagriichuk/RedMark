import type { RouteRequest } from "@contracts/route_request";
import type { RouteResponse } from "@contracts/route_response";
import type { SimStep, SimulateResponse } from "@contracts/simulate_response";
import { describe, expect, it } from "vitest";
import { walkBadges } from "./breakIt";
import { landmarkDirection, lostModeStart, returnHeading, returnRequest } from "./lost";
import { simulateRequest } from "./schedule";

// A straight 1800 m walk due north, then 900 m east.
const route: RouteResponse = {
  site: "gale",
  mode: "fastest",
  path: [
    { x: 0, y: 0 },
    { x: 0, y: 900 },
    { x: 900, y: 900 },
  ],
  legs: [
    { start_index: 0, end_index: 1, distance_m: 900, time_s: 1620 },
    { start_index: 1, end_index: 2, distance_m: 900, time_s: 1620 },
  ],
  total_distance_m: 1800,
  total_time_s: 3240,
  walk_back_margin_s: 3600,
  extra_time_vs_fastest_s: null,
  limit_checks: [{ limit: "slope", passed: true, value: 4, threshold: 20, units: "deg" }],
  checkpoints: [],
};

describe("simulateRequest for a break-it scenario", () => {
  it.each([
    ["camera-off", { camera_off: true, radio_off: false, drone_grounded: false }],
    ["radio-off", { camera_off: false, radio_off: true, drone_grounded: false }],
    ["drone-grounded", { camera_off: false, radio_off: false, drone_grounded: true }],
    ["everything", { camera_off: true, radio_off: true, drone_grounded: true }],
  ] as const)("%s re-runs the same walk with its source switched off", (scenario, breakIt) => {
    const request = simulateRequest(route, scenario);

    // 1800 m at the 2 km/h planning speed is 3240 s: fixes at a third, a half and two thirds.
    expect(request).toEqual({
      site: "gale",
      path: route.path,
      fix_schedule: [
        { time_s: 1080, method: "horizon" },
        { time_s: 1620, method: "ground" },
        { time_s: 2160, method: "drone" },
      ],
      break_it: breakIt,
      seed: 1,
    });
  });
});

function step(mode: SimStep["mode"], events: SimStep["events"] = [], y = 0, uncertainty_m = 1): SimStep {
  return {
    t_s: y * 1.8,
    true_position: { x: 0, y },
    estimated_position: { x: 0, y },
    uncertainty_m,
    confidence_pct: 95,
    sources: ["motion_sensor", "step_count", "sun"],
    events,
    mode,
  };
}

const run = (...steps: SimulateResponse["steps"]): SimulateResponse => ({
  site: "gale",
  simulated: true,
  seed: 1,
  steps,
});

describe("walkBadges", () => {
  it("says Camera off from the moment the camera is lost", () => {
    const cameraOff = run(step("normal", [{ kind: "camera_off" }]), step("normal", [], 100));

    expect(walkBadges(cameraOff, 1).map((badge) => badge.label)).toEqual(["Camera off"]);
  });

  it("says Offline mode while the radio link is down", () => {
    const radioOff = run(step("offline", [{ kind: "radio_off" }]), step("offline", [], 100));

    expect(walkBadges(radioOff, 1).map((badge) => badge.label)).toEqual(["Offline mode"]);
  });

  it("adds Lost mode once everything at once has run the circle past the fix request", () => {
    const everything = run(
      step("offline", [{ kind: "camera_off" }, { kind: "radio_off" }, { kind: "drone_grounded" }]),
      step("lost", [{ kind: "lost_mode" }], 1200, 10),
    );

    expect(walkBadges(everything, 0).map((badge) => badge.label)).toEqual(["Camera off", "Offline mode"]);
    expect(walkBadges(everything, 1).map((badge) => badge.label)).toEqual([
      "Camera off",
      "Offline mode",
      "Lost mode",
    ]);
  });

  it("gives a grounded drone no badge: its fixes are greyed out on the timeline instead", () => {
    const grounded = run(step("normal", [{ kind: "drone_grounded" }]));

    expect(walkBadges(grounded, 0)).toEqual([]);
  });
});

const everything = run(
  step("offline", [{ kind: "camera_off" }, { kind: "radio_off" }, { kind: "drone_grounded" }]),
  step("offline", [], 600, 6),
  step("lost", [{ kind: "lost_mode" }], 1200, 10),
  step("lost", [], 1500, 12),
);

describe("lostModeStart", () => {
  it("is the estimate where lost mode began: the last known position and its circle", () => {
    expect(lostModeStart(everything)).toEqual({
      index: 2,
      t_s: 2160,
      position: { x: 0, y: 1200 },
      uncertainty_m: 10,
    });
  });

  it("is null for a walk that never gets lost", () => {
    expect(lostModeStart(run(step("normal"), step("offline", [], 100)))).toBeNull();
  });
});

describe("returnRequest", () => {
  const planned: RouteRequest = {
    site: "gale",
    start: { x: 0, y: 0 },
    goal: { x: 900, y: 900 },
    mode: "science",
    uncertainty_m: 0,
    limits: { max_slope_deg: 15, max_distance_from_habitat_m: 2000, planning_speed_kmh: 2, max_walk_h: 6 },
  };

  it("plans the fastest safe walk from the last known position back to the start, its hazard margin the circle", () => {
    // 2160 s out is 0.6 h of the 6 h walk-time limit (exit to re-entry), so 5.4 h are left.
    const lastKnown = { index: 2, t_s: 2160, position: { x: 0, y: 1200 }, uncertainty_m: 10 };

    expect(returnRequest(planned, lastKnown)).toEqual({
      site: "gale",
      start: { x: 0, y: 1200 },
      goal: { x: 0, y: 0 },
      mode: "fastest",
      uncertainty_m: 10,
      limits: { max_slope_deg: 15, max_distance_from_habitat_m: 2000, planning_speed_kmh: 2, max_walk_h: 5.4 },
    });
  });

  it("leaves the walk back one second when the walk-time limit is already spent, so the engine refuses it", () => {
    const late = { index: 9, t_s: 6.5 * 3600, position: { x: 0, y: 1200 }, uncertainty_m: 10 };

    expect(returnRequest(planned, late).limits.max_walk_h).toBe(1 / 3600);
  });
});

describe("returnHeading", () => {
  it("points at the first bend of the way back at least 20 m off, not the first grid step", () => {
    // The 5 m step due north is noise; (20, 20) is 28 m away at 045°.
    const path = [
      { x: 0, y: 0 },
      { x: 0, y: 5 },
      { x: 20, y: 20 },
      { x: 20, y: 400 },
    ];

    expect(returnHeading(path)).toBeCloseTo(45, 9);
  });

  it("points at the end of a way back shorter than 20 m", () => {
    expect(returnHeading([{ x: 0, y: 0 }, { x: 10, y: 0 }])).toBeCloseTo(90, 9);
  });
});

describe("landmarkDirection for the walk back", () => {
  // From (0, 400) on the first leg: the peak is due east, Texoli due south and the rim's
  // two points 2.9° either side of due north, so the rim lies due north.
  const landmarks = [
    { id: "peak", in_sentence: "the upper Mount Sharp peak", points: [{ x: 10000, y: 400 }] },
    { id: "texoli", in_sentence: "Texoli", points: [{ x: 0, y: -10000 }] },
    {
      id: "rim",
      in_sentence: "the Gale crater rim",
      points: [
        { x: -1000, y: 20000 },
        { x: 1000, y: 20000 },
      ],
    },
  ];
  const seen = (peak: number, texoli: number, rim: number) => [
    { id: "peak", share_of_leg_in_view: peak },
    { id: "texoli", share_of_leg_in_view: texoli },
    { id: "rim", share_of_leg_in_view: rim },
  ];
  const directions = (first: ReturnType<typeof seen>) => ({
    path: route.path,
    landmarks,
    legs: [
      { leg: 0, start_index: 0, end_index: 1, landmarks: first },
      { leg: 1, start_index: 1, end_index: 2, landmarks: seen(0, 0, 0) },
    ],
  });
  const at = { x: 3, y: 400 };
  const south = 180;

  it("puts the first landmark in view from half the leg on the side it lies walking back", () => {
    // Walking south, due east is on the left.
    expect(landmarkDirection(directions(seen(0.5, 1, 1)), route, at, south)).toEqual({
      kind: "landmark",
      leg: 0,
      legs: 2,
      text: "Keep the upper Mount Sharp peak on your left",
    });
  });

  it("walks towards a landmark ahead, skipping one seen from less than half the leg", () => {
    expect(landmarkDirection(directions(seen(0.49, 0.9, 1)), route, at, south)).toEqual({
      kind: "landmark",
      leg: 0,
      legs: 2,
      text: "Walk towards Texoli",
    });
  });

  it("keeps a landmark of several points behind, at the mean of their headings", () => {
    expect(landmarkDirection(directions(seen(0, 0, 0.6)), route, at, south)).toEqual({
      kind: "landmark",
      leg: 0,
      legs: 2,
      text: "Keep the Gale crater rim behind you",
    });
  });

  it("says no landmark is in view when layer 5 saw none from half the leg", () => {
    // 5 m north of the second leg, nearer it than the first.
    expect(landmarkDirection(directions(seen(1, 1, 1)), route, { x: 600, y: 905 }, 270)).toEqual({
      kind: "none-in-view",
      leg: 1,
      legs: 2,
    });
  });

  it("says layer 5 has no directions when its legs follow another route", () => {
    const other = { ...directions(seen(1, 1, 1)), path: [{ x: 0, y: 0 }, { x: 0, y: 900 }, { x: 900, y: 901 }] };

    expect(landmarkDirection(other, route, at, south)).toEqual({ kind: "not-this-route" });
    expect(landmarkDirection(null, route, at, south)).toEqual({ kind: "not-this-route" });
  });
});
