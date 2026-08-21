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

  await page.locator("textarea").fill(MT541);
  await page.getByRole("button", { name: "Preview conversion" }).click();
  await expect(page.getByText(/only exact Mapping Pack is synthetic/)).toBeVisible();

  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Preview conversion" }).click();
  await expect(page.getByText("READY", { exact: true })).toBeVisible();
  await expect(page.getByText("Not represented", { exact: true })).toBeVisible();
  await expect(page.getByText("MT541-A-23G-NONE")).toBeVisible();
  await expect(page.getByText("Canonical target preview")).toBeVisible();
  await expect(page.locator(".proof")).toContainText("sese.023");
  await expect(page.locator(".proof")).toContainText("BusinessMessage");
});
