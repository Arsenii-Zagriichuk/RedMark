// The Drone fix screen's data (P1-09): Person 2's simulated Gale drone fix (P2-07), saved in
// the demo cache as step drone.fix.gale, and its two images.
import type { FixResult } from "@contracts/fix_result";
import type { ApiClient, Mode } from "../api/client";

export const DRONE_FIX_STEP = "drone.fix.gale";
const DRONE_PHOTO_ID = "gale-sim-drone-0001";
/** The walk the drone fix sits on, as the Walk view keys it: base camp to the first science
 * target, fastest, 20° (cache/README.md). */
export const DRONE_FIX_WALK = "fastest.sw-ridge.20";

export function loadDroneFix(client: ApiClient): Promise<FixResult> {
  return client.fix(DRONE_FIX_STEP, "drone", DRONE_PHOTO_ID);
}

export interface DroneFixImages {
  /** P2-07's overlay sheet: the photo beside the map with its matched outline. */
  sheet: string;
  /** The drone photo alone, with the detected astronauts. */
  photo: string;
}

/** Static copies of P2-07's images in app/public/fallback/, for when the cache or the
 * service can't give them. Both are stamped SIMULATED. */
export const DRONE_FIX_FALLBACK: DroneFixImages = {
  sheet: "/fallback/drone-fix-sheet.png",
  photo: "/fallback/drone-fix-photo.png",
};

/** The demo cache's drone images (cache/demo/drone/overlays/), bundled, by file name. */
export const bundledDroneImages: Readonly<Record<string, string>> = Object.fromEntries(
  Object.entries(
    import.meta.glob<string>("../../../cache/demo/drone/overlays/*.png", {
      eager: true,
      query: "?url",
      import: "default",
    }),
  ).map(([path, url]) => [path.slice(path.lastIndexOf("/") + 1), url]),
);

/** gale_fix.py names the overlay `<photo id>-<matcher>-<run id>.png` and writes the photo
 * beside it as `<photo id>-photo-<run id>.png`. */
function photoPath(fix: FixResult): string {
  const folder = fix.overlay.slice(0, fix.overlay.lastIndexOf("/") + 1);
  const runId = fix.overlay.slice(fix.overlay.lastIndexOf("-") + 1);
  return `${folder}${fix.photo_id}-photo-${runId}`;
}

interface ImageSources {
  bundled: Readonly<Record<string, string>>;
  fileUrl: (path: string) => string;
}

export function droneFixImages(fix: FixResult, mode: Mode, sources: ImageSources): DroneFixImages {
  const paths = { sheet: fix.overlay, photo: photoPath(fix) };
  if (mode === "live") {
    return {
      sheet: sources.fileUrl(`/overlays/${paths.sheet}`),
      photo: sources.fileUrl(`/overlays/${paths.photo}`),
    };
  }
  const fromBundle = (path: string) => sources.bundled[path.slice(path.lastIndexOf("/") + 1)];
  return {
    sheet: fromBundle(paths.sheet) ?? DRONE_FIX_FALLBACK.sheet,
    photo: fromBundle(paths.photo) ?? DRONE_FIX_FALLBACK.photo,
  };
}
