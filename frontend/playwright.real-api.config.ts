import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "financial-review-real-api.spec.ts",
  workers: 1,
  timeout: 60000,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:5179",
    ...devices["Desktop Chrome"],
    channel: process.env.PLAYWRIGHT_CHANNEL as "chrome" | undefined,
    trace: "retain-on-failure",
  },
  webServer: {
    command: "npm run dev -- --port 5179 --strictPort",
    url: "http://127.0.0.1:5179",
    reuseExistingServer: false,
    env: { VITE_API_BASE_URL: "http://127.0.0.1:8019" },
  },
});
