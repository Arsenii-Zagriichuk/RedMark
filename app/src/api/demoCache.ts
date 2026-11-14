// Every saved demo step in cache/demo/, bundled into the app at build time, so demo mode
// runs with the network off and the service down.
import type { DemoCacheEntry } from "@contracts/demo_cache";

const files = import.meta.glob<DemoCacheEntry>("../../../cache/demo/*/*.json", {
  eager: true,
  import: "default",
});

export const demoCache: readonly DemoCacheEntry[] = Object.values(files);
