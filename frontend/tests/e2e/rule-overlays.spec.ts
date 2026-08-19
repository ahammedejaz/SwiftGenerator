import { expect, test } from "@playwright/test";

/**
 * Reviewed rule packs, as a tester meets them.
 *
 * The point of the rule engine is that a tester should not have to know it exists. They
 * pick a profile, enter values, and get a plain sentence naming a field and what to do
 * about it. The rule identifier, the pack and the source location that established the
 * rule sit behind the same Technical details control that has always held the rule id.
 *
 * Both overlays here are synthetic: DEMO_MARKET_V1 is a market invented for this
 * repository, and DEMO_MARKET_CLIENT_V1 is an invented client that narrows it further.
 */

const CONDITION = "Settlement Condition Code";
const COMMON_ID = "Common Identification";

async function openSese023(page: import("@playwright/test").Page) {
  await page.goto("/");
  await page.getByRole("button", { name: /Choose MX/ }).click();
  await page.getByRole("button", { name: /Securities Settlement/ }).click();
  await page.getByRole("button", { name: /sese\.023/ }).click();
  await page.getByRole("button", { name: /Load typical sample/ }).click();
  await page.getByRole("button", { name: "Expert" }).click();
}

test.describe("Reviewed rule packs", () => {
  test("a profile with no overlays validates exactly as it always did", async ({ page }) => {
    await openSese023(page);
    // BASE_DEMO_V1 is the default and has no market or client rule pack.
    await page.getByLabel(CONDITION).selectOption("DIRT");
    await page.getByRole("button", { name: "Generate message" }).click();

    await expect(page.getByText("Ready to generate")).toBeVisible({ timeout: 20_000 });
  });

  test("the client layer refuses a code the market allows, and says which layer", async ({
    page,
  }) => {
    await openSese023(page);
    await page.getByLabel("Client profile").selectOption("DEMO_MARKET_CLIENT_V1");
    // PART passes the market overlay and fails the client's narrower list.
    await page.getByLabel(CONDITION).selectOption("PART");
    await page.getByRole("button", { name: "Generate message" }).click();

    await expect(page.getByText(/issue.* need.* attention/)).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText(`${CONDITION} needs attention`)).toBeVisible();
    await expect(page.getByText(/only the settlement condition NOMC/)).toBeVisible();
    await expect(page.getByText("What to do:").first()).toBeVisible();

    // The evidence is one disclosure away, and never in a tester's face.
    await page.getByText("Technical details").first().click();
    await expect(page.getByText("DEMO-CLI-SESE023-SETTLEMENT-CONDITION")).toBeVisible();
    await expect(page.getByText("Client rule")).toBeVisible();
    await expect(page.getByText(/MX:sese\.023\.001\.11:CLIENT_PROFILE/)).toBeVisible();
    await expect(page.getByText(/SYNTH-DEMO-CLIENT-V1/)).toBeVisible();
    await expect(page.getByText("REVIEWED").first()).toBeVisible();
  });

  test("a code outside the market is refused by both layers, each naming itself", async ({
    page,
  }) => {
    await openSese023(page);
    await page.getByLabel("Client profile").selectOption("DEMO_MARKET_CLIENT_V1");
    await page.getByLabel(CONDITION).selectOption("DIRT");
    await page.getByRole("button", { name: "Generate message" }).click();

    await expect(page.getByText(/need.* attention/).first()).toBeVisible({ timeout: 20_000 });
    // Neither layer suppresses the other: both findings are shown, each in its own words.
    await expect(
      page.getByText(/only the settlement conditions NOMC, PART and CLEN/),
    ).toBeVisible();
    await expect(page.getByText(/only the settlement condition NOMC\./)).toBeVisible();

    // "What was checked" names the new layer; the "Market practice rule" label inside the
    // collapsed Technical details is a different string, which is why this one is exact.
    await page.getByRole("button", { name: "What was checked" }).click();
    await expect(page.getByText("Market practice", { exact: true })).toBeVisible();
  });

  test("correcting the value clears the finding and the message generates", async ({ page }) => {
    await openSese023(page);
    await page.getByLabel("Client profile").selectOption("DEMO_MARKET_CLIENT_V1");
    await page.getByLabel(CONDITION).selectOption("PART");
    await page.getByRole("button", { name: "Generate message" }).click();
    await expect(page.getByText(/needs attention/).first()).toBeVisible({ timeout: 20_000 });

    await page.getByLabel(CONDITION).selectOption("NOMC");
    await page.getByRole("button", { name: "Generate message" }).click();

    await expect(page.getByText("Ready to generate")).toBeVisible({ timeout: 20_000 });
    const proof = page.locator(".proof").first();
    await expect(proof).toContainText("<Cd>NOMC</Cd>");
  });

  test("a client rule can require a field the structure leaves optional", async ({ page }) => {
    await openSese023(page);
    await page.getByLabel("Client profile").selectOption("DEMO_MARKET_CLIENT_V1");
    await page.getByLabel(CONDITION).selectOption("NOMC");
    await page.getByLabel(COMMON_ID).fill("");
    await page.getByRole("button", { name: "Generate message" }).click();

    await expect(page.getByText(`${COMMON_ID} needs attention`)).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText(/supplies a common identification on every instruction/)).toBeVisible();
  });

  test("Message Intelligence shows the reviewed rules that name a field", async ({ page }) => {
    await page.goto("/intelligence");
    await page.getByLabel("Search message fields").fill("SttlmTxCond");

    await expect(page.getByRole("heading", { name: CONDITION })).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByRole("heading", { name: "Rules that use this field" })).toBeVisible();
    await expect(page.getByText("Market practice rule")).toBeVisible();
    await expect(page.getByText("Client rule")).toBeVisible();
    await expect(page.getByText(/SYNTH-DEMO-MARKET-V1/).first()).toBeVisible();
    // A candidate is a reviewer's artifact and never appears here.
    await expect(page.getByText(/AI_CANDIDATE|MACHINE_CHECKED/)).toHaveCount(0);
  });

  test("the rule findings stay readable on a phone", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openSese023(page);
    await page.getByLabel("Client profile").selectOption("DEMO_MARKET_CLIENT_V1");
    await page.getByLabel(CONDITION).selectOption("DIRT");
    await page.getByRole("button", { name: "Generate message" }).click();
    await expect(page.getByText(/need.* attention/).first()).toBeVisible({ timeout: 20_000 });

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(1);
  });
});
