import type { RouteResponse } from "@contracts/route_response";
import type { SiteConfig } from "@contracts/site";
import { describe, expect, it } from "vitest";
import { limitRows, routeRequests } from "./routes";

const site: SiteConfig = {
  site: "gale",
  name: "Gale",
  projection: "+proj=eqc +R=3396190",
  bounds: { min_x: 0, min_y: 0, max_x: 4000, max_y: 4000 },
  habitat: { x: 2000, y: 2000 },
  base_camp: { x: 1600, y: 1740 },
  science_targets: [{ id: "ridge-1", name: "Ridge centre", position: { x: 2800, y: 2640 } }],
  checkpoints: [],
  files: {},
  replayed_sol: 4600,
};
const target = site.science_targets[0]!;
const artemis20 = {
  max_slope_deg: 20,
  max_distance_from_habitat_m: 2000,
  planning_speed_kmh: 2,
  max_walk_h: 6,
};

describe("routeRequests", () => {
  it("asks for the walk from base camp to the target, and the cart's trip to base camp", () => {
    expect(routeRequests(site, target, 20)).toEqual({
      fastest: {
        site: "gale",
        start: { x: 1600, y: 1740 },
        goal: { x: 2800, y: 2640 },
        mode: "fastest",
        uncertainty_m: 0,
        limits: artemis20,
      },
      science: {
        site: "gale",
        start: { x: 1600, y: 1740 },
        goal: { x: 2800, y: 2640 },
        mode: "science",
        uncertainty_m: 0,
        limits: artemis20,
      },
      cart: {
        site: "gale",
        start: { x: 2000, y: 2000 },
        goal: { x: 1600, y: 1740 },
        mode: "cart",
        uncertainty_m: 0,
        limits: artemis20,
      },
    });
  });

  it("puts the 15° slope limit into all three requests", () => {
    const requests = routeRequests(site, target, 15);

    expect([
      requests.fastest?.limits.max_slope_deg,
      requests.science?.limits.max_slope_deg,
      requests.cart?.limits.max_slope_deg,
    ]).toEqual([15, 15, 15]);
  });

  it("starts the walk at the habitat when the site has no base camp, and asks for no cart route", () => {
    const requests = routeRequests({ ...site, base_camp: null }, target, 20);

    expect(requests.fastest?.start).toEqual({ x: 2000, y: 2000 });
    expect(requests.cart).toBeNull();
  });
});

function response(checks: RouteResponse["limit_checks"]): RouteResponse {
  return {
    site: "gale",
    mode: "fastest",
    path: [
      { x: 1600, y: 1740 },
      { x: 2800, y: 2640 },
    ],
    legs: [{ start_index: 0, end_index: 1, distance_m: 2410, time_s: 7800 }],
    total_distance_m: 2410,
    total_time_s: 7800,
    walk_back_margin_s: 3480,
    extra_time_vs_fastest_s: null,
    limit_checks: checks,
    checkpoints: [],
  };
}

describe("limitRows", () => {
  it("lists all seven limits in order, with each value against its limit", () => {
    const rows = limitRows(
      response([
        { limit: "slope", passed: true, value: 18, threshold: 20, units: "deg" },
        { limit: "distance_from_habitat", passed: true, value: 1210, threshold: 2000, units: "m" },
        { limit: "planning_speed", passed: true, value: 2, threshold: 2, units: "km/h" },
        { limit: "walk_time", passed: true, value: 2.1666, threshold: 6, units: "h" },
        { limit: "walk_back", passed: true, value: 3480, threshold: 0, units: "s" },
        { limit: "daylight", passed: true, value: 7500, threshold: 0, units: "s" },
        { limit: "hazard_margin", passed: false, value: 40, threshold: 50, units: "m" },
      ]),
    );

    expect(rows).toEqual([
      { limit: "slope", label: "Slope", text: "18° / 20° max", status: "pass" },
      { limit: "distance_from_habitat", label: "From habitat", text: "1.21 km / 2 km", status: "pass" },
      { limit: "planning_speed", label: "Planning speed", text: "2 km/h / 2 km/h", status: "pass" },
      { limit: "walk_time", label: "Walk time", text: "2 h 10 min / 6 h", status: "pass" },
      { limit: "walk_back", label: "Walk-back margin", text: "58 min spare", status: "pass" },
      { limit: "daylight", label: "Daylight", text: "2 h 5 min spare", status: "pass" },
      { limit: "hazard_margin", label: "Hazard margin", text: "40 m / 50 m min", status: "fail" },
    ]);
  });

  it("says how far short a broken walk-back rule falls", () => {
    const rows = limitRows(
      response([{ limit: "walk_back", passed: false, value: -300, threshold: 0, units: "s" }]),
    );

    expect(rows.find((row) => row.limit === "walk_back")).toEqual({
      limit: "walk_back",
      label: "Walk-back margin",
      text: "5 min short",
      status: "fail",
    });
  });

  it("marks a limit the route didn't check as not checked", () => {
    const rows = limitRows(
      response([{ limit: "slope", passed: true, value: 0, threshold: 15, units: "deg" }]),
    );

    expect(rows.map((row) => [row.limit, row.status, row.text])).toEqual([
      ["slope", "pass", "0° / 15° max"],
      ["distance_from_habitat", "not-checked", "not checked"],
      ["planning_speed", "not-checked", "not checked"],
      ["walk_time", "not-checked", "not checked"],
      ["walk_back", "not-checked", "not checked"],
      ["daylight", "not-checked", "not checked"],
      ["hazard_margin", "not-checked", "not checked"],
    ]);
  });
});
