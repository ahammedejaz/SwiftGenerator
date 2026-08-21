import { expect, test, type Page } from "@playwright/test";

/**
 * The Knowledge Base operator page, against the synthetic fixture corpus that
 * global-setup indexed before the servers started.
 *
 * Every spec here also asserts that the browser console stayed clean: a React key warning
 * or a hydration mismatch is a defect even when the page looks right, and this is the only
 * place it would be seen.
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

test.describe("Knowledge Base", () => {
  test("shows the index as indexed, lists its sources and searches it", async ({ page }) => {
    const problems = watchConsole(page);
    await page.goto("/knowledge-base");

    await expect(page.getByRole("heading", { name: "Knowledge Base", level: 1 })).toBeVisible();
    await expect(page.getByText("Indexed", { exact: true })).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText("Mode: local_uat")).toBeVisible();

    // Provider names are shown; nothing that could be a key or an endpoint is.
    await expect(page.getByText("deployment configured").first()).toBeVisible();
    await expect(page.getByText(/sk-|https?:\/\//)).toHaveCount(0);

    // The synthetic MRG is discovered under its content-derived identity.
    await expect(page.getByText("SWIFT-MT-SR2026-MT999-MRG").first()).toBeVisible();
    await expect(page.getByText("SWIFT-MT-SR2027-MT999-MRG").first()).toBeVisible();
    await expect(page.getByText("ISO20022-XSD-test.001.001.01").first()).toBeVisible();

    // Messages the index yields, with their readiness.
    await expect(page.getByText(/generation ready/).first()).toBeVisible();
    await page.getByLabel("Filter messages").fill("MT999");
    await expect(page.getByText("SR2026", { exact: true }).first()).toBeVisible();

    await page.getByLabel("Search the knowledge base").fill("settlement amount");
    await page.getByRole("button", { name: "Search" }).click();
    await expect(page.getByText(/\d+ citations? ·/)).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("MT999 SR2026 MRG").first()).toBeVisible();
    await expect(page.getByText(/page \d+/).first()).toBeVisible();

    expect(await horizontalOverflow(page)).toBeLessThanOrEqual(1);
    expect(problems()).toEqual([]);
  });

  test("offers a sync only because the backend says it may, and reports the run", async ({
    page,
  }) => {
    const problems = watchConsole(page);
    await page.goto("/knowledge-base");

    const sync = page.getByRole("button", { name: "Sync Knowledge Base" });
    await expect(sync).toBeVisible({ timeout: 20_000 });
    await sync.click();

    // A rerun is incremental: every document is unchanged and every structure reused.
    await expect(page.getByText("Sync just run")).toBeVisible({ timeout: 120_000 });
    await expect(page.getByText("Documents found").first()).toBeVisible();
    await expect(page.getByText("Structures reused").first()).toBeVisible();

    expect(problems()).toEqual([]);
  });

  test("is reachable from Advanced and fits a phone", async ({ page }) => {
    const problems = watchConsole(page);
    await page.goto("/advanced");
    await page.getByRole("link", { name: /Knowledge Base/ }).click();
    await expect(page).toHaveURL(/\/knowledge-base$/);

    // Still six primary destinations: this page lives under Advanced.
    await expect(page.getByRole("navigation", { name: "Primary" }).getByRole("link")).toHaveCount(6);

    await page.setViewportSize({ width: 390, height: 844 });
    await page.reload();
    await expect(page.getByText("Indexed", { exact: true })).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText("SWIFT-MT-SR2026-MT999-MRG").first()).toBeVisible();
    expect(await horizontalOverflow(page), "knowledge base scrolls sideways on a phone").toBeLessThanOrEqual(1);

    expect(problems()).toEqual([]);
  });
});

test.describe("Excel for the knowledge-preview lane", () => {
  test("offers a template per generation-ready preview message, addressed by lane and release", async ({
    page,
  }) => {
    const problems: string[] = [];
    page.on("console", (message) => {
      if (message.type() === "error") problems.push(`console: ${message.text()}`);
    });
    page.on("pageerror", (error) => problems.push(`pageerror: ${error.message}`));

    await page.goto("/excel");
    await expect(page.getByRole("heading", { name: "Knowledge-preview template" })).toBeVisible();
    const select = page.getByTestId("excel-preview-select");
    await expect(select).toBeVisible({ timeout: 20_000 });

    // The lane radio cannot be chosen before a preview message is picked: never implicit.
    await expect(page.getByTestId("excel-lane-preview")).toBeDisabled();

    await page.getByTestId("excel-preview-filter").fill("MT999");
    const options = select.locator("option");
    await expect(options.filter({ hasText: "MT999" }).first()).toBeAttached();
    const sr2026 = await options.filter({ hasText: "SR2026" }).first().getAttribute("value");
    expect(sr2026).toBeTruthy();
    await select.selectOption(sr2026!);

    const href = await page.getByTestId("excel-preview-download").getAttribute("href");
    expect(href).toContain("/api/v1/templates/MT.xlsx");
    expect(href).toContain("messageType=MT999");
    expect(href).toContain("lane=KNOWLEDGE_PREVIEW");
    expect(href).toContain("release=SR2026");
    await expect(page.getByTestId("excel-preview-note")).toContainText("KNOWLEDGE_PREVIEW");

    // The template itself downloads from the backend as a real workbook.
    const response = await page.request.get(href!);
    expect(response.status()).toBe(200);
    expect(response.headers()["content-type"]).toContain("spreadsheetml");

    await expect(page.getByTestId("excel-lane-preview")).toBeEnabled();
    expect(problems).toEqual([]);
  });
});
