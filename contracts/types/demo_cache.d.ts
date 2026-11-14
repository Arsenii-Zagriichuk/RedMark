/* Generated from contracts/schemas by tools/gen_contracts.py. Do not edit by hand. */

/**
 * One saved response for one step of the 3-minute demo, in cache/demo/<producer>/<step>.json. Demo mode answers from these and never touches the network.
 */
export interface DemoCacheEntry {
  /**
   * Demo step id, e.g. planning.route.fastest.
   */
  step: string;
  request: CachedRequest;
  status: number;
  /**
   * Name of the schema in contracts/schemas the response matches (e.g. route_response); null if none.
   */
  contract: null | string;
  /**
   * The saved response body.
   */
  response: {
    [k: string]: unknown;
  };
}
/**
 * The request that produced the response.
 */
export interface CachedRequest {
  method: "GET" | "POST";
  /**
   * Service path, e.g. /route.
   */
  path: string;
  /**
   * Request body; null for GET.
   */
  body: null | {
    [k: string]: unknown;
  };
}
