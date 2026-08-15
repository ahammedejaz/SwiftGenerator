import { expect, test } from "@playwright/test";

test("uploads the Excel template, reports invalid rows, and downloads the ZIP", async ({
  page,
  request,
}) => {
  const template = await request.get("http://localhost:8000/api/bulk/template");
  expect(template.ok()).toBeTruthy();
  await page.goto("/bulk");
  await page.getByLabel("Select Excel workbook").setInputFiles({
    name: "synthetic-scenarios.xlsx",
    mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    buffer: await template.body(),
  });
  await page.getByRole("button", { name: "Generate valid rows" }).click();
  await expect(page.getByText("3 generated · 1 failed · 4 total")).toBeVisible();
  await expect(page.getByRole("cell", { name: "BULK-INVALID-MT541" })).toBeVisible();
  await expect(page.getByText("FAILED", { exact: true })).toBeVisible();

  await page.getByRole("link", { name: "Open execution report" }).click();
  await expect(page.getByRole("heading", { name: "Bulk execution report" })).toBeVisible();
  await expect(page.getByText("Row audit")).toBeVisible();
  await expect(page.getByText("3", { exact: true }).first()).toBeVisible();

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download complete ZIP" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/securities-message-studio-report-.*\.zip/);
});
