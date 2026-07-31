import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
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
