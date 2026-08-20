import { expect, test, type Page } from "@playwright/test";

/**
 * The authoring journey a tester reported problems with, in a real browser.
 *
 * Each test here corresponds to something that was wrong: a field that demanded SWIFT
 * syntax, a code list rendered as a free-text box, a message that required both settlement
 * agents, and a sample that took four clicks to find.
 */

async function openMessage(page: Page, messageType: string) {
  await page.goto("/");
  await page.getByRole("button", { name: /Choose MT/ }).click();
  await page.getByRole("button", { name: /Securities Settlement/ }).click();
  await page.getByRole("button", { name: new RegExp(messageType) }).click();
}

async function loadTypicalSample(page: Page, messageType: string) {
  await openMessage(page, messageType);
  // Not every message has a distinct TYPICAL sample — where it would equal MINIMAL it is
  // not offered twice — so the leading button is whichever sample leads.
  await page.getByRole("button", { name: /^Load .* sample/ }).click();
  await expect(page.getByText(/required fields filled/)).toBeVisible();
}

/** The generated FIN message, once it is on screen. */
async function generated(page: Page) {
  await page.getByRole("button", { name: "Generate message" }).click();
  await expect(page.getByText("Ready to generate")).toBeVisible({ timeout: 20_000 });
  return page.locator(".proof").first();
}

test.describe("Scenario A — a beginner builds an MT541", () => {
  test("reaches a valid FIN message from a sample without typing SWIFT syntax", async ({
    page,
  }) => {
    await openMessage(page, "MT541");

    // The sample is the first thing offered, not a footnote under two cards.
    const load = page.getByRole("button", { name: /Load typical sample/ });
    await expect(load).toBeVisible();
    await load.click();

    // Values are visible and marked as sample data.
    await expect(page.getByText(/Sample data/)).toBeVisible();
    await expect(page.getByLabel("Sender's Message Reference")).toHaveValue("TESTREF001");

    // The identifier is the identifier alone. The literal is a badge, not something typed.
    const isin = page.getByLabel("Financial Instrument Identification");
    await expect(isin).toHaveValue(/^[A-Z]{2}[A-Z0-9]{9}[0-9]$/);
    await expect(isin).not.toHaveValue(/ISIN/);
    await expect(page.getByText("12 / 12 characters")).toBeVisible();
    await expect(page.getByText("Check digit valid")).toBeVisible();

    // A receipt names the delivering side. The receiving agent is not another core field.
    await expect(page.getByText("Delivering Agent", { exact: true })).toBeVisible();
    await expect(page.getByText("Place of Settlement", { exact: true })).toBeVisible();
    await expect(page.getByText("Receiving Agent", { exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /Add settlement party/ })).toBeVisible();

    // The transaction type is a labelled dropdown carrying a transaction type, not a
    // direction, and it appears once.
    const setr = page.getByLabel("Settlement Transaction Type", { exact: true });
    await expect(setr).toHaveValue("TRAD");
    await expect(setr.locator("option", { hasText: "TRAD — Trade" })).toHaveCount(1);

    const proof = await generated(page);
    await expect(proof).toContainText("{2:I541");
    await expect(proof).toContainText(":22F::SETR//TRAD");
    await expect(proof).toContainText(":95P::DEAG//");
    await expect(proof).toContainText(":95P::PSET//");
    await expect(proof).toContainText(":19A::SETT//");
    await expect(proof).not.toContainText("SETR//BUY");
    await expect(proof).not.toContainText("SETR//RECE");
    await expect(proof).not.toContainText("REAG");
  });

  test("writes the ISIN literal exactly once", async ({ page }) => {
    await loadTypicalSample(page, "MT541");

    const proof = await generated(page);
    // The proof sheet annotates each line with the field name, so match the message text
    // at the start of the line rather than the whole line.
    const text = (await proof.innerText()).match(/:35B:[^\t\n]*/)?.[0] ?? "";

    expect(text.trim()).toMatch(/^:35B:ISIN [A-Z]{2}[A-Z0-9]{9}[0-9]$/);
    expect(text).not.toContain("ISIN ISIN");
  });
});

