import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  // The demo cache (cache/demo/), the cited benchmarks (pitch/) and layer 5's landmark
  // directions (layers/location_quality/) live outside app/.
  server: { fs: { allow: [".", "../cache", "../pitch", "../layers/location_quality"] } },
});
