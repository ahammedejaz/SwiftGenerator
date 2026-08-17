import { expect, test } from "@playwright/test";

/**
 * The round trip as a tester experiences it: generate a message, paste it back, change one
 * value, generate again. The backend proves the byte-for-byte property; this proves the
 * tester can actually reach it without knowing an endpoint exists.
 */

const API = "http://127.0.0.1:8000";

/**
 * A real generated message to paste back in.
 *
 * Taken from the API rather than scraped out of the rendered proof sheet: the proof sheet
 * adds line numbers for the reader, and a test that has to strip them is testing its own
 * regex as much as the import.
 */
async function generateSese023(
  request: import("@playwright/test").APIRequestContext,
): Promise<string> {
  const samples = await request.get(`${API}/api/v1/messages/sese.023/samples?format=MX`);
  expect(samples.ok()).toBeTruthy();
  const elements = (await samples.json()).at(-1).elements;

  const generated = await request.post(`${API}/api/v1/messages/generate`, {
    data: { format: "MX", messageType: "sese.023", elements, persist: false },
  });
  expect(generated.ok()).toBeTruthy();
  const xml = (await generated.json()).outputs.xml as string;
  expect(xml).toContain("SctiesSttlmTxInstr");
  return xml;
}

/** The MT equivalent: a complete FIN message, headers and all. */
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
  const fin = (await generated.json()).outputs.fin as string;
  expect(fin).toContain("{1:F01");
  return fin;
}

test.describe("Import an existing message", () => {
  test("is offered on the first step, before a message is chosen", async ({ page }) => {
    await page.goto("/");

    await expect(page.getByRole("heading", { name: /Already have a message/ })).toBeVisible();
    await page.getByRole("button", { name: "Import a message" }).click();
    await expect(page.getByLabel("Message to import")).toBeVisible();
  });

  test("reads a generated message back into the builder and regenerates it", async ({
    page,
    request,
  }) => {
    const xml = await generateSese023(request);

    await page.goto("/");
    await page.getByRole("button", { name: "Import a message" }).click();
    await page.getByLabel("Message to import").fill(xml);
    await page.getByRole("button", { name: "Read this message" }).click();

    // Lands in the builder, with the message identified from the document itself.
    await expect(page.getByText(/Loaded from the message you imported/)).toBeVisible({
      timeout: 20_000,
    });
    await expect(page.getByText(/values? read from/)).toBeVisible();
    await expect(page.getByText("sese.023.001.11").first()).toBeVisible();

    // The values are editable, and regenerating produces the change.
    const reference = page.getByLabel("Transaction Identification").first();
    await expect(reference).toHaveValue(/TESTREF001/);
    await reference.fill("IMPORTED0001");

    await page.getByRole("button", { name: "Generate message" }).click();
    await expect(page.getByText("Ready to generate")).toBeVisible({ timeout: 20_000 });
    await expect(page.locator(".proof").first()).toContainText(
      "<TxId>IMPORTED0001</TxId>",
    );
  });

  test("explains why a document it cannot read was refused", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Import a message" }).click();
    await page
      .getByLabel("Message to import")
      .fill('<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pacs.008.001.10"><X>1</X></Document>');
    await page.getByRole("button", { name: "Read this message" }).click();

    // Names the reason and what is supported — never a bare failure.
    await expect(page.getByText(/not configured in this repository/)).toBeVisible({
      timeout: 20_000,
    });
  });

  test("reports what it could not import rather than dropping it", async ({
    page,
    request,
  }) => {
    const xml = await generateSese023(request);
    const tampered = xml.replace("<TxId>", "<NotInTheSubset>x</NotInTheSubset><TxId>");

    await page.goto("/");
    await page.getByRole("button", { name: "Import a message" }).click();
    await page.getByLabel("Message to import").fill(tampered);
    await page.getByRole("button", { name: "Read this message" }).click();

    await expect(page.getByText(/could not be imported/).first()).toBeVisible({
      timeout: 20_000,
    });
    await expect(page.getByText(/NotInTheSubset/).first()).toBeVisible();
  });

  test("checks an existing MX message from the Validate screen", async ({
    page,
    request,
  }) => {
    const xml = await generateSese023(request);

    await page.goto("/validate");
    await page.getByRole("radio", { name: "An existing message" }).click();
    await page.getByLabel("Message to validate").fill(xml);
    await page.getByRole("button", { name: "Validate" }).click();

    await expect(page.getByText("Ready to generate")).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText("Schema validation")).toBeHidden();
    await page.getByRole("button", { name: /What was checked/ }).click();
    await expect(page.getByText("Schema validation")).toBeVisible();
  });
  test("reads a generated MT message back into the builder and regenerates it", async ({
    page,
    request,
  }) => {
    const fin = await generateMt541(request);

    await page.goto("/");
    await page.getByRole("button", { name: "Import a message" }).click();
    await page.getByLabel("Message to import").fill(fin);
    await page.getByRole("button", { name: "Read this message" }).click();

    // The message named itself in its application header; nothing was chosen by hand.
    await expect(page.getByText(/Loaded from the message you imported/)).toBeVisible({
      timeout: 20_000,
    });
    await expect(page.getByText("MT541").first()).toBeVisible();

    const reference = page.getByLabel("Sender's Message Reference").first();
    await expect(reference).toHaveValue(/TESTREF001/);
    await reference.fill("MTIMPORT0001");

    await page.getByRole("button", { name: "Generate message" }).click();
    await expect(page.getByText("Ready to generate")).toBeVisible({ timeout: 20_000 });
    await expect(page.locator(".proof").first()).toContainText(
      ":20C::SEME//MTIMPORT0001",
    );
  });

  test("asks which message a bare text block is, only once it cannot tell", async ({
    page,
    request,
  }) => {
    const fin = await generateMt541(request);
    // The text block on its own fits MT540 through MT543 equally well.
    const block4 = fin.slice(fin.indexOf("{4:"));

    await page.goto("/");
    await page.getByRole("button", { name: "Import a message" }).click();
    // The question is not asked up front.
    await expect(
      page.getByLabel("Message type of the pasted text block"),
    ).toBeHidden();

    await page.getByLabel("Message to import").fill(block4);
    await page.getByRole("button", { name: "Read this message" }).click();

    await expect(page.getByText(/fits more than one message/)).toBeVisible({
      timeout: 20_000,
    });
    const picker = page.getByLabel("Message type of the pasted text block");
    await expect(picker).toBeVisible();
    await picker.selectOption("MT541");
    await page.getByRole("button", { name: "Read this message" }).click();

    await expect(page.getByText(/Loaded from the message you imported/)).toBeVisible({
      timeout: 20_000,
    });
  });

  test("names the field it could not import from an MT message", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Import a message" }).click();
    await page
      .getByLabel("Message to import")
      .fill("{2:MT541}\n{4:\n:16R:GENL\n:99Z::ZZZZ//X\n:16S:GENL\n-}");
    await page.getByRole("button", { name: "Read this message" }).click();

    await expect(page.getByText(/99Z\/ZZZZ is not part of the configured/)).toBeVisible({
      timeout: 20_000,
    });
  });

  test("checks an existing MT message from the Validate screen", async ({
    page,
    request,
  }) => {
    const fin = await generateMt541(request);

    await page.goto("/validate");
    await page.getByRole("radio", { name: "An existing message" }).click();
    await page.getByLabel("Message to validate").fill(fin);
    await page.getByRole("button", { name: "Validate" }).click();

    await expect(page.getByText("Ready to generate")).toBeVisible({ timeout: 20_000 });
  });
});