test.describe("Scenario B — a tester supplies their own identifier", () => {
  test("names the actual defect as the value is typed, and clears when corrected", async ({
    page,
  }) => {
    await loadTypicalSample(page, "MT541");
    const isin = page.getByLabel("Financial Instrument Identification");

    // The value from the reported defect: a final character that is not a check digit.
    await isin.fill("US9897778ABC");
    await expect(page.getByText("The last character must be a numeric check digit")).toBeVisible();

    await page.getByRole("button", { name: "Validate" }).click();
    await expect(
      page.getByText("The final ISIN character must be a numeric check digit."),
    ).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText("You entered")).toBeVisible();
    await expect(page.getByText(/Expected/).first()).toBeVisible();
    // The rule id stays available, and stays out of the way.
    await expect(page.getByText("MT_ISIN_CHECK_DIGIT_NOT_NUMERIC")).toBeHidden();
    await page.getByText("Technical details").first().click();
    await expect(page.getByText("MT_ISIN_CHECK_DIGIT_NOT_NUMERIC")).toBeVisible();

    // Well shaped but the wrong check digit is a different, equally specific answer.
    await isin.fill("XS0000000001");
    await expect(page.getByText(/Check digit does not match — expected 9/)).toBeVisible();

    // Corrected: the live state flips and the message generates.
    await isin.fill("XS0000000009");
    await expect(page.getByText("Check digit valid")).toBeVisible();

    const proof = await generated(page);
    await expect(proof).toContainText(":35B:ISIN XS0000000009");
  });

  test("normalises a pasted literal instead of doubling it", async ({ page }) => {
    await loadTypicalSample(page, "MT541");
    const isin = page.getByLabel("Financial Instrument Identification");

    await isin.fill("ISIN XS0000000009");

    await expect(isin).toHaveValue("XS0000000009");
    const proof = await generated(page);
    await expect(proof).toContainText(":35B:ISIN XS0000000009");
    await expect(proof).not.toContainText("ISIN ISIN");
  });
});

test.describe("Scenario C — the symmetric MT543", () => {
  test("requires the receiving agent and not the delivering agent", async ({ page }) => {
    await loadTypicalSample(page, "MT543");

    await expect(page.getByText("Receiving Agent", { exact: true })).toBeVisible();
    await expect(page.getByText("Place of Settlement", { exact: true })).toBeVisible();
    await expect(page.getByText("Delivering Agent", { exact: true })).toHaveCount(0);

    const proof = await generated(page);
    await expect(proof).toContainText(":22F::SETR//TRAD");
    await expect(proof).toContainText(":95P::REAG//");
    await expect(proof).toContainText(":95P::PSET//");
    await expect(proof).not.toContainText("DEAG");
    await expect(proof).not.toContainText("SETR//DELI");
    await expect(proof).not.toContainText("SETR//SELL");
  });
});

test.describe("Free of payment", () => {
  for (const messageType of ["MT540", "MT542"]) {
    test(`${messageType} never asks for a cash amount`, async ({ page }) => {
      await loadTypicalSample(page, messageType);

      await expect(page.getByText("Settlement Amount", { exact: true })).toHaveCount(0);

      const proof = await generated(page);
      await expect(proof).not.toContainText(":19A::");
    });
  }
});

