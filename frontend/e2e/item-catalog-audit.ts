/** Persisted catalog through real UI/HTTP/SQLite; no extra login or mocked options. */
import { expect, type Page } from "@playwright/test";
import { randomUUID } from "node:crypto";
import Decimal from "decimal.js";
import { auditNumberFonts, contrast } from "./theme-audit";

type Choice = { id: string; name: string; is_active: boolean; version_id: number };
export async function auditItemCatalog(page: Page) {
  expect(process.env.VIRA_E2E_DISPOSABLE_DATABASE).toBe("1");
  const suffix = randomUUID().slice(0, 8);
  const names = {
    types: `رزین ${suffix}`,
    units: `لیتر ${suffix}`,
    suppliers: `تأمین رزین ${suffix}`,
  };
  const choices: Record<string, Choice> = {};
  const get = async (path: string) => {
    const response = await page.request.get(`/api/v1/warehouse/${path}`);
    expect(response.ok(), await response.text()).toBe(true);
    return response.json();
  };
  await page.goto("/settings");
  for (const category of ["types", "units", "suppliers"] as const) {
    const panel = page.getByTestId(`catalog-${category}`);
    await panel.getByTestId(`catalog-name-${category}`).fill(names[category]);
    await panel.getByRole("button", { name: "افزودن", exact: true }).click();
    await expect(panel.getByText(names[category], { exact: true })).toBeVisible();
    choices[category] = (
      await get(category === "suppliers" ? "suppliers" : `catalog/${category}`)
    ).find((r: Choice) => r.name === names[category]);
    expect(choices[category].is_active).toBe(true);
  }
  // An unused choice is physically deleted only after explicit confirmation.
  const units = page.getByTestId("catalog-units");
  const unused = `موقت ${suffix}`;
  await units.getByTestId("catalog-name-units").fill(unused);
  await units.getByRole("button", { name: "افزودن", exact: true }).click();
  await units.getByRole("button", { name: `حذف ${unused}`, exact: true }).click();
  const confirm = units.getByRole("alertdialog");
  await expect(confirm).toBeVisible();
  await confirm.getByRole("button", { name: "تأیید حذف", exact: true }).click();
  await expect(units.getByText(unused, { exact: true })).toHaveCount(0);
  expect((await get("catalog/units")).some((r: Choice) => r.name === unused)).toBe(false);

  const createName = `کالای رزین ${suffix}`;
  await page.goto("/warehouse");
  await page.getByTestId("new-item-name").fill(createName);
  await page.getByTestId("new-item-kind").selectOption(choices.types.id);
  await page.getByTestId("new-item-unit").selectOption(choices.units.id);
  await page.getByTestId("new-item-supplier").selectOption(choices.suppliers.id);
  await page.getByTestId("new-item-quantity").fill("۱۲٫۳۴۵۶");
  await page.getByTestId("new-item-price").fill("۷٫۰۰۰۱");
  await page.getByTestId("new-item-min").fill("۲۰");
  await page.getByTestId("new-item-submit").click();
  await expect(page.getByTestId("warehouse-message")).toContainText("کالا ثبت شد");
  const item = (await get("items")).find((row: { name: string }) => row.name === createName);
  expect(new Decimal(item.value).eq(new Decimal("12.3456").times("7.0001"))).toBe(true);
  // Public movements listing is the canonical read endpoint.
  const movements = (await get("movements")).filter(
    (row: { item_id: string }) => row.item_id === item.id,
  );
  await page.reload();
  const row = page.getByTestId(`item-${item.id}`);
  await expect(row).toContainText(names.types);
  await expect(row).toContainText(names.units);
  await expect(row).toContainText(names.suppliers);

  await page.goto("/settings");
  for (const category of ["types", "units", "suppliers"] as const) {
    const panel = page.getByTestId(`catalog-${category}`);
    await panel.getByRole("button", { name: `حذف ${names[category]}`, exact: true }).click();
    await panel
      .getByRole("alertdialog")
      .getByRole("button", { name: "تأیید حذف", exact: true })
      .click();
    await expect(panel.getByTestId(`catalog-row-${choices[category].id}`)).toContainText("غیرفعال");
    await expect(panel.getByRole("status")).toContainText("سوابق");
  }
  await page.goto("/warehouse");
  await expect(
    page.getByTestId("new-item-kind").locator(`option[value="${choices.types.id}"]`),
  ).toHaveCount(0);
  await expect(
    page.getByTestId("new-item-supplier").locator(`option[value="${choices.suppliers.id}"]`),
  ).toHaveCount(0);
  await expect(page.getByTestId(`item-${item.id}`)).toContainText(names.units);
  expect(
    (await get("movements")).filter((r: { item_id: string }) => r.item_id === item.id),
  ).toEqual(movements);
  const csrf = (await page.context().cookies()).find((c) => c.name === "vira_csrf")!.value;
  const blocked = await page.request.post("/api/v1/warehouse/items", {
    headers: { "X-CSRF-Token": decodeURIComponent(csrf) },
    data: {
      name: "غیرفعال",
      kind: choices.types.id,
      unit: choices.units.id,
      supplier_id: choices.suppliers.id,
    },
  });
  expect(blocked.status()).toBe(400);
  await page.goto("/settings");
  for (const category of ["types", "units", "suppliers"] as const) {
    const panel = page.getByTestId(`catalog-${category}`);
    await panel.getByRole("button", { name: `فعال‌سازی ${names[category]}`, exact: true }).click();
    await expect(panel.getByTestId(`catalog-row-${choices[category].id}`)).not.toContainText(
      "غیرفعال",
    );
  }
  for (const width of [390, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    for (const dark of [true, false]) {
      const current = await page.locator("html").evaluate((el) => el.classList.contains("dark"));
      if (current !== dark)
        await page
          .getByRole("button", { name: dark ? "حالت تاریک" : "حالت روشن", exact: true })
          .click();
      // Measure final theme colors, not a frame halfway through a real CSS
      // color transition. Do not disable animations or lower the AA threshold.
      await page.evaluate(async () => {
        await Promise.allSettled(
          document
            .getAnimations()
            .filter((animation) => animation instanceof CSSTransition)
            .map((animation) => animation.finished),
        );
      });
      const catalog = page.locator("#item-catalog-settings");
      await contrast(catalog.locator("h3, label, li>span, button:visible"));
      await auditNumberFonts(page);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      );
    }
  }
  await page.goto("/warehouse");
  await expect(
    page.getByTestId("new-item-kind").locator(`option[value="${choices.types.id}"]`),
  ).toHaveCount(1);
  await page.getByTestId("new-item-kind").selectOption(choices.types.id);
  await expect(
    page.getByTestId("new-item-unit").locator(`option[value="${choices.units.id}"]`),
  ).toHaveCount(1);
}
