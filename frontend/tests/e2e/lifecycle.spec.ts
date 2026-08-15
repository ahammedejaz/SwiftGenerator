import { expect, test } from "@playwright/test";

test("creates the MT541 to MT548 to MT545 lifecycle", async ({ page }) => {
  await page.goto("/lifecycle");
  await page.getByRole("button", { name: "Create synthetic MT541" }).click();
  await expect(page.getByRole("heading", { name: "MT541", exact: true })).toBeVisible();
  await expect(page.getByText("Correlation valid")).toBeVisible();

  await page.getByRole("button", { name: "Generate MT548 Pending" }).click();
  await expect(page.getByRole("heading", { name: "MT548", exact: true })).toBeVisible();
  await expect(page.getByText("PENDING", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Generate MT545 Full" }).click();
  await expect(page.getByRole("heading", { name: "MT545", exact: true })).toBeVisible();
  await expect(page.getByText("FULL", { exact: true })).toBeVisible();

  const types = page.locator("ol li p.text-2xl");
  await expect(types).toHaveText(["MT541", "MT548", "MT545"]);
});
