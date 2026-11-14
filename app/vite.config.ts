import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  // The demo cache lives in the repo's cache/demo/, and layer 5's landmark directions in
  // layers/location_quality/, both outside app/.
  server: { fs: { allow: [".", "../cache", "../layers/location_quality"] } },
});
