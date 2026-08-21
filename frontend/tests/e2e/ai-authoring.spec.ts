import { expect, test, type Page } from "@playwright/test";

/**
 * AI-assisted authoring and the knowledge-preview lane in the browser.
 *
 * The backend runs with the scripted provider: every "model" answer is a deterministic
 * seed, so these specs are repeatable and call no network model. What they prove is the
 * product behaviour — a preview entry is named by its release on every call, an AI sample
 * lands on the form through the same path as a deterministic one, an entry that cannot be
 * generated says why, and the deterministic path never touches the assistant.
 */

function watchConsole(page: Page): () => string[] {
  const problems: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") problems.push(`console: ${message.text()}`);
  });
  page.on("pageerror", (error) => problems.push(`pageerror: ${error.message}`));
  return () => problems;
}

async function horizontalOverflow(page: Page): Promise<number> {
  return page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
}

const PREVIEW_STATEMENT = "Structure-backed test generation; complete semantic rules not established.";

test.describe("Create Message — catalogue across lanes", () => {
  test("search lists the configured MT541 first and the MT999 previews with their release chip", async ({
    page,
  }) => {
    const problems = watchConsole(page);
    await page.goto("/");
    await page.getByRole("button", { name: /Choose MT/ }).click();

    const search = page.getByLabel("Search messages");
    await search.fill("MT541");
    const rows = page.getByRole("listitem").filter({ hasText: "MT541" });
    // The reviewed configured entry leads whatever else the catalogue lists for the type.
    await expect(rows.first()).toContainText("Configured & validated");
    await expect(rows.first()).toContainText("Receive Against Payment");

    await search.fill("MT999");
    const previews = page.getByRole("listitem").filter({ hasText: "future release, test preview" });
    await expect(previews).toHaveCount(2);
    await expect(previews.filter({ hasText: "SR2026" })).toHaveCount(1);
    await expect(previews.filter({ hasText: "SR2027" })).toHaveCount(1);

    // A release is searchable on its own.
    await search.fill("SR2027");
    await expect(page.getByRole("listitem").filter({ hasText: "MT999" })).toHaveCount(1);

    expect(problems()).toEqual([]);
  });

  test("generates MT999 SR2026 from an AI sample, with the preview lane stated throughout", async ({
    page,
  }) => {
    const problems = watchConsole(page);
    const laneCalls: string[] = [];
    page.on("request", (request) => {
      const url = request.url();
      if (url.includes("/api/v1/messages/") && url.includes("MT999")) laneCalls.push(url);
    });

    await page.goto("/");
    await page.getByRole("button", { name: /Choose MT/ }).click();
    await page.getByLabel("Search messages").fill("MT999");
    await page.getByRole("button", { name: /MT999.*SR2026 · future release/ }).click();

    // The capability statement is shown before any data is entered.
    await expect(page.getByText(PREVIEW_STATEMENT).first()).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText(/Structure from SWIFT MRG SR2026, Prowide SR2025 corroborated/)).toBeVisible();

    await page.getByRole("button", { name: "AI Typical sample" }).click();
    await expect(page.getByText(/required fields filled/)).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(/AI-assisted synthetic sample|AI sample — cached/)).toBeVisible();
    await expect(page.getByText(/validated by the deterministic engine/)).toBeVisible();
    await expect(page.getByText(/AI used \d+ source sections?/)).toBeVisible();
    await expect(page.getByText(/Cache: (HIT — 0|MISS — \d+) model calls?/)).toBeVisible();

    // The evidence list names documents, sections and pages — nothing about retrieval.
    await page.getByRole("button", { name: "Show details" }).click();
    await expect(page.getByText("MT999 SR2026 MRG").first()).toBeVisible();
    await expect(page.getByText(/page \d+/).first()).toBeVisible();

    await page.getByRole("button", { name: "Validate" }).click();
    await expect(page.getByText("Ready to generate")).toBeVisible({ timeout: 20_000 });

    await page.getByRole("button", { name: "Generate message" }).click();
    await expect(page.getByTestId("provenance")).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId("provenance")).toContainText("Knowledge preview");
    await expect(page.getByTestId("provenance")).toContainText("SR2026");

    const proof = page.locator(".proof").first();
    await expect(proof).toContainText("{2:I999");
    await expect(proof).toContainText(":20C::SEME//");

    // Every specification, sample and generation call named the lane and the release.
    expect(laneCalls.length).toBeGreaterThan(0);
    for (const url of laneCalls) {
      expect(url, `${url} did not name the preview lane`).toContain("lane=KNOWLEDGE_PREVIEW");
      expect(url).toContain("release=SR2026");
    }

    expect(problems()).toEqual([]);
  });

  test("a second AI sample request is served from the cache with no model call", async ({
    page,
  }) => {
    const problems = watchConsole(page);
    await page.goto("/");
    await page.getByRole("button", { name: /Choose MT/ }).click();
    await page.getByLabel("Search messages").fill("MT999");
    await page.getByRole("button", { name: /MT999.*SR2027 · future release/ }).click();
    await expect(page.getByRole("button", { name: "AI Minimal" })).toBeEnabled({ timeout: 20_000 });

    await page.getByRole("button", { name: "AI Minimal" }).click();
    await expect(page.getByText(/required fields filled/)).toBeVisible({ timeout: 30_000 });

    // Back to the start-with step and ask again: the validated sample is cached by identity.
    await page.getByRole("button", { name: "Back", exact: true }).click();
    await page.getByRole("button", { name: "AI Minimal" }).click();
    await expect(page.getByText(/required fields filled/)).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText("Cache: HIT — 0 model calls")).toBeVisible();

    expect(problems()).toEqual([]);
  });

  test("an entry that cannot be generated is listed, explains why, and offers no generate", async ({
    page,
  }) => {
    const problems = watchConsole(page);
    await page.goto("/");
    await page.getByRole("button", { name: /Choose MT/ }).click();
    await page.getByLabel("Search messages").fill("MT998");

    const rows = page.getByRole("listitem").filter({ hasText: "MT998" });
    await expect(rows.first()).toBeVisible();
    await expect(rows.first()).toContainText("Not generatable yet");

    // Clicking opens the reason in place rather than moving on to a step it cannot honour.
    const knowledgeOnly = rows.filter({ hasText: "Knowledge available; structure not yet compilable" }).first();
    await knowledgeOnly.getByRole("button").first().click();
    await expect(page.getByText(/No structure source has been indexed/)).toBeVisible();
    await expect(page.getByText("STRUCTURE_SOURCE_MISSING")).toBeVisible();
    await expect(page.getByText(/Generation and samples are not offered for this entry/)).toBeVisible();

    await expect(page.getByRole("button", { name: "Generate message" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /AI Typical sample/ })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: /Start with MT998/ })).toHaveCount(0);

    expect(problems()).toEqual([]);
  });

  test("a dynamic MX message compiled from a schema loads its form and generates XML", async ({
    page,
  }) => {
    const problems = watchConsole(page);
    await page.goto("/");
    await page.getByRole("button", { name: /Choose MX/ }).click();
    await page.getByLabel("Search messages").fill("test.001");
    await page.getByRole("button", { name: /test\.001\.001\.01/ }).click();

    await expect(page.getByText(/XSD-backed structure/).first()).toBeVisible({ timeout: 20_000 });
    await page.getByRole("button", { name: /Load .* sample/ }).first().click();
    await expect(page.getByText(/required fields filled/)).toBeVisible({ timeout: 20_000 });

    await page.getByRole("button", { name: "Generate message" }).click();
    await expect(page.getByText("Ready to generate")).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId("provenance")).toContainText("Knowledge preview");

    const proof = page.locator(".proof").first();
    await expect(proof).toContainText("urn:iso:std:iso:20022:tech:xsd:test.001.001.01");
    await expect(proof).toContainText("<SynthTstInstr>");
    await expect(proof).not.toContainText("{4:");

    expect(problems()).toEqual([]);
  });

  test("describing a scenario prepares MT541 values into the builder", async ({ page }) => {
    const problems = watchConsole(page);
    await page.goto("/");
    await page.getByRole("button", { name: /Choose MT/ }).click();
    await page.getByRole("button", { name: /Securities Settlement/ }).click();
    await page.getByRole("button", { name: /MT541/ }).click();

    const describe = page.getByLabel("Describe what you want to test");
    await expect(describe).toBeVisible();
    await describe.fill("receive securities against payment");
    await expect(page.getByRole("button", { name: "Prepare values" })).toBeEnabled({ timeout: 20_000 });
    await page.getByRole("button", { name: "Prepare values" }).click();

    await expect(page.getByText(/required fields filled/)).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText("AI-assisted values")).toBeVisible();
    await expect(page.getByLabel("Sender's Message Reference")).toHaveValue(/\S+/);

    await page.getByRole("button", { name: "Validate" }).click();
    await expect(page.getByText("Ready to generate")).toBeVisible({ timeout: 20_000 });

    expect(problems()).toEqual([]);
  });

  test("describing a scenario before choosing a message identifies one from the catalogue", async ({
    page,
  }) => {
    const problems = watchConsole(page);
    await page.goto("/");
    await page.getByRole("button", { name: /Choose MT/ }).click();

    await page.getByLabel("Describe what you want to test").fill("receive securities against payment");
    await page.getByRole("button", { name: "Find the message" }).click();

    const candidate = page.getByRole("button", { name: /MT541.*Receive Against Payment.*Configured & validated/ });
    await expect(candidate).toBeVisible({ timeout: 20_000 });
    await candidate.click();
    await expect(page.getByRole("heading", { name: "Start with MT541" })).toBeVisible();

    expect(problems()).toEqual([]);
  });

  test("the deterministic path never calls the assistant or the knowledge base", async ({
    page,
  }) => {
    const assistantCalls: string[] = [];
    page.on("request", (request) => {
      const url = request.url();
      if (url.includes("/api/v1/ai/") || url.includes("/api/v1/knowledge/")) {
        assistantCalls.push(url);
      }
    });

    await page.goto("/");
    await page.getByRole("button", { name: /Choose MT/ }).click();
    await page.getByRole("button", { name: /Securities Settlement/ }).click();
    await page.getByRole("button", { name: /MT541/ }).click();
    await page.getByRole("button", { name: /Load typical sample/ }).click();
    await page.getByRole("button", { name: "Generate message" }).click();
    await expect(page.getByText("Ready to generate")).toBeVisible({ timeout: 20_000 });

    expect(assistantCalls).toEqual([]);
  });

  test("the wizard with a preview entry fits a phone", async ({ page }) => {
    const problems = watchConsole(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");
    await page.getByRole("button", { name: /Choose MT/ }).click();
    await page.getByLabel("Search messages").fill("MT999");
    await expect(page.getByText("future release, test preview").first()).toBeVisible();
    expect(await horizontalOverflow(page), "search results scroll sideways").toBeLessThanOrEqual(1);

    await page.getByRole("button", { name: /MT999.*SR2026 · future release/ }).click();
    await expect(page.getByText(PREVIEW_STATEMENT).first()).toBeVisible({ timeout: 20_000 });
    expect(await horizontalOverflow(page), "start-with step scrolls sideways").toBeLessThanOrEqual(1);

    await page.getByRole("button", { name: /Load minimal valid sample/ }).click();
    await expect(page.getByText(/required fields filled/)).toBeVisible({ timeout: 20_000 });
    expect(await horizontalOverflow(page), "form scrolls sideways").toBeLessThanOrEqual(1);

    expect(problems()).toEqual([]);
  });
});

