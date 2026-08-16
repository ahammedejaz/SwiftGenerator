import { expect, test } from "@playwright/test";

/**
 * The comparison as a tester meets it: import a message, generate, and be told in one
 * sentence whether the difference matters.
 *
 * The backend suite proves the attribution is correct. These prove a tester can reach it,
 * read it, and act on it — and that an expected difference never looks like a fault.
 */

const API = "http://127.0.0.1:8000";

async function generateMt541(
  request: import("@playwright/test").APIRequestContext,
): Promise<string> {
  const samples = await request.get(`${API}/api/v1/messages/MT541/samples?format=MT`);
  expect(samples.ok()).toBeTruthy();
  const fields = (await samples.json()).at(-1).inputs;
  const generated = await request.post(`${API}/api/v1/messages/generate`, {
    data: { format: "MT", messageType: "MT541", fields, persist: false },
  });
  expect(generated.ok()).toBeTruthy();
  return (await generated.json()).outputs.fin as string;
}

async function generateSese023(
  request: import("@playwright/test").APIRequestContext,
): Promise<string> {
  const samples = await request.get(`${API}/api/v1/messages/sese.023/samples?format=MX`);
  const elements = (await samples.json()).at(-1).elements;
  const generated = await request.post(`${API}/api/v1/messages/generate`, {
    data: { format: "MX", messageType: "sese.023", elements, persist: false },
  });
  return (await generated.json()).outputs.xml as string;
}

/** Import a message on step 1 and land in the builder. */
async function importInWizard(page: import("@playwright/test").Page, text: string) {
  await page.goto("/");
  await page.getByRole("button", { name: "Import a message" }).click();
  await page.getByLabel("Message to import").fill(text);
  await page.getByRole("button", { name: "Read this message" }).click();
  await expect(page.getByText(/Loaded from the message you imported/)).toBeVisible({
    timeout: 20_000,
  });
}

