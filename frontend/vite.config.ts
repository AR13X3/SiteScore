import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev (`python run.py dev`) Vite serves the UI and proxies /api to FastAPI.
// In production (`python run.py start`) FastAPI serves the built dist/ folder.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  build: { outDir: "dist", chunkSizeWarningLimit: 1200 },
});
