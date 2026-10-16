/** Calendar acceptance through real authenticated forms / disposable SQLite. */
import { expect, type Page } from "@playwright/test";
export async function auditCalendar(page: Page): Promise<void> {
  expect(process.env.VIRA_E2E_DISPOSABLE_DATABASE).toBe("1");
  async function mobileDate(id: string) {
    await page.setViewportSize({ width: 390, height: 844 });
    const input = page.getByTestId(id);
    await input.scrollIntoViewIfNeeded();
    const box = await input.boundingBox();
    expect(box!.width).toBeGreaterThanOrEqual(120);
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(390);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
      true,
    );
    await page.setViewportSize({ width: 1440, height: 900 });
  }
  await mobileDate("entry-date");
  const write = (path: string) =>
    page.waitForResponse(
      (r) => new URL(r.url()).pathname === `/api/v1/${path}` && r.request().method() === "POST",
    );
  await expect(page.getByTestId("entry-date")).toHaveValue("1405/07/25");
  await page.getByTestId("entry-date").fill("۱۴۰۵/۰۷/۲۵");
  await expect(page.getByTestId("entry-date-preview")).toHaveText("۱۴۰۵/۰۷/۲۵");
  const created = write("journal-entries");
  page.once("dialog", (d) => d.accept());
  await page.getByTestId("submit-entry").click();
  const entryResponse = await created;
  expect(entryResponse.status(), await entryResponse.text()).toBe(201);
  const entry = await entryResponse.json();
  expect(entry.transaction_date).toBe("2026-10-17");
  await page.goto("/orders");
  await mobileDate("order-date");
  await expect(page.getByTestId("order-date")).toHaveValue("1405/07/25");
  await page.getByTestId("order-date").fill("۱۴۰۴/۰۱/۰۱");
  await page.getByTestId("order-customer").fill("آزمون تقویم نوروز");
  await page.getByTestId("line-0").getByPlaceholder("نام محصول").fill("نمونه تقویم");
  await page.getByTestId("line-0").getByPlaceholder("قیمت واحد", { exact: true }).fill("۱۲۳.۴۵۶۷");
  let response = write("orders");
  await page.getByTestId("order-submit").click();
  const order = await (await response).json();
  expect(order.order_date).toBe("2025-03-21");
  await page.getByTestId("orders-from").fill("۱۴۰۴/۱۲/۳۰");
  await expect(page.getByTestId("orders-from")).toHaveAttribute("aria-invalid", "true");
  await expect(page.getByTestId(`order-${order.id}`)).toHaveCount(0);
  await page.getByTestId("orders-to").fill("1404/01/01");
  await page.getByTestId("orders-from").fill("1404/01/02");
  await expect(
    page.getByText("ابتدای بازه نباید پس از انتهای آن باشد.", { exact: true }),
  ).toBeVisible();
  const filtered = page.waitForResponse((r) => {
    const u = new URL(r.url());
    return (
      u.pathname === "/api/v1/orders" &&
      u.searchParams.get("date_from") === "2025-03-21" &&
      u.searchParams.get("date_to") === "2025-03-21"
    );
  });
  await page.getByTestId("orders-from").fill("۱۴۰۴/۰۱/۰۱");
  await page.getByTestId("orders-to").fill("1404/01/01");
  await filtered;
  await expect(page.getByTestId(`order-${order.id}`)).toContainText("۱۴۰۴/۰۱/۰۱");
  // An unsaved civil date must survive another tab changing the global preference.
  await page.getByTestId("order-date").fill("۱۴۰۵/۰۷/۲۵");
  const settings = await page.context().newPage();
  await settings.goto("/settings");
  await settings.getByTestId("calendar-choice").selectOption("gregorian");
  await settings.getByTestId("save-calendar").click();
  await expect(settings.getByText("تقویم ذخیره شد.", { exact: true })).toBeVisible();
  await page.bringToFront();
  await expect(page.getByTestId("order-date")).toHaveValue("2026/10/17", { timeout: 35_000 });
  await expect(page.getByTestId("orders-from")).toHaveValue("2025/03/21");
  await expect(page.getByTestId("orders-to")).toHaveValue("2025/03/21");
  await expect(page.getByTestId(`order-${order.id}`)).toContainText("۲۰۲۵/۰۳/۲۱");
  await page.getByTestId("order-customer").fill("آزمون روز ثابت پس از تغییر تقویم");
  await page.getByTestId("line-0").getByPlaceholder("نام محصول").fill("نمونه دوم");
  response = write("orders");
  await page.getByTestId("order-submit").click();
  expect((await (await response).json()).order_date).toBe("2026-10-17");
  // Reload + another browser timezone: persisted policy, same Tehran today.
  const state = await page.context().storageState();
  const other = await page
    .context()
    .browser()!
    .newContext({
      storageState: { cookies: state.cookies, origins: [] },
      timezoneId: "Pacific/Kiritimati",
      locale: "fa-IR",
      baseURL: new URL(page.url()).origin,
    });
  const alternate = await other.newPage();
  await alternate.clock.setFixedTime(new Date("2026-10-16T21:00:00Z"));
  await alternate.goto("/journal/new");
  await expect(alternate.getByTestId("entry-date")).toHaveValue("2026/10/17");
  await alternate.reload();
  await expect(alternate.getByTestId("entry-date")).toHaveValue("2026/10/17");
  await other.close();
  await page.goto("/journal");
  await expect(page.getByRole("cell", { name: "۲۰۲۶/۱۰/۱۷", exact: true }).first()).toBeVisible();
  for (const [path, original] of [
    [`orders/${order.id}`, order],
    [`journal-entries/${entry.id}`, entry],
  ] as const) {
    const read = await page.request.get(`/api/v1/${path}`);
    expect(read.ok()).toBe(true);
    expect(await read.json()).toEqual(original);
  }
  await settings.bringToFront();
  await settings.getByTestId("calendar-choice").selectOption("jalali");
  await settings.getByTestId("save-calendar").click();
  await expect(settings.getByText("تقویم ذخیره شد.", { exact: true })).toBeVisible();
  await settings.close();
  await page.bringToFront();
}
