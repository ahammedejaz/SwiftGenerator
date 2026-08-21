import { defineConfig, devices } from "@playwright/test";

/** A shared runner is slower than a laptop, and a cold Next compile is the slowest part of
 *  the first test. Thirty seconds is comfortable locally and marginal in CI. */
const CI_SERVER_TIMEOUT_MS = process.env.CI ? 180_000 : 30_000;
const BACKEND_PORT = Number(process.env.E2E_BACKEND_PORT ?? 8000);
const FRONTEND_PORT = Number(process.env.E2E_FRONTEND_PORT ?? 3000);
const REUSE_EXISTING = !process.env.CI && !process.env.E2E_BACKEND_PORT && !process.env.E2E_FRONTEND_PORT;

/**
 * The knowledge base the AI-authoring specs run against. Built from the synthetic fixture
 * corpus under backend/tests/fixtures/knowledge into ignored build/ paths, by global-setup,
 * before either server starts. Paths are relative to the repository root; the backend
 * resolves them itself. The same values go to the backend so it reads what setup wrote.
 */
export const KNOWLEDGE_ENV = {
  KNOWLEDGE_AI_PROVIDER: "scripted",
  KNOWLEDGE_SOURCE_DIR: "backend/tests/fixtures/knowledge",
  KNOWLEDGE_DB_PATH: "build/knowledge-e2e/knowledge.sqlite3",
  KNOWLEDGE_PACK_DIR: "build/knowledge-e2e/packs",
  KNOWLEDGE_SOURCE_CACHE_DIR: "build/knowledge-e2e/cache",
  EMBEDDING_PROVIDER: "fake",
};

export default defineConfig({
  testDir: "./tests/e2e",
  globalSetup: "./tests/e2e/global-setup.ts",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  // On CI the HTML report is the artifact somebody opens after a failure; locally it is
  // noise nobody asked for.
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    // 127.0.0.1 everywhere, never `localhost`. The servers bind 127.0.0.1, but a browser
    // resolves `localhost` to ::1 first on a dual-stack machine and only then falls back —
    // so a request occasionally died with ECONNREFUSED ::1:8000 and a test unrelated to
    // networking failed with "the backend is down". macOS binds `--host ::` as IPv6-only,
    // so matching the address is the fix rather than listening on both.
    baseURL: `http://127.0.0.1:${FRONTEND_PORT}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command:
        `../backend/.venv/bin/uvicorn app.main:app --app-dir ../backend --host 127.0.0.1 --port ${BACKEND_PORT}`,
      url: `http://127.0.0.1:${BACKEND_PORT}/api/health/ready`,
      // Never adopt a process CI did not start. A runner has nothing on these ports, so
      // this changes no behaviour there — it removes the possibility of a green run that
      // tested somebody else's server, which is a failure mode worth making impossible
      // rather than unlikely.
      reuseExistingServer: REUSE_EXISTING,
      timeout: CI_SERVER_TIMEOUT_MS,
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
        FRONTEND_ORIGIN: `http://127.0.0.1:${FRONTEND_PORT}`,
        // local_uat exposes the sync endpoint, which the Knowledge Base page offers only
        // when the backend says it may. The scripted provider answers from deterministic
        // seeds, so no model is ever called and no key is needed.
        KNOWLEDGE_MODE: "local_uat",
        ...KNOWLEDGE_ENV,
      },
    },
    {
      command: `npm run dev -- --hostname 127.0.0.1 --port ${FRONTEND_PORT}`,
      url: `http://127.0.0.1:${FRONTEND_PORT}`,
      reuseExistingServer: REUSE_EXISTING,
      timeout: CI_SERVER_TIMEOUT_MS,
      env: {
        NEXT_PUBLIC_API_BASE_URL: `http://127.0.0.1:${BACKEND_PORT}`,
        NEXT_DIST_DIR: `.next-e2e-${FRONTEND_PORT}`,
      },
    },
  ],
});
