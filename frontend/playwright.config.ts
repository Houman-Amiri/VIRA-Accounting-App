/**
 * Playwright — end-to-end smoke for the V.I.R.A SPA (Persian RTL).
 * Run: pnpm e2e (requires `playwright install chromium`).
 */
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  use: {
    baseURL: process.env.VIRA_E2E_BASE_URL || "http://127.0.0.1:5173",
    locale: "fa-IR",
    timezoneId: "Asia/Tehran",
    viewport: { width: 1440, height: 900 },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "cd .. && .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8787",
      url: "http://127.0.0.1:8787/api/v1/health/live",
      reuseExistingServer: true,
      timeout: 120_000,
    },
    {
      command: "pnpm dev",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: true,
      timeout: 120_000,
    },
  ],
});
