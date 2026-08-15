import { expect, test } from "@playwright/test";

test("deterministic amendment decision and MT530 priority workflow", async ({ page }) => {
  await page.goto("/settlement-processing");
  await page.getByRole("button", { name: "Create synthetic MT541" }).click();
  await expect(page.getByText("MT541").first()).toBeVisible();

  await page.getByRole("button", { name: "Decide priority change" }).click();
  await expect(page.getByText("Decision: PROCESSING_DATA_MODIFICATION")).toBeVisible();
  await expect(page.getByText("Method: MT530_PRIORITY")).toBeVisible();

  await page.getByRole("button", { name: "Generate MT530 priority" }).click();
  await expect(page.getByRole("heading", { name: "MT530" })).toBeVisible();
  await page.getByRole("tab", { name: "Raw View" }).click();
  await expect(page.getByText(":22F::PRIR//0042")).toBeVisible();
  await expect(page.getByRole("button", { name: "Explain PRIR" })).toBeVisible();
});
