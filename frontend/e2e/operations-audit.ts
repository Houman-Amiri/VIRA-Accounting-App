/** Phase 7: use the actual forms and actual SQLite; no business-response mocks. */
import { expect, type Page } from "@playwright/test";
import { randomUUID } from "node:crypto";
import Decimal from "decimal.js";

type Item = { id: string; name: string; quantity: string };
export async function auditOperations(page: Page): Promise<void> {
  expect(process.env.VIRA_E2E_DISPOSABLE_DATABASE).toBe("1");
  const suffix = randomUUID().slice(0, 8);
  const base = `آزمایشی گردش کامل ${suffix}`;
  const waitWrite = (path: string, status = 201) =>
    page.waitForResponse(
      (r) =>
        new URL(r.url()).pathname === `/api/v1/${path}` &&
        r.request().method() === "POST" &&
        r.status() === status,
    );
  async function get(path: string) {
    const response = await page.request.get(`/api/v1/${path}`);
    expect(response.ok(), await response.text()).toBe(true);
    return response.json();
  }
  async function createItem(name: string, kind: "FILAMENT" | "PRODUCT"): Promise<Item> {
    await page.getByTestId("new-item-name").fill(name);
    await page.getByTestId("new-item-kind").selectOption(kind);
    await page.getByTestId("new-item-quantity").fill("۰");
    await page.getByTestId("new-item-price").fill(kind === "FILAMENT" ? "۱۰۰" : "۰");
    await page.getByTestId("new-item-min").fill("۰");
    const response = waitWrite("warehouse/items");
    await page.getByTestId("new-item-submit").click();
    const item = await (await response).json();
    await expect(page.getByTestId(`item-${item.id}`)).toContainText(name);
    return item;
  }
  async function receipt(item: Item, quantity: string) {
    await page.getByTestId(`move-${item.id}`).click();
    await page.getByTestId("movement-qty").fill(quantity);
    const response = waitWrite(`warehouse/items/${item.id}/movements`);
    await page.getByTestId("movement-submit").click();
    await response;
    await expect(page.getByTestId("movement-form")).toHaveCount(0);
  }
  await page.goto("/warehouse");
  const filament = await createItem(`${base} — فیلامنت`, "FILAMENT");
  const first = await createItem(`${base} — مدل اول`, "PRODUCT");
  const second = await createItem(`${base} — مدل دوم`, "PRODUCT");
  await receipt(filament, "۲۰");

  await page.getByRole("link", { name: "سفارش‌ها", exact: true }).click();
  await page.getByTestId("order-customer").fill(base);
  await page.getByTestId("order-channel").selectOption("direct");
  await page.getByRole("button", { name: "+ افزودن قلم" }).click();
  // Item 3: no grams/time on an order line; item 7: the product comes from the
  // warehouse, so the line is a select of stocked products, not a free name.
  for (const [i, product, qty, price, cost] of [
    [0, first, "۲", "۱۲۳.۴۵۶۷", "۲۳.۴۵۶۷"],
    [1, second, "۱", "۴۵۶.۱۲۳۴", "۵۶.۱۲۳۴"],
  ] as const) {
    await page.getByTestId(`line-product-${i}`).selectOption(product.id);
    await page.getByTestId(`line-quantity-${i}`).fill(qty);
    await page.getByTestId(`line-price-${i}`).fill(price);
    await page.getByTestId(`line-cost-${i}`).fill(cost);
  }
  const orderResponse = waitWrite("orders");
  await page.getByTestId("order-submit").click();
  const order = await (await orderResponse).json();
  await expect(page.getByTestId(`order-${order.id}`)).toContainText("۷۰۳.۰۳۶۸");

  async function createJob(index: number, product: Item) {
    await page.getByRole("link", { name: "تولید", exact: true }).click();
    await page.getByTestId("job-order").selectOption(order.id);
    await page.getByTestId("job-order-line").selectOption(order.items[index].id);
    await page.getByTestId("job-product-item").selectOption(product.id);
    // Item 6: each spool of the job is chosen with its own grams per piece.
    await page.getByTestId("job-spool-0-item").selectOption(filament.id);
    await page.getByTestId("job-spool-0-grams").fill(index === 0 ? "۱۲.۵" : "۲۰");
    const response = waitWrite("production/jobs");
    await page.getByTestId("job-submit").click();
    const job = await (await response).json();
    expect(job.order_item_id).toBe(order.items[index].id);
    expect(job.unit_price).toBe(order.items[index].unit_price);
    expect(job.unit_cost).toBe(order.items[index].unit_cost);
    expect(job.channel).toBe("direct");
    await expect(page.getByTestId(`job-${job.id}`)).toBeVisible();
    return job;
  }
  const a = await createJob(0, first);
  let response = waitWrite(`production/jobs/${a.id}/start`, 200);
  await page.getByTestId(`job-${a.id}-start`).click();
  await response;
  response = waitWrite(`production/jobs/${a.id}/finish`, 409);
  await page.getByTestId(`job-${a.id}-finish`).click();
  await response;
  await expect(page.getByTestId("production-message")).toContainText("فیلامنت کافی نیست");
  // Plain numbers: an exponent such as "2E+1" must never reach the user (item 5).
  await expect(page.getByTestId("production-message")).not.toContainText(/[BE][+-]\d/);
  let items: Item[] = (await get("warehouse/summary")).items;
  expect(new Decimal(items.find((i) => i.id === filament.id)!.quantity).eq(20)).toBe(true);
  expect(new Decimal(items.find((i) => i.id === first.id)!.quantity).eq(0)).toBe(true);
  expect((await get(`production/jobs/${a.id}`)).status).toBe("IN_PROGRESS");

  await page.getByRole("link", { name: "انبار", exact: true }).click();
  await receipt(filament, "۱۸۰");
  await page.getByRole("link", { name: "تولید", exact: true }).click();
  response = waitWrite(`production/jobs/${a.id}/finish`, 200);
  await page.getByTestId(`job-${a.id}-finish`).click();
  await response;
  await expect(page.getByTestId(`job-${a.id}`)).toContainText("تمام‌شده");
  expect((await get(`orders/${order.id}`)).status).toBe("IN_PRODUCTION");
  const b = await createJob(1, second);
  response = waitWrite(`production/jobs/${b.id}/finish`, 200);
  await page.getByTestId(`job-${b.id}-finish`).click();
  await response;
  expect((await get(`orders/${order.id}`)).status).toBe("READY");
  items = (await get("warehouse/summary")).items;
  expect(new Decimal(items.find((i) => i.id === filament.id)!.quantity).eq(155)).toBe(true);
  expect(new Decimal(items.find((i) => i.id === first.id)!.quantity).eq(2)).toBe(true);
  expect(new Decimal(items.find((i) => i.id === second.id)!.quantity).eq(1)).toBe(true);
  const movements: Array<{ kind: string; quantity: string; reference_id: string }> =
    await get("warehouse/movements");
  for (const [id, grams, count] of [
    [a.id, "25", "2"],
    [b.id, "20", "1"],
  ]) {
    const legs = movements.filter((m) => m.reference_id === id);
    expect(legs).toHaveLength(2);
    expect(new Decimal(legs.find((m) => m.kind === "OUT")!.quantity).eq(grams)).toBe(true);
    expect(new Decimal(legs.find((m) => m.kind === "IN")!.quantity).eq(count)).toBe(true);
  }
  const csrf = (await page.context().cookies()).find((c) => c.name === "vira_csrf")!.value;
  const repeat = await page.request.post(`/api/v1/production/jobs/${b.id}/finish`, {
    headers: { "X-CSRF-Token": decodeURIComponent(csrf) },
  });
  expect(repeat.status()).toBe(409);
  expect((await get("warehouse/movements")).length).toBe(movements.length);

  await page.getByRole("link", { name: "سفارش‌ها", exact: true }).click();
  const row = page.getByTestId(`order-${order.id}`);
  await expect(row).toContainText("آمادهٔ ارسال");
  const href = await row.getByRole("link", { name: "پیش‌فاکتور" }).getAttribute("href");
  expect(href).toBe(`/api/v1/orders/${order.id}/proforma.pdf`);
  const document = await page.request.get(href!);
  expect(document.status()).toBe(200);
  if (document.headers()["content-type"].startsWith("application/pdf"))
    expect((await document.body()).subarray(0, 4).toString()).toBe("%PDF");
  else {
    expect(await document.text()).toContain(base);
    expect(await document.text()).toContain("۷۰۳٫۰۳۶۸");
  }
}
