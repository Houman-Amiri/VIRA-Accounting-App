/** Phase 5: actual browser styles, real API options; no extra login or mocked theme. */
import { expect, type Locator, type Page } from "@playwright/test";
import { randomUUID } from "node:crypto";

export async function contrast(
  locator: Locator,
  minimum = 4.5,
  property: "color" | "borderTopColor" = "color",
): Promise<void> {
  const ratios = await locator.evaluateAll((elements, colorProperty) => {
    function rgb(value: string): number[] {
      const parts = value.match(/[\d.]+/g)?.map(Number) ?? [];
      if (parts.length < 3) throw new Error(`Unresolved color: ${value}`);
      return parts;
    }
    function luminance(channels: number[]): number {
      return channels.slice(0, 3).reduce((sum, channel, i) => {
        const c = channel / 255;
        return (
          sum +
          (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4) * [0.2126, 0.7152, 0.0722][i]
        );
      }, 0);
    }
    return elements.map((element) => {
      const foreground = rgb(getComputedStyle(element)[colorProperty]);
      let node: Element | null = element;
      const background = [0, 0, 0];
      let remaining = 1;
      while (node && remaining > 0.000001) {
        const channels = rgb(getComputedStyle(node).backgroundColor);
        const alpha = channels[3] ?? 1;
        for (let i = 0; i < 3; i++) background[i] += channels[i] * alpha * remaining;
        remaining *= 1 - alpha;
        node = node.parentElement;
      }
      if (remaining > 0.000001) throw new Error("No resolved opaque background");
      // System Highlight may be translucent in forced-colors mode. Composite
      // actual computed colors rather than rounding or assuming white/black.
      const alpha = foreground[3] ?? 1;
      const a = luminance(foreground.map((c, i) => c * alpha + background[i] * (1 - alpha)));
      const b = luminance(background);
      return {
        text: element.textContent?.slice(0, 80),
        ratio: (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05),
      };
    });
  }, property);
  expect(ratios.length).toBeGreaterThan(0);
  for (const row of ratios) expect(row.ratio, row.text).toBeGreaterThanOrEqual(minimum);
}

async function auditNative(page: Page, count: number, dark: boolean): Promise<void> {
  const selects = page.locator("select:visible");
  await expect(selects).toHaveCount(count);
  for (const select of await selects.all()) {
    await expect(select).toHaveCSS("color-scheme", dark ? "dark" : "light");
    await contrast(select);
    await contrast(select.locator("option"));
    await expect(select.locator("option:checked")).toHaveCount(1);
    // Focus via keyboard, not a synthetic :focus-visible class.
    await select.focus();
    await page.keyboard.press("Tab");
    await page.keyboard.press("Shift+Tab");
    await expect(select).toBeFocused();
    await expect(select).toHaveCSS("outline-style", "solid");
    await expect(select).toHaveCSS("outline-width", "2px");
    // Native OS menus live outside the DOM. Exercise open/close keyboard
    // commands, but do not mistake CSS assertions for a Windows popup capture.
    await select.press("Alt+ArrowDown");
    await page.keyboard.press("Escape");
  }
}

/** Real loaded fonts and computed numeric styles; not only a declared CSS stack. */
export async function auditNumberFonts(page: Page): Promise<void> {
  const loaded = await page.evaluate(async () => {
    const glyphs = "0123456789۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩";
    const faces = await document.fonts.load('16px "Vazirmatn Variable"', glyphs);
    await document.fonts.ready;
    return (
      faces.length >= 2 &&
      faces.every((face) => face.status === "loaded" && face.family.includes("Vazirmatn")) &&
      document.fonts.check('16px "Vazirmatn Variable"', glyphs)
    );
  });
  expect(loaded).toBe(true);
  const numbers = page.locator("main .num:visible");
  // Empty import screens have no numeric results yet: check their controls too.
  await expect(
    page
      .locator("main .num:visible, main input:visible, main select:visible, main textarea:visible")
      .first(),
  ).toBeVisible();
  for (const number of await numbers.all()) {
    await expect(number).toHaveCSS("font-family", /Vazirmatn/);
    await expect(number).toHaveCSS("font-variant-numeric", "tabular-nums");
    await expect(number).toHaveCSS("direction", "ltr");
    await expect(number).toHaveCSS("unicode-bidi", "isolate");
  }
  for (const control of await page
    .locator("main input:visible, main select:visible, main textarea:visible")
    .all())
    await expect(control).toHaveCSS("font-family", /Vazirmatn/);
  const chartText = page.locator("main svg text:visible");
  for (const text of await chartText.all())
    await expect(text).toHaveCSS("font-family", /Vazirmatn/);
}

