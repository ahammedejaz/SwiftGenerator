import { execFileSync } from "node:child_process";
import path from "node:path";
import { KNOWLEDGE_ENV } from "../../playwright.config";

/**
 * Build the synthetic knowledge base before either server starts.
 *
 * The AI-authoring and Knowledge Base specs need an indexed corpus, and the backend reads
 * it at start-up, so it has to exist first. The sync is incremental: a rerun finds every
 * document unchanged and every structure reused, so this costs seconds after the first
 * run. It also compiles the committed Prowide structure evidence, which is intended — the
 * preview catalogue those specs assert on comes from it.
 */
export default function globalSetup(): void {
  const backend = path.resolve(__dirname, "../../../backend");
  execFileSync(
    path.join(backend, ".venv/bin/python"),
    ["-m", "app.knowledge_base", "sync", "--quiet"],
    {
      cwd: backend,
      stdio: "inherit",
      env: {
        ...process.env,
        ...KNOWLEDGE_ENV,
        // The CLI needs no admin surface, so it runs in plain local mode; the paths are the
        // same ones the backend is given, so it indexes exactly what the server will read.
        KNOWLEDGE_MODE: "local",
        DATABASE_URL: "sqlite://",
        AI_PROVIDER: "disabled",
        APP_ENV: "development",
      },
    },
  );
}
