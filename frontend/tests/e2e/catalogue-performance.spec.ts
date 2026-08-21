import { expect, test } from "@playwright/test";

test("configured catalogue becomes interactive before preview enrichment and is reused", async ({ page }) => {
  let configured = 0;
  let preview = 0;
  await page.route("**/api/v1/catalogue**", async (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.get("includePreview") === "false") {
      configured += 1;
    } else {
      preview += 1;
      await new Promise((resolve) => setTimeout(resolve, 2_000));
    }
    await route.continue();
  });

  await page.goto("/");
  await expect(page.getByRole("button", { name: /Choose MT/ })).toBeVisible({ timeout: 1_500 });
  // Next development mode can force one complete browser reload after compiling a route.
  // Production makes one request; either way, remounting must not create request fan-out.
  expect(configured).toBeGreaterThanOrEqual(1);
  expect(configured).toBeLessThanOrEqual(2);
  expect(preview).toBe(configured);

  await page.waitForTimeout(2_200);
  const configuredAfterStartup = configured;
  const previewAfterStartup = preview;
  await page.goto("/advanced");
  await page.goto("/");
  await expect(page.getByRole("button", { name: /Choose MT/ })).toBeVisible();
  expect(configured).toBe(configuredAfterStartup);
  expect(preview).toBe(previewAfterStartup);
});