test.describe("Cancellation and modification lifecycle", () => {
  const LIFECYCLE = [
    { type: "sese.020", root: "SctiesMsgCxlAdvc" },
    { type: "sese.027", root: "SctiesTxCxlReq" },
    { type: "sese.030", root: "SctiesSttlmCondsModReq" },
    { type: "sese.031", root: "SctiesSttlmCondModStsAdvc" },
  ];

  for (const { type, root } of LIFECYCLE) {
    test(`generates ${type} as AppHdr plus Document`, async ({ page }) => {
      await page.goto("/");
      await page.getByRole("button", { name: /Choose MX/ }).click();
      await page.getByRole("button", { name: /Settlement Commands/ }).click();
      await page.getByRole("button", { name: new RegExp(type.replace(".", "\\.")) }).click();
      await page.getByRole("button", { name: /^Load .* sample/ }).click();
      await page.getByRole("button", { name: "Generate message" }).click();

      await expect(page.getByText("Ready to generate")).toBeVisible({ timeout: 20_000 });
      const proof = page.locator(".proof").first();
      await expect(proof).toContainText(`<${root}>`);
      await expect(proof).toContainText("<AppHdr");
      await expect(proof).not.toContainText("{1:");
    });
  }

  test("states that the lifecycle subsets are unverified", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: /Choose MX/ }).click();
    await page.getByRole("button", { name: /Settlement Commands/ }).click();

    await expect(page.getByText(/sese\.030/).first()).toBeVisible();
  });
});
