import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the phone app runs on :5173 and forwards /api to the FastAPI server on :8000.
// In production FastAPI serves the built app (frontend/dist) itself, so both share one address.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://localhost:8000" } },
});
