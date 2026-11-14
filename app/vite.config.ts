import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  // The demo cache (cache/demo/) and the cited benchmarks (pitch/) live outside app/.
  server: { fs: { allow: [".", "../cache", "../pitch"] } },
});
