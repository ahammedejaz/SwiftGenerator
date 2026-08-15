import { expect, test } from "@playwright/test";

test("MT537 penalty builder reports supplied amount without calculation", async ({ page }) => {
  await page.goto("/penalties");
  await expect(page.getByText(/does not calculate penalty amounts/i)).toBeVisible();
  await page.getByRole("button", { name: "Generate MT537" }).click();
  await expect(page.getByRole("heading", { name: "MT537" })).toBeVisible();
  await page.getByRole("tab", { name: "Raw View" }).click();
  await expect(page.getByText(":22H::PNTP//SEFP")).toBeVisible();
  await expect(page.getByText(":19A::AMCO//NEUR25,00")).toBeVisible();
});
