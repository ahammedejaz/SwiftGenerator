import { expect, test } from "@playwright/test";

test("creates the supported corporate-action lifecycle", async ({ page }) => {
  await page.goto("/corporate-actions");
  await page.getByRole("button", { name: "Create MT564 notification" }).click();
  // Exact and level 2 throughout: a generated message's code is an <h2>, and a loose name
  // match would also find a page title containing it. No collision on this page today;
  // pinned so a reworded heading cannot quietly create one.
  await expect(page.getByRole("heading", { name: "MT564", exact: true, level: 2 })).toBeVisible();
  await page.getByRole("button", { name: "Create MT565 election" }).click();
  await expect(page.getByRole("heading", { name: "MT565", exact: true, level: 2 })).toBeVisible();
  await page.getByRole("button", { name: "Create MT567 pending" }).click();
  await expect(page.getByRole("heading", { name: "MT567", exact: true, level: 2 })).toBeVisible();
  await page.getByRole("button", { name: "Create MT566 confirmation" }).click();
  await expect(page.getByRole("heading", { name: "MT566", exact: true, level: 2 })).toBeVisible();
  await page.getByRole("button", { name: "Create MT568 narrative" }).click();
  await expect(page.getByRole("heading", { name: "MT568", exact: true, level: 2 })).toBeVisible();
});