/** 4-B: real rendered text/control contrast on each themed form, not only tokens. */
export async function auditSurfaces(page: Page, dark: boolean): Promise<void> {
  await auditNumberFonts(page);
  const main = page.locator("main");
  await contrast(main.locator("h1:visible, h2:visible, label:visible, th:visible"));
  if (!dark) {
    await expect(page.locator("body")).toHaveCSS("background-color", "rgb(249, 247, 240)");
    const controls = main.locator("input:visible:not(:disabled), select:visible:not(:disabled)");
    // Read-only reports contain no form borders to measure.
    if (await controls.count()) await contrast(controls, 3, "borderTopColor");
    const primary = main.locator("button.bg-primary:visible:not(:disabled)");
    if (await primary.count()) await contrast(primary);
  }
}

/** Called from the existing shell journey: the real auth limiter stays intact. */
export async function auditMenuThemes(page: Page): Promise<void> {
  async function csrfHeaders(): Promise<Record<string, string>> {
    // The auth provider refreshes session/CSRF cookies on full navigation.
    const csrf = (await page.context().cookies()).find(
      (cookie) => cookie.name === "vira_csrf",
    )?.value;
    expect(csrf).toBeTruthy();
    return { "X-CSRF-Token": decodeURIComponent(csrf ?? "") };
  }
  const resources: Array<{ path: string; version_id: number }> = [];
  async function create(path: string, data: Record<string, unknown>): Promise<string> {
    const response = await page.request.post(path, { headers: await csrfHeaders(), data });
    expect(response.status(), await response.text()).toBe(201);
    const item = await response.json();
    resources.push({ path: `${path}/${item.id}`, version_id: item.version_id });
    return item.id as string;
  }
  try {
    const suffix = randomUUID();
    const supplier = await create("/api/v1/warehouse/suppliers", {
      name: `theme-supplier-${suffix}`,
    });
    const filament = await create("/api/v1/warehouse/items", {
      name: `theme-filament-${suffix}`,
      kind: "FILAMENT",
      unit: "G",
      quantity: "0",
      min_quantity: "0",
      unit_price: "0",
      supplier_id: supplier,
    });
    await create("/api/v1/warehouse/items", {
      name: `theme-product-${suffix}`,
      kind: "PRODUCT",
      unit: "PCS",
      quantity: "0",
      min_quantity: "0",
      unit_price: "0",
      supplier_id: supplier,
    });

    // Toggle the real store through the UI; do not just mutate html.classList.
    for (const dark of [true, false]) {
      await page
        .getByRole("button", { name: dark ? "حالت تاریک" : "حالت روشن", exact: true })
        .click();
      await expect(page.locator("html")).toHaveClass(dark ? /dark/ : /^(?!.*\bdark\b)/);
      for (const [path, count] of [
        ["/price-calc", 1],
        ["/journal/new", 1],
        ["/orders", 6],
        ["/production", 6],
        ["/warehouse", 5],
        ["/bank-import", 5],
        ["/settings", 1],
        ["/journal", 0],
        ["/accounts", 0],
        ["/statements", 0],
        ["/system", 0],
      ] as const) {
        await page.goto(path);
        if (path === "/system") {
          // Exercise the real step-up; never bypass protection for a font audit.
          await expect(page.getByTestId("sudo-dialog")).toBeVisible();
          await page
            .getByTestId("sudo-password")
            .fill(process.env.VIRA_E2E_PASSWORD || "e2e-owner-password");
          await page.getByTestId("sudo-confirm").click();
          await expect(page.getByTestId("sudo-dialog")).not.toBeVisible();
        }
        if (path === "/journal") {
          // The ledger book must let the owner open an entry and change it.
          const open = page.getByTestId(/^entry-open-/).first();
          if ((await open.count()) > 0) {
            await open.click();
            await expect(page.getByTestId("entry-drawer")).toBeVisible();
            await expect(
              page.getByTestId("entry-drawer").getByTestId("entry-status"),
            ).toBeVisible();
            await page.getByTestId("entry-drawer-close").click();
            await expect(page.getByTestId("entry-drawer")).toHaveCount(0);
          }
        }
        if (path === "/accounts") {
          // Plain language only: no English account types, real balances.
          await expect(page.locator("body")).not.toContainText(/\b(ASSET|LIABILITY|EQUITY)\b/);
          await expect(page.locator("body")).not.toContainText("در حال بارگذاری…");
          await expect(page.getByTestId("accounts-row-1010")).toBeVisible();
        }
        if (path === "/statements") {
          // The three statements must show real report data, never the old
          // "will be loaded later" placeholder.
          await expect(page.getByTestId("balance-sheet-state-ready")).toBeVisible();
          await expect(page.getByRole("table", { name: "ترازنامه" })).toBeVisible();
          await expect(page.locator("body")).not.toContainText("Phase 5");
          // Drill down into a real account and back out again.
          const account = page.getByTestId("stmt-open-1010");
          if ((await account.count()) > 0) {
            await account.click();
            await expect(page.getByTestId("stmt-drill")).toBeVisible();
            await page.getByTestId("stmt-drill-close").click();
            await expect(page.getByTestId("stmt-drill")).toHaveCount(0);
          }
          for (const tab of ["سود و زیان", "جریان وجوه نقد"]) {
            await page.getByRole("tab", { name: tab, exact: true }).click();
            await expect(page.getByTestId("income-state-ready")).toHaveCount(
              tab === "سود و زیان" ? 1 : 0,
            );
          }
          await page.getByRole("tab", { name: "جریان وجوه نقد", exact: true }).click();
          await expect(page.getByRole("table", { name: "جریان وجوه نقد" })).toBeVisible();
          await page.getByRole("tab", { name: "ترازنامه آزمایشی", exact: true }).click();
          await expect(page.getByTestId("trial-chart").locator("svg")).toBeVisible();
        }
        if (path === "/warehouse") {
          await page.getByTestId(`move-${filament}`).click();
          await expect(page.getByTestId("movement-form")).toBeVisible();
        }
        if (path === "/bank-import") {
          await page.locator('input[type="file"]').setInputFiles({
            name: "theme-mapping.csv",
            mimeType: "text/csv",
            buffer: Buffer.from(
              "date,amount,description,reference,account\n2026-10-16,1,test,ref,bank\n",
            ),
          });
        }
        if (path === "/settings") {
          await expect(page.getByTestId("const-filamentPerGram")).toBeVisible();
        }
        await auditNative(page, count, dark);
        await auditSurfaces(page, dark);
      }
      // Keyboard selection must still drive a real React-controlled field.
      await page.goto("/price-calc");
      const channel = page.locator("select");
      await channel.focus();
      await channel.press("Home");
      await channel.press("ArrowDown");
      await channel.press("Enter");
      await expect(channel).toHaveValue("direct");
      await channel.press("Home");
      await channel.press("Enter");
      await expect(channel).toHaveValue("marketplace");

      await page.keyboard.press("Control+k");
      const palette = page.getByRole("dialog", { name: "پالت فرمان‌ها" });
      await expect(palette).toBeVisible();
      const input = palette.locator("[cmdk-input]");
      await input.focus();
      await input.press("ArrowDown");
      await expect(palette.locator('[cmdk-item][aria-selected="true"]')).toHaveCount(1);
      await contrast(palette.locator("[cmdk-item]"));
      await expect(input).toHaveCSS("box-shadow", /rgb/);
      // Exercise real search results too (heading text is muted, hits must not be).
      await input.fill("صندوق");
      await expect(page.getByTestId("palette-search-hit").first()).toBeVisible();
      await contrast(page.getByTestId("palette-search-hit"));
      await page.keyboard.press("Escape");
      await expect(palette).not.toBeVisible();

      // Synthetic fixture is only for states not currently present in forms.
      await page.evaluate(() => {
        const fixture = document.createElement("section");
        fixture.id = "theme-state-fixture";
        fixture.innerHTML =
          '<select aria-label="theme states"><option>normal</option><option disabled>disabled</option><optgroup label="group" disabled><option>group disabled</option></optgroup></select><select disabled aria-label="disabled control"><option>disabled control</option></select>';
        document.querySelector("main")?.append(fixture);
      });
      const fixture = page.locator("#theme-state-fixture");
      await contrast(fixture.locator("option:disabled"), 3);
      await expect(fixture.locator("select:disabled")).toHaveCSS("cursor", "not-allowed");
      await contrast(fixture.locator("select:disabled"), 3);
      await page.emulateMedia({ forcedColors: "active" });
      await expect(fixture.locator("select").first()).toHaveCSS("forced-color-adjust", "auto");
      await contrast(fixture.locator("option:checked").first());
      await page.emulateMedia({ forcedColors: "none" });
      await fixture.evaluate((element) => element.remove());
    }
  } catch (error) {
    console.log("THEME AUDIT FAILURE:", error instanceof Error ? error.message : String(error));
    throw error;
  } finally {
    await page.emulateMedia({ forcedColors: "none" });
    // No stock movement or accounting entry was created. Deactivate only our
    // zero-quantity fixtures using the real optimistic-lock/CSRF contract.
    for (const resource of resources.reverse()) {
      const response = await page.request.patch(resource.path, {
        headers: await csrfHeaders(),
        data: { version_id: resource.version_id, is_active: false },
      });
      expect(response.ok(), await response.text()).toBe(true);
    }
  }
}
