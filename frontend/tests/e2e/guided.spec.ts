import { expect, test } from "@playwright/test";

test("guided phrase resolves and generates MT541 in three views", async ({ page }) => {
  await page.goto("/guided");
  await page.getByRole("button", { name: "Interpret scenario" }).click();
  await expect(page.getByText("AI interpretation is not configured.")).toBeVisible();
  await page.getByRole("button", { name: "Use deterministic form" }).click();
  await expect(page.getByText("Deterministic non-AI mode")).toBeVisible();
  await expect(page.getByText("MT541", { exact: true })).toBeVisible();
  await expect(page.getByText(/What synthetic reference should identify/)).toBeVisible();

  await page.getByRole("button", { name: "Load synthetic demo answers" }).click();
  await expect(page.getByText("All required business information is present.")).toBeVisible();
  await page.getByRole("button", { name: "Generate valid MT541" }).click();
  await expect(page.getByRole("heading", { name: "MT541", exact: true })).toBeVisible();
  await expect(page.getByText("AGAINST_PAYMENT", { exact: true })).toBeVisible();

  await page.getByRole("tab", { name: "Tag View" }).click();
  await expect(page.getByRole("columnheader", { name: "Tag / qualifier" })).toBeVisible();
  await page.getByRole("button", { name: "Explain PSET" }).first().click();
  await expect(page.getByRole("dialog", { name: "Place of Settlement" })).toBeVisible();
  await expect(page.getByText("Why it is used")).toBeVisible();
  await expect(page.getByText("Client-specific rule")).toBeVisible();
  await expect(page.getByText(/OFFICIAL_ISO_15022/)).toBeVisible();
  await page.getByRole("button", { name: "Close", exact: true }).click();
  await page.getByRole("tab", { name: "Raw View" }).click();
  await expect(page.getByLabel("Supported-subset raw message")).toHaveValue(/\{2:MT541\}/);
  await page.getByRole("button", { name: "Validate raw subset" }).click();
  await expect(page.getByText(/Raw subset validation: VALID/)).toBeVisible();
});


test("BFS profile adds its field and controlled negative mode is explicit", async ({ page }) => {
  await page.goto("/guided");
  await page.getByRole("button", { name: "Use deterministic form" }).click();
  await page.getByLabel("Client profile").selectOption("BFS_CLIENT_DEMO_V1");
  await expect(page.getByLabel("Client reference (BFS required)")).toBeVisible();
  await page.getByRole("button", { name: "Load synthetic demo answers" }).click();
  await expect(page.getByText("All required business information is present.")).toBeVisible();

  await page.getByLabel("Negative test: remove MT541 settlement amount").check();
  await page
    .getByRole("button", { name: "Generate intentional-invalid MT541" })
    .click();
  await expect(
    page.getByText("Intentionally invalid message generated for negative testing."),
  ).toBeVisible();
  await expect(page.getByText(/Profile BFS_CLIENT_DEMO_V1 version 1.0.0/)).toBeVisible();
});


test("expert builder exposes business tag and raw views", async ({ page }) => {
  await page.goto("/expert");
  await page.getByRole("button", { name: "Generate and validate synthetic MT541" }).click();
  await expect(page.getByRole("heading", { name: "MT541", exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "Tag View" }).click();
  await expect(page.getByRole("cell", { name: "Sender reference" })).toBeVisible();
  await page.getByRole("tab", { name: "Raw View" }).click();
  await expect(page.getByLabel("Supported-subset raw message")).toHaveValue(
    /\{1:DEMONSTRATION\}/,
  );
});
