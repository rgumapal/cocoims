import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import pkg from "./package.json";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // Single source of truth for the version shown in the nav footer — read
  // from package.json at build time so bumping the version there is the
  // only step, with no second copy in the UI to forget.
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    proxy: {
      // Backend runs on 8010 in dev (8000 is often occupied by other local
      // projects on this machine — see backend/README.md).
      "/api": "http://127.0.0.1:8010",
    },
  },
});
