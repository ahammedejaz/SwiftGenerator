import { expect, test } from "@playwright/test";

test("guided view and efficiency dashboard distinguish deterministic usage", async ({ page }) => {
  await page.goto("/guided");
  await page.getByRole("button", { name: "Use deterministic form" }).click();
  await page.getByText(/AI usage · Deterministic · 0 new tokens/).click();
  await expect(page.getByText("Prompt tokens used now")).toBeVisible();
  await expect(page.getByText("Total tokens used now")).toBeVisible();
  await expect(page.getByText("API calls avoided")).toBeVisible();

  await page.goto("/ai-efficiency");
  await expect(page.getByRole("heading", { name: "AI Efficiency" })).toBeVisible();
  await expect(page.getByText("Deterministic-only")).toBeVisible();
  await expect(page.getByText("Tokens avoided", { exact: true })).toBeVisible();
  await expect(page.getByText("Cache safety and current state")).toBeVisible();
});
