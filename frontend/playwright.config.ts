import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "list",
  use: {
    baseURL: "http://localhost:3000",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command:
        "../backend/.venv/bin/uvicorn app.main:app --app-dir ../backend --host 127.0.0.1 --port 8000",
      url: "http://localhost:8000/api/health",
      reuseExistingServer: true,
      timeout: 30_000,
      env: {
        DATABASE_URL: "sqlite://",
        APP_ENV: "development",
        AI_PROVIDER: "disabled",
        REAL_DATA_MODE_ENABLED: "true",
        AUTH_MODE: "development",
        SESSION_HMAC_SECRET: "playwright-session-secret-at-least-32-characters",
        DATA_ENCRYPTION_KEY: "VFRUVFRUVFRUVFRUVFRUVFRUVFRUVFRUVFRUVFRUVFQ=",
      },
    },
    {
      command: "npm run dev -- --hostname 127.0.0.1 --port 3000",
      url: "http://localhost:3000",
      reuseExistingServer: true,
      timeout: 30_000,
    },
  ],
});
