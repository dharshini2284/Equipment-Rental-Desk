import { defineConfig, devices } from "@playwright/test";

// Browser tests against a running stack. They expect freshly seeded data:
//   backend:  python -m app.seed --reset && uvicorn app.main:app --port 8000
//   frontend: npm run dev            (or set E2E_BASE_URL to another UI)
// PW_CHANNEL=msedge uses the installed Edge instead of Playwright's own Chromium.
export default defineConfig({
  testDir: "e2e",
  // The scenarios change shared data (loans, payments), so they run one after another.
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:5173",
    channel: process.env.PW_CHANNEL || undefined,
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "desktop",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1366, height: 900 } },
    },
  ],
});
