import type { DemoCacheEntry } from "@contracts/demo_cache";
import type { RouteRequest } from "@contracts/route_request";
import { describe, expect, it, vi } from "vitest";
import { ApiError, createClient, DemoCacheMiss } from "./client";
import { demoCache } from "./demoCache";

const routeRequest: RouteRequest = {
  site: "gale",
  start: { x: 1, y: 2 },
  goal: { x: 3, y: 4 },
  mode: "fastest",
  uncertainty_m: 5,
  limits: {
    max_slope_deg: 20,
    max_distance_from_habitat_m: 2000,
    planning_speed_kmh: 2,
    max_walk_h: 6,
  },
};

const cache: DemoCacheEntry[] = [
  {
    step: "planning.route.fastest",
    request: { method: "POST", path: "/route", body: { ...routeRequest } },
    status: 200,
    contract: "route_response",
    response: { total_time_s: 1800 },
  },
  {
    step: "walk.conditions",
    request: { method: "GET", path: "/conditions/4600", body: null },
    status: 200,
    contract: "conditions",
    response: { sol: 4600 },
  },
  {
    step: "lab.missing-photo",
    request: { method: "GET", path: "/fixes/horizon/nope", body: null },
    status: 404,
    contract: null,
    response: { detail: "no such file" },
  },
];

function fakeFetch(status: number, body: unknown) {
  return vi.fn(async () => new Response(JSON.stringify(body), { status }));
}

describe("live mode", () => {
  it("calls the service and tags the request with its demo step", async () => {
    const fetchFn = fakeFetch(200, { total_time_s: 1800 });
    const client = createClient({ mode: "live", baseUrl: "http://svc", cache: [], fetchFn });

    const answer = await client.route("planning.route.fastest", routeRequest);

    expect(answer).toEqual({ total_time_s: 1800 });
    expect(fetchFn).toHaveBeenCalledWith("http://svc/route", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Demo-Step": "planning.route.fastest" },
      body: JSON.stringify(routeRequest),
    });
  });

  it("sends GETs without a body", async () => {
    const fetchFn = fakeFetch(200, { sol: 4600 });
    const client = createClient({ mode: "live", baseUrl: "http://svc", cache: [], fetchFn });

    await client.conditions("walk.conditions", "4600");

    expect(fetchFn).toHaveBeenCalledWith("http://svc/conditions/4600", {
      method: "GET",
      headers: { "Content-Type": "application/json", "X-Demo-Step": "walk.conditions" },
    });
  });

  it("turns an error status into an ApiError", async () => {
    const fetchFn = fakeFetch(404, { detail: "no such file" });
    const client = createClient({ mode: "live", baseUrl: "http://svc", cache: [], fetchFn });

    await expect(client.fix("lab.photo", "horizon", "nope")).rejects.toEqual(
      new ApiError(404, "lab.photo", { detail: "no such file" }),
    );
  });

  it("keeps a non-JSON error body as text", async () => {
    const fetchFn = vi.fn(async () => new Response("Bad gateway", { status: 502 }));
    const client = createClient({ mode: "live", baseUrl: "http://svc", cache: [], fetchFn });

    await expect(client.summaries("lab.chart")).rejects.toEqual(
      new ApiError(502, "lab.chart", "Bad gateway"),
    );
  });
});

describe("demo mode", () => {
  it("answers each cached step from the cache and never touches the network", async () => {
    const fetchFn = fakeFetch(500, {});
    const client = createClient({ mode: "demo", baseUrl: "http://svc", cache, fetchFn });

    expect(await client.route("planning.route.fastest", routeRequest)).toEqual({
      total_time_s: 1800,
    });
    expect(await client.conditions("walk.conditions", "4600")).toEqual({ sol: 4600 });
    expect(fetchFn).not.toHaveBeenCalled();
  });

  it("fails loudly on a step that was never recorded", async () => {
    const fetchFn = fakeFetch(200, {});
    const client = createClient({ mode: "demo", baseUrl: "http://svc", cache, fetchFn });

    await expect(client.conditions("walk.unknown", "4600")).rejects.toThrow(DemoCacheMiss);
    expect(fetchFn).not.toHaveBeenCalled();
  });

  it("fails loudly when the step was recorded for a different request", async () => {
    const client = createClient({ mode: "demo", baseUrl: "http://svc", cache });
    const steeper = { ...routeRequest, limits: { ...routeRequest.limits, max_slope_deg: 15 } };

    await expect(client.route("planning.route.fastest", steeper)).rejects.toThrow(
      "planning.route.fastest was recorded for POST /route with a different body",
    );
  });

  it("replays a recorded error as an ApiError", async () => {
    const client = createClient({ mode: "demo", baseUrl: "http://svc", cache });

    await expect(client.fix("lab.missing-photo", "horizon", "nope")).rejects.toEqual(
      new ApiError(404, "lab.missing-photo", { detail: "no such file" }),
    );
  });

  it("replays every step saved in the repo's demo cache exactly", async () => {
    const fetchFn = fakeFetch(500, {});
    const client = createClient({ mode: "demo", baseUrl: "http://svc", cache: demoCache, fetchFn });

    expect(demoCache.length).toBeGreaterThan(0);
    for (const entry of demoCache) {
      const { method, path, body } = entry.request;
      const replay = client.call(entry.step, method, path, body);
      if (entry.status >= 400) {
        await expect(replay).rejects.toEqual(new ApiError(entry.status, entry.step, entry.response));
      } else {
        expect(await replay).toEqual(entry.response);
      }
    }
    expect(fetchFn).not.toHaveBeenCalled();
  });
});