test.describe("Original and regenerated", () => {
  test("says nothing was lost when a message round-trips untouched", async ({
    page,
    request,
  }) => {
    await importInWizard(page, await generateMt541(request));
    await page.getByRole("button", { name: "Generate message" }).click();

    await expect(
      page.getByText("The regenerated message is identical"),
    ).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText(/Nothing was lost and nothing was rewritten/)).toBeVisible();
  });

  test("attributes an edited value to the tester and names the field", async ({
    page,
    request,
  }) => {
    await importInWizard(page, await generateMt541(request));
    await page.getByLabel("Sender's Message Reference").first().fill("DIFFTEST0001");
    await page.getByRole("button", { name: "Generate message" }).click();

    await expect(page.getByText("Every difference is accounted for")).toBeVisible({
      timeout: 20_000,
    });
    const diff = page.getByRole("table", {
      name: "Original message compared with the regenerated message",
    });
    await expect(diff).toContainText(":20C::SEME//TESTREF001");
    await expect(diff).toContainText(":20C::SEME//DIFFTEST0001");
    await expect(diff.getByText("You changed this").first()).toBeVisible();
    await expect(diff.getByText("Sender's Message Reference").first()).toBeVisible();
  });

  test("never presents a network-generated trailer as a fault", async ({
    page,
    request,
  }) => {
    const fin = await generateMt541(request);
    await importInWizard(page, `${fin}\n{5:{MAC:00000000}{CHK:123456789ABC}}`);
    await page.getByRole("button", { name: "Generate message" }).click();

    await expect(page.getByText("Every difference is accounted for")).toBeVisible({
      timeout: 20_000,
    });
    await expect(page.getByText(/None of them is a fault/)).toBeVisible();
    await expect(page.getByText("Never generated").first()).toBeVisible();
    // The alarming counters stay at zero.
    await expect(page.getByText(/unexplained/)).toBeHidden();
    await expect(page.getByText(/could not be imported/)).toBeHidden();
  });

  test("says plainly when part of the original could not be imported", async ({
    page,
    request,
  }) => {
    const fin = await generateMt541(request);
    await importInWizard(page, fin.replace(":23G:NEWM", ":23G:NEWM\n:99Z::ZZZZ//SOMETHING"));
    await page.getByRole("button", { name: "Generate message" }).click();

    await expect(
      page.getByText("One part of the original could not be imported"),
    ).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText("Could not be imported").first()).toBeVisible();
  });

  test("ignores formatting-only differences in an ISO 20022 document", async ({
    page,
    request,
  }) => {
    const xml = await generateSese023(request);
    const collapsed = xml
      .split("\n")
      .map((line) => line.trim())
      .join("");

    await importInWizard(page, collapsed);
    await page.getByRole("button", { name: "Generate message" }).click();

    await expect(page.getByText("The regenerated message is identical")).toBeVisible({
      timeout: 20_000,
    });
  });

  test("shows only the changes, and the whole message when asked", async ({
    page,
    request,
  }) => {
    await importInWizard(page, await generateMt541(request));
    await page.getByLabel("Sender's Message Reference").first().fill("DIFFTEST0002");
    await page.getByRole("button", { name: "Generate message" }).click();
    await expect(page.getByText("Every difference is accounted for")).toBeVisible({
      timeout: 20_000,
    });

    const diff = page.getByRole("table", {
      name: "Original message compared with the regenerated message",
    });
    const onlyChanges = page.getByLabel("Show only changes");
    await expect(onlyChanges).toBeChecked();
    const changedRows = await diff.locator("tbody tr").count();

    await onlyChanges.uncheck();
    expect(await diff.locator("tbody tr").count()).toBeGreaterThan(changedRows);
    await expect(diff).toContainText(":16R:GENL");
  });

  test("offers copy, download and a way back to the form", async ({ page, request }) => {
    await importInWizard(page, await generateMt541(request));
    await page.getByRole("button", { name: "Generate message" }).click();
    await expect(page.getByText("The regenerated message is identical")).toBeVisible({
      timeout: 20_000,
    });

    await expect(page.getByRole("button", { name: "Copy regenerated" })).toBeVisible();

    const download = page.waitForEvent("download");
    await page.getByRole("button", { name: "Download regenerated" }).click();
    expect((await download).suggestedFilename()).toMatch(/\.fin$/);

    await page.getByRole("button", { name: "Return to edit" }).click();
    await expect(page.getByLabel("Sender's Message Reference").first()).toBeVisible();
  });

  test("explains what each reason means, without jargon", async ({ page, request }) => {
    const fin = await generateMt541(request);
    await importInWizard(page, `${fin}\n{5:{CHK:123456789ABC}}`);
    await page.getByRole("button", { name: "Generate message" }).click();
    await expect(page.getByText("Every difference is accounted for")).toBeVisible({
      timeout: 20_000,
    });

    await expect(page.getByText("What the reasons mean")).toBeVisible();
    await expect(
      page.getByText(/Allocated by a messaging interface or by the network/),
    ).toBeVisible();
  });

  test("compares a message checked from the Validate screen too", async ({
    page,
    request,
  }) => {
    const fin = await generateMt541(request);

    await page.goto("/validate");
    await page.getByRole("radio", { name: "An existing message" }).click();
    await page.getByLabel("Message to validate").fill(fin);
    await page.getByRole("button", { name: "Validate" }).click();

    await expect(page.getByText("The regenerated message is identical")).toBeVisible({
      timeout: 20_000,
    });
  });

  test("is not offered when there is nothing to compare against", async ({ page }) => {
    // Generating from scratch has no original, so an empty comparison panel would be a
    // dead end rather than information.
    await page.goto("/");
    await page.getByRole("button", { name: /Choose MT/ }).click();
    await page.getByRole("button", { name: /Settlement/ }).first().click();
    await page.getByRole("button", { name: /MT541/ }).first().click();
    await page.getByRole("button", { name: /^Typical/ }).click();
    await page.getByRole("button", { name: "Generate message" }).click();

    await expect(page.getByText("Ready to generate")).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText("Original and regenerated")).toBeHidden();
  });

  test("stays readable on a phone", async ({ page, request }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await importInWizard(page, await generateMt541(request));
    await page.getByRole("button", { name: "Generate message" }).click();
    await expect(page.getByText("The regenerated message is identical")).toBeVisible({
      timeout: 20_000,
    });

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBe(0);
  });
});
