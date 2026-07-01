import path from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    port: 5173,
    proxy: { "/api": "http://localhost:8000" },
  },
  build: {
    // build straight into the backend so one container serves everything
    outDir: "../backend/app/static",
    emptyOutDir: true,
  },
});