test.describe("API & Automation", () => {
  test("documents the AI Test Data API with a Java example and the preview lane", async ({
    page,
  }) => {
    const problems = watchConsole(page);
    await page.goto("/automation");

    await expect(page.getByRole("heading", { name: "AI Test Data API" })).toBeVisible();
    await expect(page.getByText(/Deterministic API: 0 LLM calls/)).toBeVisible();
    await expect(page.getByText(/ai\/test-data\/generate/).first()).toBeVisible();
    await expect(page.getByText(/"scenario":"Typical receive-against-payment settlement"/).first()).toBeVisible();

    await page.getByRole("radio", { name: "Java example" }).click();
    await expect(page.getByText("AiTestDataMt541")).toBeVisible();
    await expect(page.getByText(/post\("\/api\/v1\/ai\/test-data\/generate"\)/)).toBeVisible();

    await expect(page.getByText(/"lane": "KNOWLEDGE_PREVIEW"/).first()).toBeVisible();
    await expect(page.getByText("/api/v1/knowledge/status", { exact: true })).toBeVisible();
    await expect(page.getByText("/api/v1/ai/samples", { exact: true })).toBeVisible();

    expect(problems()).toEqual([]);
  });
});

test.describe("AI Efficiency", () => {
  test("shows the knowledge and authoring counters without inventing a cost", async ({
    page,
  }) => {
    const problems = watchConsole(page);
    await page.goto("/ai-efficiency");

    await expect(page.getByRole("heading", { name: "AI & Knowledge Usage" })).toBeVisible();
    await expect(page.getByText("AI calls today", { exact: true })).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText("Tokens today", { exact: true })).toBeVisible();
    await expect(page.getByText("Model calls avoided", { exact: true })).toBeVisible();
    await expect(page.getByText("Average retrieval", { exact: true })).toBeVisible();
    await expect(page.getByText("Sample cache hits", { exact: true })).toBeVisible();
    await expect(page.getByText("Recent operations", { exact: true })).toBeVisible();
    await expect(page.getByText(/cost unavailable/)).toBeVisible();

    expect(problems()).toEqual([]);
  });
});

test.describe("Message Intelligence", () => {
  test("asks the indexed source about a field and answers only from evidence", async ({
    page,
  }) => {
    const problems = watchConsole(page);
    await page.goto("/intelligence");
    await page.getByLabel("Search message fields").fill("settlement amount");
    await expect(page.getByRole("heading", { name: "What it means" })).toBeVisible({ timeout: 15_000 });

    await page.getByRole("button", { name: "Ask about this field" }).click();
    const answer = page.getByTestId("ask-answer");
    await expect(answer).toBeVisible({ timeout: 20_000 });

    const citations = await page.getByTestId("ask-citation").count();
    if (citations === 0) {
      // No indexed source covers the configured MT541, so the assistant must say exactly
      // that rather than produce something plausible.
      await expect(answer).toHaveText("The available indexed source does not establish this.");
      await expect(page.getByText("Not established by the indexed source")).toBeVisible();
    } else {
      await expect(page.getByTestId("ask-citation").first()).toContainText(/page \d+|·/);
    }

    expect(problems()).toEqual([]);
  });
});
