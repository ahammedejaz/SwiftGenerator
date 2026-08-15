import { expect, test } from "@playwright/test";

test("creates an empty encrypted draft then explicitly loads an annotated sample", async ({ page }) => {
  await page.goto("/message-builder?messageType=MT541");
  await page.getByRole("button", { name: "Sign in as development author" }).click();
  await expect(page.getByText(/Development Author/)).toBeVisible();

  await page.getByRole("button", { name: "Create empty draft" }).click();
  await expect(page.getByText(/MT541 · PARTIAL/)).toBeVisible();
  await expect(page.getByText(/revision 1 · DRAFT/)).toBeVisible();
  await expect(page.getByText(/Source: SAMPLE_DATA/)).toHaveCount(0);

  await page.getByRole("button", { name: "Load synthetic sample" }).click();
  await expect(page.getByText(/Source: SAMPLE_DATA/).first()).toBeVisible();
  await expect(page.getByText(/confirmation required/).first()).toBeVisible();
  await page.getByRole("button", { name: "Compose and validate" }).click();
  await expect(page.getByRole("heading", { name: "Deterministic Block 4" })).toBeVisible();
  await expect(page.getByText(/CANONICAL_VALID/)).toBeVisible();
});

test("catalogue is explicit about partial and catalogue-only capabilities", async ({ page }) => {
  await page.goto("/catalogue");
  await expect(page.getByText(/no message is marked production-capable/i)).toBeVisible();
  await expect(page.getByRole("cell", { name: "MT537" })).toBeVisible();
  await expect(page.getByText("Specification visible; generation not implemented.").first()).toBeVisible();
});
