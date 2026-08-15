import { expect, test } from "@playwright/test";

test("creates the supported corporate-action lifecycle", async ({ page }) => {
  await page.goto("/corporate-actions");
  await page.getByRole("button", { name: "Create MT564 notification" }).click();
  await expect(page.getByRole("heading", { name: "MT564" })).toBeVisible();
  await page.getByRole("button", { name: "Create MT565 election" }).click();
  await expect(page.getByRole("heading", { name: "MT565" })).toBeVisible();
  await page.getByRole("button", { name: "Create MT567 pending" }).click();
  await expect(page.getByRole("heading", { name: "MT567" })).toBeVisible();
  await page.getByRole("button", { name: "Create MT566 confirmation" }).click();
  await expect(page.getByRole("heading", { name: "MT566" })).toBeVisible();
  await page.getByRole("button", { name: "Create MT568 narrative" }).click();
  await expect(page.getByRole("heading", { name: "MT568" })).toBeVisible();
});
