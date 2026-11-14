import type { Conditions } from "@contracts/conditions";
import type { RouteResponse } from "@contracts/route_response";
import type { SimStep, SimulateResponse } from "@contracts/simulate_response";
import { describe, expect, it } from "vitest";
import { conditionsAt } from "./conditions";
import { fixEvents, indexAtTime, walkStatus } from "./playback";
import { fixSchedule, simulateRequest } from "./schedule";

// A straight 1800 m walk due north, with one checkpoint halfway.
const route: RouteResponse = {
  site: "gale",
  mode: "fastest",
  path: [
    { x: 0, y: 0 },
    { x: 0, y: 900 },
    { x: 0, y: 1800 },
  ],
  legs: [{ start_index: 0, end_index: 2, distance_m: 1800, time_s: 3240 }],
  total_distance_m: 1800,
  total_time_s: 3240,
  walk_back_margin_s: 3600,
  extra_time_vs_fastest_s: null,
  limit_checks: [{ limit: "slope", passed: true, value: 4, threshold: 20, units: "deg" }],
  checkpoints: [{ id: "cp-1", position: { x: 0, y: 900 } }],
};

describe("fixSchedule", () => {
  it("puts a horizon fix at a third, a ground fix halfway and a drone fix at two thirds", () => {
    // 1800 m at the 2 km/h planning speed is 3240 s of walking.
    expect(fixSchedule(route)).toEqual([
      { time_s: 1080, method: "horizon" },
      { time_s: 1620, method: "ground" },
      { time_s: 2160, method: "drone" },
    ]);
  });

  it("asks for the walk along the route with no break-it scenario", () => {
    expect(simulateRequest(route)).toEqual({
      site: "gale",
      path: route.path,
      fix_schedule: [
        { time_s: 1080, method: "horizon" },
        { time_s: 1620, method: "ground" },
        { time_s: 2160, method: "drone" },
      ],
      break_it: { camera_off: false, radio_off: false, drone_grounded: false },
      seed: 1,
    });
  });
});

function step(t_s: number, y: number, uncertainty_m: number, events: SimStep["events"] = []): SimStep {
  return {
    t_s,
    true_position: { x: 0, y },
    estimated_position: { x: 0, y },
    uncertainty_m,
    confidence_pct: 95,
    sources: ["visual_odometry", "motion_sensor", "step_count", "sun"],
    events,
    mode: "normal",
  };
}

const simulation: SimulateResponse = {
  site: "gale",
  simulated: true,
  seed: 1,
  steps: [
    step(0, 0, 0.5),
    step(1080, 600, 12, [{ kind: "fix_requested" }]),
    step(1080, 600, 3, [{ kind: "fix", method: "horizon" }]),
    step(2160, 1200, 8),
    step(2160, 1200, 2, [{ kind: "fix", method: "drone" }]),
    step(3240, 1800, 4),
  ],
};

describe("walkStatus", () => {
  it("reads the walk at one step: circle, time and distance left, the next waypoint", () => {
    expect(walkStatus(simulation, 1, route, "Ridge centre")).toEqual({
      t_s: 1080,
      position: { x: 0, y: 600 },
      uncertainty_m: 12,
      confidence_pct: 95,
      level: "over",
      timeLeft_s: 2160,
      distanceLeft_m: 1200,
      instruction: "Head 000° to checkpoint 1",
      waypointBearing: 0,
      waypointDistance_m: 300,
      simulated: true,
    });
  });

  it("shows the circle shrinking at the fix, and heads for the target after the last checkpoint", () => {
    const status = walkStatus(simulation, 4, route, "Ridge centre");

    expect([status.uncertainty_m, status.level, status.instruction, status.waypointDistance_m]).toEqual([
      2,
      "sure",
      "Head 000° to Ridge centre",
      600,
    ]);
  });

  it("marks a circle between 5 m and the 10 m fix request as check", () => {
    expect(walkStatus(simulation, 3, route, "Ridge centre").level).toBe("check");
  });
});

describe("fixEvents", () => {
  it("lists every fix and fix request with where it falls on the timeline", () => {
    expect(fixEvents(simulation)).toEqual([
      { index: 1, t_s: 1080, fraction: 1 / 3, kind: "fix_requested", method: null, buddy: false },
      { index: 2, t_s: 1080, fraction: 1 / 3, kind: "fix", method: "horizon", buddy: false },
      { index: 4, t_s: 2160, fraction: 2 / 3, kind: "fix", method: "drone", buddy: false },
    ]);
  });

  it("adds the fixes that can't reach the crew, the buddy's camera fixes and the start of lost mode", () => {
    const broken: SimulateResponse = {
      ...simulation,
      steps: [
        step(0, 0, 0.5, [{ kind: "camera_off" }, { kind: "drone_grounded" }]),
        step(1080, 600, 3, [{ kind: "fix", method: "horizon" }, { kind: "buddy_camera" }]),
        step(2160, 1200, 9, [{ kind: "fix_unavailable", method: "drone" }]),
        step(2700, 1500, 10, [{ kind: "lost_mode" }]),
        step(3240, 1800, 12),
      ],
    };

    expect(fixEvents(broken)).toEqual([
      { index: 1, t_s: 1080, fraction: 1 / 3, kind: "fix", method: "horizon", buddy: true },
      { index: 2, t_s: 2160, fraction: 2 / 3, kind: "fix_unavailable", method: "drone", buddy: false },
      { index: 3, t_s: 2700, fraction: 2700 / 3240, kind: "lost_mode", method: null, buddy: false },
    ]);
  });
});

describe("indexAtTime", () => {
  it("finds the step at a time in another run, after the fix when one falls there", () => {
    // Steps at 0, 1080, 1080 (the fix), 2160, 2160 (the fix), 3240 s.
    expect([0, 1080, 1500, 2160, 9999].map((t_s) => indexAtTime(simulation, t_s))).toEqual([
      0, 2, 2, 4, 5,
    ]);
  });
});

const conditions: Conditions = {
  site: "gale",
  sol: 4600,
  radiation_ugy_per_day: 160.56,
  dust: { optical_depth: 0.5, source: "estimated" },
  sunset_lmst: "17:30",
  steps: [
    { lmst: "05:00", temperature_c: -82, pressure_pa: 760, sun_azimuth_deg: 70, sun_elevation_deg: -3 },
    { lmst: "06:00", temperature_c: -79.7, pressure_pa: 755, sun_azimuth_deg: 66, sun_elevation_deg: 2.6 },
    { lmst: "07:00", temperature_c: -61.2, pressure_pa: 752, sun_azimuth_deg: 62, sun_elevation_deg: 15 },
  ],
  provenance: { script: "conditions/gen_conditions.py", commit: "abc", inputs: [] },
};

describe("conditionsAt", () => {
  it("starts the walk at first light and reads the strip at that hour", () => {
    expect(conditionsAt(conditions, 0)).toEqual({
      lmst: "06:00",
      temperature: "-80 °C",
      radiation: "161 µGy/day",
      dust: "τ 0.5",
      dustSource: "estimated",
      sunsetIn: "11 h 30 min",
    });
  });

  it("moves the local time on in Mars hours as the walk goes", () => {
    // 1.5 Mars hours = 1.5 x 88775.244 / 24 = 5548.45 s, so 06:00 becomes 07:30.
    const later = conditionsAt(conditions, 5548.45);

    expect([later.lmst, later.temperature, later.sunsetIn]).toEqual(["07:30", "-61 °C", "10 h"]);
  });
});