test.describe("Scenario D — Expert mode", () => {
  test("keeps every value across a round trip and still uses controlled inputs", async ({
    page,
  }) => {
    await loadTypicalSample(page, "MT541");
    const reference = page.getByLabel("Sender's Message Reference");
    await reference.fill("ROUNDTRIP01");

    // Guided -> Expert.
    await page.getByRole("group", { name: "Detail level" }).getByRole("button", {
      name: "Expert",
    }).click();

    await expect(reference).toHaveValue("ROUNDTRIP01");
    await expect(page.getByLabel("Financial Instrument Identification")).toHaveValue(
      /^[A-Z]{2}[A-Z0-9]{9}[0-9]$/,
    );
    // Expert reveals the optional additional chain party the message does not require.
    await expect(page.getByText("Receiving Agent", { exact: true })).toBeVisible();
    // Controlled fields are still dropdowns, not free text.
    await expect(
      page.getByLabel("Settlement Transaction Type", { exact: true }),
    ).toHaveValue("TRAD");
    await expect(page.getByLabel("Function of the Message", { exact: true })).toHaveValue(
      "NEWM",
    );

    // Fill an advanced field, then go back to Guided.
    await page.getByLabel("Previous Message Reference").fill("PREVREF0001");
    await page.getByRole("group", { name: "Detail level" }).getByRole("button", {
      name: "Guided",
    }).click();

    // A value entered in Expert is still visible in Guided rather than hidden but submitted.
    await expect(reference).toHaveValue("ROUNDTRIP01");
    await expect(page.getByLabel("Previous Message Reference")).toHaveValue("PREVREF0001");
  });

  test("offers the party options as a business question, not as option letters", async ({
    page,
  }) => {
    await loadTypicalSample(page, "MT541");

    const question = page.getByText("How do you want to identify this party?").first();
    await expect(question).toBeVisible();
    await expect(page.getByRole("button", { name: "Proprietary identifier" }).first()).toBeVisible();

    // Switching to the proprietary form asks for the scheme separately, so a BIC cannot be
    // written into it by accident.
    const deag = page.locator("#row-MT541-E-95P-DEAG");
    await expect(deag).toBeVisible();
    await deag.getByRole("button", { name: "Proprietary identifier" }).click();
    await expect(deag.getByLabel("Delivering Agent data source scheme")).toBeVisible();
    await expect(deag.getByLabel("Delivering Agent proprietary identifier")).toBeVisible();

    await deag.getByLabel("Delivering Agent data source scheme").fill("AGT");
    await deag.getByLabel("Delivering Agent proprietary identifier").fill("DEMODEAG01");

    const proof = await generated(page);
    // Option R is `:4!c/8c/34x`: one slash before the data source scheme, not the `//`
    // that precedes a BIC in option P. The golden fixtures render it the same way.
    await expect(proof).toContainText(":95R::DEAG/AGT/DEMODEAG01");
    await expect(proof).not.toContainText(":95P::DEAG//");
  });
});

test.describe("Controlled values", () => {
  test("every configured code list is a labelled selector", async ({ page }) => {
    await loadTypicalSample(page, "MT548");

    for (const [label, expected] of [
      ["Settlement Processing Status", "PEND — Pending"],
      ["Linked Message Type", "541 — MT541 — Receive Against Payment"],
    ] as const) {
      const select = page.getByLabel(label, { exact: true });
      await expect(select).toHaveJSProperty("tagName", "SELECT");
      await expect(select.locator("option", { hasText: expected })).toHaveCount(1);
    }
  });

  test("a code the message does not allow cannot be chosen", async ({ page }) => {
    await loadTypicalSample(page, "MT541");

    const options = await page
      .getByLabel("Settlement Transaction Type", { exact: true })
      .locator("option")
      .allInnerTexts();

    expect(options.join(" ")).toContain("TRAD — Trade");
    expect(options.join(" ")).not.toContain("BUY");
    expect(options.join(" ")).not.toContain("SELL");
    expect(options.join(" ")).not.toContain("RECE");
    expect(options.join(" ")).not.toContain("DELI");
  });
});

test.describe("Scenario E — mobile", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("the sample flow works at phone width with no sideways scrolling", async ({ page }) => {
    await loadTypicalSample(page, "MT541");

    await expect(page.getByLabel("Financial Instrument Identification")).toBeVisible();
    await expect(page.getByText("Delivering Agent", { exact: true })).toBeVisible();

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(1);

    const proof = await generated(page);
    await expect(proof).toContainText(":22F::SETR//TRAD");

    const afterGenerate = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(afterGenerate).toBeLessThanOrEqual(1);
  });
});
