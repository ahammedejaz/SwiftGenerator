import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

/** The other five primary screens, plus the automation-tester journey through Excel. */

test.describe("Bulk / Excel", () => {
  test("offers both templates and explains the columns", async ({ page }) => {
    await page.goto("/excel");

    await expect(page.getByRole("heading", { name: "Bulk and Excel", level: 1 })).toBeVisible();
    await expect(page.getByText(/ScenarioID · MessageType · Sequence/)).toBeVisible();
    await expect(page.getByText(/ScenarioID · MessageType · XPath/)).toBeVisible();
  });

  test("downloads the MT template and generates messages from it", async ({ page }) => {
    await page.goto("/excel");

    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("link", { name: /Download MT template/ }).click(),
    ]);
    const path = join(tmpdir(), `mt-template-${Date.now()}.xlsx`);
    await download.saveAs(path);
    expect(readFileSync(path).length).toBeGreaterThan(4_000);

    await page.setInputFiles('input[type="file"]', path);

    await expect(page.getByText(/scenarios processed/)).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText("3 generated, 0 need attention")).toBeVisible();
    await expect(page.getByRole("button", { name: /TC001 MT541/ })).toBeVisible();
  });

  test("downloads the MX template and generates XML from it", async ({ page }) => {
    await page.goto("/excel");

    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("link", { name: /Download MX template/ }).click(),
    ]);
    const path = join(tmpdir(), `mx-template-${Date.now()}.xlsx`);
    await download.saveAs(path);

    await page.setInputFiles('input[type="file"]', path);
    await expect(page.getByText("3 generated, 0 need attention")).toBeVisible({
      timeout: 30_000,
    });

    // The first scenario opens automatically, so its proof is already rendered.
    await expect(page.locator(".proof").first()).toContainText("urn:iso:std:iso:20022");
  });
});

test.describe("Message Intelligence", () => {
  test("finds PSET across both standards", async ({ page }) => {
    await page.goto("/intelligence");

    await page.getByLabel("Search message fields").fill("PSET");

    await expect(page.getByText("MT — ISO 15022")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("MX — ISO 20022")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Place of Settlement" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "What it means" })).toBeVisible();
    await expect(page.getByText("In a real generated message")).toBeVisible();
  });

  test("finds an MX element by its element name", async ({ page }) => {
    await page.goto("/intelligence");

    await page.getByLabel("Search message fields").fill("SttlmDt");

    await expect(
      page.getByRole("heading", { name: "Intended Settlement Date" }),
    ).toBeVisible({ timeout: 15_000 });
    await expect(
      page.getByText("/Document/SctiesSttlmTxInstr/TradDtls/SttlmDt/Dt/Dt").last(),
    ).toBeVisible();
    await expect(page.getByText("ISODate").first()).toBeVisible();
  });

  test("does not call a model", async ({ page }) => {
    const modelCalls: string[] = [];
    page.on("request", (request) => {
      if (request.url().includes("/agent/") || request.url().includes("openrouter")) {
        modelCalls.push(request.url());
      }
    });

    await page.goto("/intelligence");
    await page.getByLabel("Search message fields").fill("settlement amount");
    await expect(page.getByText("Deterministic")).toBeVisible({ timeout: 15_000 });

    expect(modelCalls).toEqual([]);
  });

  test("says so plainly when nothing matches", async ({ page }) => {
    await page.goto("/intelligence");
    await page.getByLabel("Search message fields").fill("zzzqqqxxx");

    await expect(page.getByRole("heading", { name: "Nothing matched" })).toBeVisible({
      timeout: 15_000,
    });
  });
});

test.describe("Validate", () => {
  test("validates a pasted request body", async ({ page }) => {
    await page.goto("/validate");

    await expect(page.getByRole("heading", { name: "Validate a message", level: 1 })).toBeVisible();
    await page.getByRole("button", { name: "Validate" }).click();

    await expect(page.getByText(/issue.* need.* attention|Ready to generate/)).toBeVisible({
      timeout: 20_000,
    });
  });

  test("explains bad JSON without a stack trace", async ({ page }) => {
    await page.goto("/validate");

    await page.getByLabel("Request body").fill("{ not json");
    await page.getByRole("button", { name: "Validate" }).click();

    await expect(page.getByText(/not valid JSON/)).toBeVisible();
    await expect(page.getByText(/Traceback|at Object\./)).toHaveCount(0);
  });
});

test.describe("API & Automation", () => {
  test("shows runnable examples in four languages", async ({ page }) => {
    await page.goto("/automation");

    await expect(page.getByText("curl -X POST").first()).toBeVisible();
    await page.getByRole("radio", { name: "Java / REST Assured" }).click();
    await expect(page.getByText("RestAssured.baseURI")).toBeVisible();
    await page.getByRole("radio", { name: "Python" }).click();
    await expect(page.getByText("import requests")).toBeVisible();
    await page.getByRole("radio", { name: "JavaScript" }).click();
    await expect(page.getByText(/await fetch/)).toBeVisible();
  });

  test("lists the whole automation surface", async ({ page }) => {
    await page.goto("/automation");

    await expect(page.getByText("/api/v1/messages/generate", { exact: true })).toBeVisible();
    await expect(page.getByText("/api/v1/messages/generate-from-excel").first()).toBeVisible();
    await expect(page.getByText("/api/v1/catalogue").first()).toBeVisible();
    await expect(page.getByText(/X-API-Key/).first()).toBeVisible();
  });
});

test.describe("Recent Messages", () => {
  test("lists what was generated and reopens it", async ({ page }) => {
    // Generate something first so the list is not empty.
    await page.goto("/");
    await page.getByRole("button", { name: /Choose MT/ }).click();
    await page.getByRole("button", { name: /Securities Settlement/ }).click();
    await page.getByRole("button", { name: /MT541/ }).click();
    await page.getByRole("button", { name: /Load typical sample/ }).click();
    await page.getByRole("button", { name: "Generate message" }).click();
    await expect(page.getByText("Ready to generate")).toBeVisible({ timeout: 20_000 });

    await page.goto("/recent");
    await expect(page.getByText("MT541").first()).toBeVisible({ timeout: 15_000 });

    await page.getByRole("button", { name: /MT541/ }).first().click();
    await expect(page.locator(".proof").first()).toContainText("{1:F01", { timeout: 15_000 });
    await expect(page.getByRole("link", { name: /Evidence ZIP/ })).toBeVisible();
  });
});

test.describe("Shell", () => {
  test("keeps the advanced screens reachable", async ({ page }) => {
    await page.goto("/advanced");

    await expect(page.getByRole("link", { name: /Settlement lifecycle/ })).toBeVisible();
    await expect(page.getByRole("link", { name: /Corporate actions/ })).toBeVisible();
    await expect(page.getByRole("link", { name: /AI efficiency/ })).toBeVisible();
  });

  test("never scrolls the page sideways", async ({ page }) => {
    for (const path of ["/", "/excel", "/intelligence", "/validate", "/automation", "/recent"]) {
      await page.goto(path);
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow, `${path} scrolls sideways`).toBeLessThanOrEqual(1);
    }
  });

  test("works on a phone", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });

    for (const path of ["/", "/excel", "/intelligence", "/automation"]) {
      await page.goto(path);
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow, `${path} scrolls sideways on mobile`).toBeLessThanOrEqual(1);
    }
    await expect(page.getByRole("navigation", { name: "Primary" })).toBeVisible();
  });

  test("has a working skip link and a single h1 per page", async ({ page }) => {
    await page.goto("/");
    await page.keyboard.press("Tab");
    await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
    await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);
  });
});
