// Layer 5's lost-mode landmark directions (P3-06), bundled into the app at build time like
// the demo cache, so lost mode works with the network off. Person 3's build writes them to
// layers/location_quality/layer5-<site>.json for the legs of one saved route in the demo
// cache, which it names; a re-recorded route only needs that build rerun.
import type { DemoCacheEntry } from "@contracts/demo_cache";
import type { RouteResponse } from "@contracts/route_response";
import type { LandmarkDirections } from "./lost";

/** The part of layer5-<site>.json the app reads; the file itself is not a contract. */
interface Layer5File {
  site: string;
  landmark_directions: {
    /** The saved route the legs follow, from the repo root. */
    route: string;
    legs: LandmarkDirections["legs"];
  };
}

const layers = import.meta.glob<Layer5File>("../../../layers/location_quality/layer5-*.json", {
  eager: true,
  import: "default",
});
const routes = import.meta.glob<DemoCacheEntry>("../../../cache/demo/route/*.json", {
  eager: true,
  import: "default",
});

export function landmarkDirectionsFor(site: string): LandmarkDirections | null {
  const file = Object.values(layers).find((layer) => layer.site === site);
  if (!file) return null;
  const saved = routes[`../../../${file.landmark_directions.route}`];
  if (!saved) return null;
  return { path: (saved.response as unknown as RouteResponse).path, legs: file.landmark_directions.legs };
}
