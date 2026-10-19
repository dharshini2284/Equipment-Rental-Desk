/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

// In development the UI calls the API on the same origin and Vite forwards /api to the
// backend, so no API URL needs to be configured locally. Production builds set
// VITE_API_BASE_URL instead (see .env.example).
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  const proxyTarget = env.DEV_API_PROXY_TARGET || "http://localhost:8000";
  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: { "/api": proxyTarget, "/health": proxyTarget },
    },
    // Unit tests only; the browser tests in e2e/ run with Playwright.
    test: { environment: "node", include: ["src/**/*.test.ts"] },
  };
});
