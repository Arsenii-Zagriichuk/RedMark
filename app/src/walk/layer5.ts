// Layer 5's lost-mode landmark data (P3-06), bundled into the app at build time like the
// demo cache, so lost mode works with the network off. Person 3's build writes it to
// layers/location_quality/layer5-<site>.json for the legs of one saved route in the demo
// cache, which it names; a re-recorded route only needs that build rerun. How a direction
// names each landmark mid-sentence is in landmarks.yaml, next to it.
import type { DemoCacheEntry } from "@contracts/demo_cache";
import type { Point, RouteResponse } from "@contracts/route_response";
import type { LandmarkDirections } from "./lost";

/** The part of layer5-<site>.json the app reads; the file itself is not a contract. */
interface Layer5File {
  site: string;
  landmarks: { id: string; title: string; points: Point[] }[];
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
const landmarksYaml = Object.values(
  import.meta.glob<string>("../../../layers/location_quality/landmarks.yaml", {
    eager: true,
    query: "?raw",
    import: "default",
  }),
)[0];
const routes = import.meta.glob<DemoCacheEntry>("../../../cache/demo/route/*.json", {
  eager: true,
  import: "default",
});

/** Each landmark's in_sentence from landmarks.yaml; a landmark without one uses its title. */
function inSentenceNames(yaml: string): Map<string, string> {
  const names = new Map<string, string>();
  for (const block of yaml.split(/^\s*- id:\s*/m).slice(1)) {
    const id = block.split(/\s/, 1)[0];
    const name = /^\s*in_sentence:\s*(.+?)\s*$/m.exec(block)?.[1];
    if (id && name) names.set(id, name);
  }
  return names;
}

export function landmarkDirectionsFor(site: string): LandmarkDirections | null {
  const file = Object.values(layers).find((layer) => layer.site === site);
  if (!file) return null;
  const saved = routes[`../../../${file.landmark_directions.route}`];
  if (!saved) return null;
  const names = inSentenceNames(landmarksYaml ?? "");
  return {
    path: (saved.response as unknown as RouteResponse).path,
    landmarks: file.landmarks.map(({ id, title, points }) => ({
      id,
      in_sentence: names.get(id) ?? title,
      points,
    })),
    legs: file.landmark_directions.legs,
  };
}
