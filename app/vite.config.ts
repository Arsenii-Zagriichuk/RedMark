import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  // The demo cache lives in the repo's cache/demo/, outside app/.
  server: { fs: { allow: [".", "../cache"] } },
});
