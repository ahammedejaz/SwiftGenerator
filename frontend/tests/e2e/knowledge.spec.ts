import { expect, test } from "@playwright/test";

test("knowledge centre searches and explains PSET without an AI flow", async ({ page }) => {
  await page.goto("/knowledge");
  await expect(page.getByRole("heading", { name: "Tag Intelligence Centre" })).toBeVisible();
  await page.getByPlaceholder("Search PSET, account, date…").fill("settlement venue");
  await page.getByRole("button", { name: "Search" }).click();
  // A settlement party is now offered in two field options — a BIC under 95P and a
  // proprietary scheme identifier under 95R — so the search returns both.
  await expect(page.getByRole("button", { name: "95P / PSET" }).first()).toBeVisible();
  const proprietary = page.getByRole("button", { name: "95R / PSET" }).first();
  await proprietary.waitFor({ state: "visible" });
  await proprietary.click();
  await expect(page.getByRole("dialog", { name: "Place of Settlement" })).toBeVisible();
  await expect(page.getByText("What happens if it is missing")).toBeVisible();
  await expect(page.getByText("├── Related to: DEAG")).toBeVisible();
  await expect(page.getByText("└── Related to: REAG")).toBeVisible();
  await expect(page.getByText(/KB_2026_08_05_V1/)).toBeVisible();
});
