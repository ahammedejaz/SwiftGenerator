import { expect, test } from "@playwright/test";

test("MT537 penalty builder reports supplied amount without calculation", async ({ page }) => {
  await page.goto("/penalties");
  await expect(page.getByText(/does not calculate penalty amounts/i)).toBeVisible();
  await page.getByRole("button", { name: "Generate MT537" }).click();
  // Level 2 and exact: the page's own <h1> is "MT537 penalty statements", so a loose name
  // match passes on the title alone before the result renders, and then fails strict mode
  // once it does. The assertion is about the generated message, so target only its heading.
  await expect(
    page.getByRole("heading", { name: "MT537", exact: true, level: 2 }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Raw View" }).click();
  await expect(page.getByText(":22H::PNTP//SEFP")).toBeVisible();
  await expect(page.getByText(":19A::AMCO//NEUR25,00")).toBeVisible();
});
