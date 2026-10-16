/** Integration proof through real HTTP/SQLite, NOT mocked chart/report responses.
 * Creates immutable posted entries: ONLY run against an explicitly disposable DB.
 */
import { expect, type Page } from "@playwright/test";
import { randomUUID } from "node:crypto";
import Decimal from "decimal.js";
import { faNumber } from "../src/lib/fa";

export async function auditDashboard(page: Page): Promise<void> {
  expect(
    process.env.VIRA_E2E_DISPOSABLE_DATABASE,
    "Financial fixtures require an explicitly disposable database",
  ).toBe("1");
  await page.goto("/");
  await expect(page.getByTestId("kpi-assets").locator(".num")).toBeVisible();
  async function post(path: string, data: Record<string, unknown> = {}) {
    const csrf = (await page.context().cookies()).find((c) => c.name === "vira_csrf")?.value;
    expect(csrf).toBeTruthy();
    const response = await page.request.post(path, {
      headers: { "X-CSRF-Token": decodeURIComponent(csrf!) },
      data,
    });
    expect(response.ok(), await response.text()).toBe(true);
    return response.json();
  }
  async function get(path: string) {
    const response = await page.request.get(path);
    expect(response.ok(), await response.text()).toBe(true);
    return response.json();
  }
  const accounts = (await get("/api/v1/accounts")) as Array<{ id: string; code: string }>;
  const account = (code: string) => accounts.find((a) => a.code === code)!.id;
  const today = await page.evaluate(() =>
    new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Tehran" }).format(new Date()),
  );
  const futureDate = new Date(`${today}T12:00:00Z`);
  futureDate.setUTCDate(futureDate.getUTCDate() + 1);
  async function journal(
    debit: string,
    credit: string,
    amount: string,
    day = today,
    posted = true,
  ) {
    const entry = await post("/api/v1/journal-entries", {
      transaction_date: day,
      description: "آزمایشی — اثبات داشبورد، نه اطلاعات واقعی کسب‌وکار",
      splits: [
        { account_id: account(debit), debit: amount },
        { account_id: account(credit), credit: amount },
      ],
    });
    if (posted) await post(`/api/v1/journal-entries/${entry.id}/post`);
  }
  await journal("1010", "3010", "1000000.0001");
  await journal("1010", "4010", "400000");
  await journal("5040", "1010", "150000");
  await journal("1020", "2010", "500000");
  await journal("1030", "3010", "700000"); // inventory is NOT cash
  await journal("1010", "4010", "990000", futureDate.toISOString().slice(0, 10));
  await journal("1010", "4010", "50000", today, false); // draft is NOT revenue
  const suffix = randomUUID().slice(0, 8);
  const supplier = await post("/api/v1/warehouse/suppliers", {
    name: `آزمایشی تأمین‌کننده داشبورد ${suffix}`,
  });
  await post("/api/v1/warehouse/items", {
    name: `آزمایشی PLA ${suffix}`,
    kind: "FILAMENT",
    unit: "G",
    quantity: "100",
    min_quantity: "150",
    unit_price: "100",
    supplier_id: supplier.id,
  });
  await post("/api/v1/warehouse/items", {
    name: `آزمایشی محصول ${suffix}`,
    kind: "PRODUCT",
    unit: "PCS",
    quantity: "2",
    min_quantity: "0",
    unit_price: "200",
  });
  const order = await post("/api/v1/orders", {
    order_date: today,
    customer_name: `آزمایشی مشتری ${suffix}`,
    items: [
      {
        product_name: "آزمایشی مدل",
        quantity: "2",
        unit_price: "3000",
        unit_cost: "1000",
        weight_g: "10",
        print_hours: "1",
      },
    ],
  });
  await post("/api/v1/orders", {
    order_date: today,
    customer_name: "آزمایشی لغوشده",
    status: "CANCELLED",
    items: [{ product_name: "آزمایشی", quantity: "1", unit_price: "90000", unit_cost: "1" }],
  });
  const job = await post("/api/v1/production/jobs", {
    product_name: `آزمایشی تولید ${suffix}`,
    quantity: "2.5",
    filament_grams: "10.1",
  });

  const balance = await get(`/api/v1/reports/balance-sheet?as_of=${today}`);
  const inventory = await get("/api/v1/warehouse/summary");
  // Read the same explicit period the SPA actually requested (no hard-coded year).
  const financialRequest = page.waitForResponse(
    (r) => r.url().includes("/reports/income-statement?") && r.ok(),
  );
  await page.reload();
  const income = await (await financialRequest).json();
  const rendered = (value: string, rial = true) =>
    faNumber(
      new Decimal(value)
        .div(rial ? 10 : 1)
        .toFixed(5)
        .replace(/(\.\d*?)0+$/, "$1")
        .replace(/\.$/, ""),
    );
  const expected: Record<string, string> = {
    assets: rendered(balance.total_assets),
    liabilities: rendered(balance.total_liabilities),
    equity: rendered(new Decimal(balance.total_equity).plus(balance.retained_earnings).toString()),
    profit: rendered(income.net_income),
    stock: rendered(inventory.total_value, false),
  };
  for (const [name, value] of Object.entries(expected))
    await expect(page.getByTestId(`kpi-${name}`).locator(".num")).toContainText(value);
  const cashRequest = await Promise.all(
    ["101", "102"].map((prefix) =>
      get(
        `/api/v1/reports/cash-flow?start=${income.period_start}&end=${today}&cash_prefix=${prefix}`,
      ),
    ),
  );
  const cash = cashRequest.reduce((sum, r) => sum.plus(r.closing_balance), new Decimal(0));
  await expect(page.getByTestId("kpi-cash").locator(".num")).toContainText(
    rendered(cash.toString()),
  );
  expect(new Decimal(balance.total_assets).gt(cash)).toBe(true);
  await expect(page.getByTestId("dash-order-" + order.id)).toContainText(rendered("6000", false));
  await expect(page.getByTestId("dash-job-" + job.id)).toContainText("۲۵.۲۵");
  await expect(page.getByTestId("alert-stock")).toContainText(supplier.name);
  await expect(page.getByTestId("alert-trial")).toContainText("تراز بدهکار و بستانکار برابر است.");

  // Real SVG plots in both persisted themes; a resized container must resize its plot.
  for (const dark of [true, false]) {
    const currentlyDark = await page
      .locator("html")
      .evaluate((el) => el.classList.contains("dark"));
    if (currentlyDark !== dark)
      await page
        .getByRole("button", { name: dark ? "حالت تاریک" : "حالت روشن", exact: true })
        .click();
    for (const name of ["structure", "pnl", "sales", "stock"]) {
      const svg = page.getByTestId(`chart-${name}`).locator("svg");
      await expect(svg).toBeVisible();
      expect(await svg.locator("path").count()).toBeGreaterThan(0);
    }
    if (dark) await page.screenshot({ path: "test-results/dashboard-dark.png", fullPage: true });
  }
  await page.screenshot({ path: "test-results/dashboard-light.png", fullPage: true });
  const chart = page.getByTestId("chart-stock");
  await chart.evaluate((el) => {
    el.style.width = "280px";
  });
  await expect.poll(() => chart.locator("svg").getAttribute("width")).toBe("280");
  await chart.evaluate((el) => {
    el.style.width = "";
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(async () =>
      page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    )
    .toBe(true);
  await page.setViewportSize({ width: 1440, height: 900 });

  // A failed refresh must not turn into zero or false "healthy"; real data recovers.
  await page.route("**/api/v1/warehouse/summary", (route) =>
    route.fulfill({ status: 503, json: { detail: "test offline" } }),
  );
  await page.getByRole("button", { name: "تازه‌سازی داده‌ها" }).click();
  await expect(page.getByTestId("kpi-stock").getByRole("alert")).toBeVisible({ timeout: 15000 });
  await expect(page.getByTestId("kpi-stock").locator(".num")).toHaveCount(0);
  await expect(page.getByTestId("chart-structure")).toBeVisible();
  await page.unroute("**/api/v1/warehouse/summary");
  await page.getByTestId("kpi-stock").getByRole("button", { name: "تلاش دوباره" }).click();
  await expect(page.getByTestId("chart-stock")).toBeVisible();
  await page
    .getByTestId("alert-trial")
    .getByRole("button", { name: "بررسی اسناد حسابداری" })
    .click();
  await expect(page).toHaveURL(/\/journal$/);
  await page.goto("/");
  await page.getByTestId("alert-stock").getByRole("button", { name: "رسیدگی به موجودی" }).click();
  await expect(page).toHaveURL(/\/warehouse$/);
  // Menu audit expects its initial route to be the dashboard, in light mode.
  await page.goto("/");
}
