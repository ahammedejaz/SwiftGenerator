import { expect, test } from "@playwright/test";

const MT541 = `{4:
:16R:GENL
:20C::SEME//TESTREF001
:20C::COMM//COMMONREF001
:23G:NEWM
:16S:GENL
:16R:TRADDET
:98A::TRAD//20260814
:98A::SETT//20260818
:35B:ISIN XS0000000009
:36B::SETT//UNIT/1000
:16S:TRADDET
:16R:FIAC
:97A::SAFE//SAFE0000001
:16S:FIAC
:16R:SETDET
:22F::SETR//TRAD
:95P::PSET//DEMOGB2LXXX
:95P::DEAG//DEMODEAGXXX
:19A::SETT//USD25000,00
:16S:SETDET
-}`;

test("conversion discloses synthetic authority, loss and validated target XML", async ({ page }) => {
  await page.goto("/convert");
  await expect(page.getByText("Target and mapping authority")).toBeVisible();
  await expect(page.getByText("SYNTHETIC_TEST_ONLY")).toBeVisible();
  await expect(page.getByText(/No production-eligible mapping evidence/)).toBeVisible();

  // The evidence class and the relationship behind the pack are disclosed before anything runs.
  await expect(page.getByTestId("evidence-class")).toContainText(/synthetic/);
  await expect(page.getByText(/synthetic fixture relates its configured MT541/)).toBeVisible();

  await page.locator("textarea").fill(MT541);
  await page.getByRole("button", { name: "Preview conversion" }).click();
  await expect(page.getByText(/only exact Mapping Pack is synthetic \(SYNTHETIC\)/)).toBeVisible();

  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Preview conversion" }).click();
  await expect(page.getByText("READY", { exact: true })).toBeVisible();
  await expect(page.getByText("Not represented", { exact: true })).toBeVisible();
  // Coverage is stated as numbers, never as "equivalent".
  await expect(page.getByTestId("conversion-coverage")).toContainText(/mandatory target elements established/);
  await expect(page.getByTestId("conversion-coverage")).toContainText(/0\/17 rules cite/);
  await expect(page.getByText("MT541-A-23G-NONE")).toBeVisible();
  await expect(page.getByText("Canonical target preview")).toBeVisible();
  await expect(page.locator(".proof")).toContainText("sese.023");
  await expect(page.locator(".proof")).toContainText("BusinessMessage");
});

test("the convert request carries the lane the chosen target declares", async ({ page }) => {
  // The two candidate packs address the knowledge-preview lane, and a request that leaves
  // `targetLane` out resolves against CONFIGURED and is refused with "No exact Mapping Pack
  // matches this source and target" — behind a screen that has just listed the pack and had
  // the user tick the opt-in, which reads as a dead button rather than as a refusal. Only a
  // browser test sees this: every API test names the lane itself.
  const bodies: Record<string, unknown>[] = [];
  await page.route("**/api/v1/messages/convert", async (route) => {
    bodies.push(route.request().postDataJSON());
    await route.continue();
  });

  await page.goto("/convert");
  await page.locator("textarea").fill(MT541);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Preview conversion" }).click();
  await expect(page.getByText("READY", { exact: true })).toBeVisible();

  expect(bodies).not.toHaveLength(0);
  for (const body of bodies) {
    expect(body).toHaveProperty("targetLane");
    expect(body.targetLane).toBeTruthy();
  }
});
