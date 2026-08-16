import { expect, test } from "@playwright/test";

test("deterministic amendment decision and MT530 priority workflow", async ({ page }) => {
  await page.goto("/settlement-processing");
  await page.getByRole("button", { name: "Create synthetic MT541" }).click();
  await expect(page.getByText("MT541").first()).toBeVisible();

  await page.getByRole("button", { name: "Decide priority change" }).click();
  await expect(page.getByText("Decision: PROCESSING_DATA_MODIFICATION")).toBeVisible();
  await expect(page.getByText("Method: MT530_PRIORITY")).toBeVisible();

  await page.getByRole("button", { name: "Generate MT530 priority" }).click();
  // Level 2 and exact: this page's <h1> is "Cancellation, MT530 priority, and cancel/rebook",
  // so a loose name match resolves to two headings once the result renders and trips strict
  // mode — while passing whenever the assertion happens to run first. It passed on a laptop
  // and failed on the first CI run. The assertion is about the generated message, so target
  // only its heading.
  await expect(
    page.getByRole("heading", { name: "MT530", exact: true, level: 2 }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Raw View" }).click();
  await expect(page.getByText(":22F::PRIR//0042")).toBeVisible();
  await expect(page.getByRole("button", { name: "Explain PRIR" })).toBeVisible();
});
