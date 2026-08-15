import { expect, test } from "@playwright/test";

test("knowledge centre searches and explains PSET without an AI flow", async ({ page }) => {
  await page.goto("/knowledge");
  await expect(page.getByRole("heading", { name: "Tag Intelligence Centre" })).toBeVisible();
  await page.getByPlaceholder("Search PSET, account, date…").fill("settlement venue");
  await page.getByRole("button", { name: "Search" }).click();
  await page.getByRole("button", { name: "95R / PSET" }).first().click();
  await expect(page.getByRole("dialog", { name: "Place of Settlement" })).toBeVisible();
  await expect(page.getByText("What happens if it is missing")).toBeVisible();
  await expect(page.getByText("└── Required with: DEAG")).toBeVisible();
  await expect(page.getByText(/KB_2026_08_05_V1/)).toBeVisible();
});
