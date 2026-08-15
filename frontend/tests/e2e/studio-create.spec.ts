import { expect, test } from "@playwright/test";

/**
 * The manual-tester journey, end to end: open the app, pick a message, enter data,
 * generate, and get something downloadable — without any SWIFT knowledge.
 */

test.describe("Create Message", () => {
  test("opens directly on the task, not a menu of thirteen things", async ({ page }) => {
    await page.goto("/");

    await expect(page.getByRole("heading", { name: "Create a message", level: 1 })).toBeVisible();
    await expect(page.getByRole("heading", { name: /which message standard/i })).toBeVisible();

    // Six primary destinations, no more.
    const nav = page.getByRole("navigation", { name: "Primary" });
    await expect(nav.getByRole("link")).toHaveCount(6);
  });

  test("walks MT541 from format to a FIN message", async ({ page }) => {
    await page.goto("/");

    await page.getByRole("button", { name: /Choose MT/ }).click();
    await page.getByRole("button", { name: /Securities Settlement/ }).click();
    await page.getByRole("button", { name: /MT541/ }).click();

    // Loading a sample is the fastest honest path for a tester with no data of their own.
    await page.getByRole("button", { name: /^Typical/ }).click();

    await expect(page.getByText(/required fields filled/)).toBeVisible();
    await page.getByRole("button", { name: "Generate message" }).click();

    await expect(page.getByText("Ready to generate")).toBeVisible({ timeout: 20_000 });

    const proof = page.locator(".proof").first();
    await expect(proof).toBeVisible();
    await expect(proof).toContainText("{1:F01");
    await expect(proof).toContainText("{2:I541");
    await expect(proof).toContainText(":20C::SEME//");
    // The fabricated placeholder the old composer emitted must be gone.
    await expect(proof).not.toContainText("DEMONSTRATION");
  });

  test("explains a field without leaving the page or calling a model", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: /Choose MT/ }).click();
    await page.getByRole("button", { name: /Securities Settlement/ }).click();
    await page.getByRole("button", { name: /MT541/ }).click();
    await page.getByRole("button", { name: "Guided" }).click();

    await page.getByRole("button", { name: /Explain Intended Settlement Date/ }).click();

    await expect(page.getByText("What it means")).toBeVisible();
    await expect(page.getByText("Expected format").first()).toBeVisible();
    // No dialog: explanations are inline.
    await expect(page.getByRole("dialog")).toHaveCount(0);
  });

  test("hides optional fields until they are asked for", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: /Choose MT/ }).click();
    await page.getByRole("button", { name: /Securities Settlement/ }).click();
    await page.getByRole("button", { name: /MT541/ }).click();
    await page.getByRole("button", { name: "Guided" }).click();

    const adder = page.getByRole("button", { name: /Add optional field/ }).first();
    await expect(adder).toBeVisible();
    await expect(page.getByText("Common or Client Reference")).toHaveCount(0);

    await adder.click();
    await page.getByRole("button", { name: /Common or Client Reference/ }).click();
    await expect(page.getByLabel("Common or Client Reference")).toBeVisible();
  });

  test("states validation problems in plain English with a fix", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: /Choose MT/ }).click();
    await page.getByRole("button", { name: /Securities Settlement/ }).click();
    await page.getByRole("button", { name: /MT541/ }).click();
    await page.getByRole("button", { name: /^Minimal valid/ }).click();

    // Break one field and validate.
    const reference = page.getByLabel("Sender's Message Reference");
    await reference.fill("");
    await page.getByRole("button", { name: "Validate" }).click();

    await expect(page.getByText(/issue.* need.* attention/)).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText("What to do:").first()).toBeVisible();
  });

  test("generates sese.023 as AppHdr plus Document, never as FIN blocks", async ({ page }) => {
    await page.goto("/");

    await page.getByRole("button", { name: /Choose MX/ }).click();
    await page.getByRole("button", { name: /Securities Settlement/ }).click();
    await page.getByRole("button", { name: /sese\.023/ }).click();
    await page.getByRole("button", { name: /^Typical/ }).click();
    await page.getByRole("button", { name: "Generate message" }).click();

    await expect(page.getByText("Ready to generate")).toBeVisible({ timeout: 20_000 });

    const proof = page.locator(".proof").first();
    await expect(proof).toContainText("<AppHdr");
    await expect(proof).toContainText("urn:iso:std:iso:20022:tech:xsd:sese.023.001.11");
    await expect(proof).toContainText("<SctiesSttlmTxInstr>");
    await expect(proof).not.toContainText("{1:");
    await expect(proof).not.toContainText("{4:");
  });

  test("shows where every envelope value came from", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: /Choose MT/ }).click();
    await page.getByRole("button", { name: /Securities Settlement/ }).click();
    await page.getByRole("button", { name: /MT541/ }).click();
    await page.getByRole("button", { name: /^Typical/ }).click();
    await page.getByRole("button", { name: "Generate message" }).click();
    await expect(page.getByText("Ready to generate")).toBeVisible({ timeout: 20_000 });

    await page.getByRole("button", { name: /Envelope values/ }).click();

    await expect(page.getByText("From the client profile").first()).toBeVisible();
    await expect(page.getByText("The network adds this").first()).toBeVisible();
    await expect(page.getByText(/never fabricated here/)).toBeVisible();
  });

  test("downloads the generated message", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: /Choose MT/ }).click();
    await page.getByRole("button", { name: /Securities Settlement/ }).click();
    await page.getByRole("button", { name: /MT541/ }).click();
    await page.getByRole("button", { name: /^Typical/ }).click();
    await page.getByRole("button", { name: "Generate message" }).click();
    await expect(page.getByText("Ready to generate")).toBeVisible({ timeout: 20_000 });

    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("button", { name: "Download" }).click(),
    ]);
    expect(download.suggestedFilename()).toMatch(/\.fin$/);
  });
});
