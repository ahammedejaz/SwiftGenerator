import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "list",
  use: {
    // 127.0.0.1 everywhere, never `localhost`. The servers bind 127.0.0.1, but a browser
    // resolves `localhost` to ::1 first on a dual-stack machine and only then falls back —
    // so a request occasionally died with ECONNREFUSED ::1:8000 and a test unrelated to
    // networking failed with "the backend is down". macOS binds `--host ::` as IPv6-only,
    // so matching the address is the fix rather than listening on both.
    baseURL: "http://127.0.0.1:3000",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command:
        "../backend/.venv/bin/uvicorn app.main:app --app-dir ../backend --host 127.0.0.1 --port 8000",
      url: "http://127.0.0.1:8000/api/health",
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
        // The demonstration throttle is per process and the whole suite shares one, so
        // whether a run passes would depend on how many requests it happens to make — a
        // test that has nothing to do with throttling fails with a 429 once the suite grows
        // past 600 requests a minute. The throttle itself is still tested, in
        // backend/tests/security/test_cors_and_throttling.py, which installs its own limiter.
        RATE_LIMIT_REQUESTS_PER_MINUTE: "1000000",
      },
    },
    {
      command: "npm run dev -- --hostname 127.0.0.1 --port 3000",
      url: "http://127.0.0.1:3000",
      reuseExistingServer: true,
      timeout: 30_000,
    },
  ],
});
