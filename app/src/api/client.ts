// The one module that reaches the service (P1-02). oxlint bans `fetch` everywhere else,
// so demo mode can't be bypassed. Live mode calls the service and tags each call with its
// demo step, so the service can record it. Demo mode answers every step from the demo
// cache and never touches the network.
import type { Conditions } from "@contracts/conditions";
import type { DemoCacheEntry } from "@contracts/demo_cache";
import type { FixResult } from "@contracts/fix_result";
import type { LayerMeta } from "@contracts/layer";
import type { RouteRequest } from "@contracts/route_request";
import type { RouteResponse } from "@contracts/route_response";
import type { SimulateRequest } from "@contracts/simulate_request";
import type { SimulateResponse } from "@contracts/simulate_response";
import type { TestSummary } from "@contracts/test_summary";

export type Mode = "live" | "demo";
type HttpMethod = DemoCacheEntry["request"]["method"];
type Body = DemoCacheEntry["request"]["body"];

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly step: string,
    readonly body: unknown,
  ) {
    super(`${step}: the service answered ${status}`);
    this.name = "ApiError";
  }
}

export class DemoCacheMiss extends Error {
  constructor(message: string) {
    super(message);
    this.name = "DemoCacheMiss";
  }
}

export interface ClientOptions {
  mode: Mode;
  baseUrl: string;
  cache: readonly DemoCacheEntry[];
  fetchFn?: typeof fetch;
}

/** JSON with object keys in a fixed order, so equal requests compare equal. */
function canonical(value: unknown): string {
  return JSON.stringify(value, (_key, inner: unknown) =>
    inner && typeof inner === "object" && !Array.isArray(inner)
      ? Object.fromEntries(Object.entries(inner).sort(([a], [b]) => a.localeCompare(b)))
      : inner,
  );
}

export function createClient({ mode, baseUrl, cache, fetchFn = fetch }: ClientOptions) {
  async function fromCache(step: string, method: HttpMethod, path: string, body: Body) {
    const entry = cache.find((candidate) => candidate.step === step);
    if (!entry) throw new DemoCacheMiss(`${step} is not in the demo cache`);
    const recorded = entry.request;
    if (recorded.method !== method || recorded.path !== path) {
      throw new DemoCacheMiss(`${step} was recorded for ${recorded.method} ${recorded.path}`);
    }
    if (canonical(recorded.body) !== canonical(body)) {
      throw new DemoCacheMiss(`${step} was recorded for ${method} ${path} with a different body`);
    }
    if (entry.status >= 400) throw new ApiError(entry.status, step, entry.response);
    return entry.response;
  }

  async function fromService(step: string, method: HttpMethod, path: string, body: Body) {
    const response = await fetchFn(`${baseUrl}${path}`, {
      method,
      headers: { "Content-Type": "application/json", "X-Demo-Step": step },
      ...(body === null ? {} : { body: JSON.stringify(body) }),
    });
    if (!response.ok) {
      const text = await response.text();
      let detail: unknown = text;
      try {
        detail = JSON.parse(text);
      } catch {
        // Not JSON, such as a proxy's error page: keep the text.
      }
      throw new ApiError(response.status, step, detail);
    }
    return (await response.json()) as unknown;
  }

  /** One call to the service, by demo step id; typed helpers below wrap it. */
  async function call(step: string, method: HttpMethod, path: string, body: Body = null) {
    return mode === "demo"
      ? fromCache(step, method, path, body)
      : fromService(step, method, path, body);
  }

  const get = async <T>(step: string, path: string) => (await call(step, "GET", path)) as T;
  const post = async <T>(step: string, path: string, body: object) =>
    (await call(step, "POST", path, { ...body })) as T;

  return {
    mode,
    call,
    layers: (step: string, site: string) => get<LayerMeta[]>(step, `/layers/${site}`),
    conditions: (step: string, sol: string) => get<Conditions>(step, `/conditions/${sol}`),
    fixes: (step: string, method: string) => get<FixResult[]>(step, `/fixes/${method}`),
    fix: (step: string, method: string, photoId: string) =>
      get<FixResult>(step, `/fixes/${method}/${photoId}`),
    summaries: (step: string) => get<TestSummary[]>(step, "/summaries"),
    summary: (step: string, method: string, test: string) =>
      get<TestSummary>(step, `/summaries/${method}/${test}`),
    route: (step: string, request: RouteRequest) => post<RouteResponse>(step, "/route", request),
    simulate: (step: string, request: SimulateRequest) =>
      post<SimulateResponse>(step, "/simulate", request),
  };
}

export type ApiClient = ReturnType<typeof createClient>;
