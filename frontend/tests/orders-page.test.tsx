import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { api } from "@/api/client";
import { OrdersPage } from "@/routes/orders";
import { CalendarProvider } from "@/lib/calendar-settings";

/**
 * «اقلام» is a dropdown and every line of the order form can be removed. Both
 * are layout changes — no invented data, no new request — so these tests pin the
 * interaction and the payload that still goes to the same endpoint.
 */
vi.mock("@/api/client", async (original) => ({
  ...(await original<typeof import("@/api/client")>()),
  api: { GET: vi.fn(), POST: vi.fn(), PATCH: vi.fn(), DELETE: vi.fn() },
}));
vi.mock("@tanstack/react-router", () => ({
  Link: ({
    to,
    children,
    ...rest
  }: { to: string; children: React.ReactNode } & Record<string, unknown>) => (
    <a href={to} {...rest}>
      {children}
    </a>
  ),
}));

const ORDER = {
  id: "o1",
  order_number: 12,
  order_date: "2026-10-14",
  customer_name: "مشتری آزمایشی",
  customer_phone: "09120000000",
  channel: "direct",
  status: "NEW",
  total: "900000",
  profit: "300000",
  version_id: 1,
  items: [
    {
      id: "i1",
      product_name: "پایه موبایل",
      variant: "plain",
      quantity: "2",
      unit_price: "200000",
      unit_cost: "100000",
      inventory_item_id: null,
    },
    {
      id: "i2",
      product_name: "مجسمه",
      variant: "chain",
      quantity: "1",
      unit_price: "500000",
      unit_cost: "300000",
      inventory_item_id: "item-1",
    },
  ],
  warnings: ["«پایه موبایل»: سفارش ۲ عدد، موجودی ۰ عدد — کمبود باید تولید شود."],
};

const data: Record<string, unknown> = {
  "/api/v1/orders": [ORDER],
  "/api/v1/warehouse/items": [
    {
      id: "item-1",
      name: "مجسمه",
      kind: "PRODUCT",
      unit: "PCS",
      quantity: "5",
      unit_price: "500000",
    },
  ],
  "/api/v1/orders/reports/sales": { rows: [], orders: 0, revenue: "0", cost: "0", profit: "0" },
  "/api/v1/settings/pricing/variables": [
    {
      id: "design",
      name: "نرخ طراحی",
      scope: "PER_UNIT",
      basis: "AMOUNT",
      allocation: "SPLIT",
      value: "50000.0000",
      is_active: true,
      is_design_rate: true,
      position: 0,
      created_at: "2026-10-16T00:00:00Z",
      updated_at: "2026-10-16T00:00:00Z",
    },
    {
      id: "pack",
      name: "بسته‌بندی",
      scope: "PER_UNIT",
      basis: "AMOUNT",
      allocation: "SPLIT",
      value: "700000.0000",
      is_active: true,
      is_design_rate: false,
      position: 1,
      created_at: "2026-10-16T00:00:00Z",
      updated_at: "2026-10-16T00:00:00Z",
    },
  ],
  "/api/v1/settings/calendar": {
    calendar: "jalali",
    version_id: 0,
    timezone: "Asia/Tehran",
    scope: "installation",
  },
};

const clients: QueryClient[] = [];

function mount() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity }, mutations: { retry: false } },
  });
  clients.push(client);
  client.setQueryData(["calendar-settings"], {
    calendar: "jalali",
    version_id: 0,
    timezone: "Asia/Tehran",
    scope: "installation",
  });
  render(
    <QueryClientProvider client={client}>
      <CalendarProvider enabled>
        <OrdersPage />
      </CalendarProvider>
    </QueryClientProvider>,
  );
  return client;
}

beforeEach(() => {
  vi.mocked(api.GET).mockImplementation((async (path: string) => ({
    data: data[path],
    response: new Response(),
  })) as typeof api.GET);
  vi.mocked(api.PATCH).mockResolvedValue({ data: {}, response: new Response() } as never);
  vi.mocked(api.DELETE).mockResolvedValue({ data: {}, response: new Response() } as never);
});

afterEach(() => {
  cleanup();
  clients.splice(0).forEach((client) => client.clear());
  vi.clearAllMocks();
});

it("keeps the items column collapsed until the owner opens it", async () => {
  mount();
  const toggle = await screen.findByTestId("order-o1-items-toggle");
  expect(toggle).toHaveTextContent("۲");
  // the rows themselves are not in the document while the menu is closed
  expect(screen.queryByTestId("order-o1-items")).not.toBeInTheDocument();
  expect(screen.queryByText("پایه موبایل")).not.toBeInTheDocument();
  expect(toggle).toHaveAttribute("aria-expanded", "false");

  fireEvent.click(toggle);

  const panel = screen.getByTestId("order-o1-items");
  const lines = within(panel).getByRole("list", { name: "اقلام سفارش" });
  expect(within(lines).getAllByRole("listitem")).toHaveLength(2);
  expect(lines).toHaveTextContent("پایه موبایل");
  expect(lines).toHaveTextContent("مجسمه");
  expect(lines).toHaveTextContent("(زنجیر)");
  expect(within(panel).getByText("بدون موجودی انبار")).toBeInTheDocument();
  // the shortage is part of the same dropdown, not of the table row
  expect(within(panel).getByTestId("order-o1-warning")).toHaveTextContent("کمبود باید تولید شود");
  expect(toggle).toHaveAttribute("aria-expanded", "true");

  fireEvent.click(toggle);
  expect(screen.queryByTestId("order-o1-items")).not.toBeInTheDocument();
});

it("removes a line from the order form and can add another one", async () => {
  mount();
  fireEvent.mouseDown(screen.getByTestId("orders-tab-form"), { button: 0, ctrlKey: false });
  await screen.findByTestId("line-0");
  expect(screen.getByTestId("line-remove-0")).toBeInTheDocument();
  fireEvent.click(screen.getByTestId("line-add"));
  expect(screen.getByTestId("line-1")).toBeInTheDocument();

  fireEvent.change(screen.getByTestId("line-name-0"), { target: { value: "ردیف اول" } });
  fireEvent.change(screen.getByTestId("line-name-1"), { target: { value: "ردیف دوم" } });

  // deleting the first row keeps the second one, with its own values
  fireEvent.click(screen.getByTestId("line-remove-0"));
  expect(screen.queryByTestId("line-1")).not.toBeInTheDocument();
  expect(screen.getByTestId("line-name-0")).toHaveValue("ردیف دوم");
});

it("never leaves the form without a row to fill", async () => {
  mount();
  fireEvent.mouseDown(screen.getByTestId("orders-tab-form"), { button: 0, ctrlKey: false });
  await screen.findByTestId("line-0");
  // a lone, incomplete row cannot be removed — there must always be one to fill
  expect(screen.getByTestId("line-remove-0")).toBeDisabled();
  fireEvent.change(screen.getByTestId("line-name-0"), { target: { value: "تنها ردیف" } });
  fireEvent.change(screen.getByTestId("line-price-0"), { target: { value: "100000" } });
  expect(screen.getByTestId("line-remove-0")).toBeEnabled();
  fireEvent.click(screen.getByTestId("line-remove-0"));
  expect(screen.getByTestId("line-0")).toBeInTheDocument();
  expect(screen.getByTestId("line-name-0")).toHaveValue("");
  expect(screen.getByTestId("line-remove-0")).toBeDisabled();
});

it("asks only for the active orders and links to the history page", async () => {
  mount();
  const link = await screen.findByTestId("orders-history-link");
  expect(link).toHaveAttribute("href", "/orders/history");
  const select = screen.getByTestId("orders-status");
  const options = within(select)
    .getAllByRole("option")
    .map((o) => o.textContent);
  expect(options).toEqual(["همه", "جدید", "تأییدشده", "در حال تولید", "آمادهٔ ارسال"]);
});

it("edits an unconfirmed order's lines and specs in place", async () => {
  mount();
  fireEvent.click(await screen.findByTestId("order-o1-edit"));
  expect(screen.getByText("ویرایش سفارش #۱۲")).toBeInTheDocument();
  // the saved lines are loaded into the same form
  expect(screen.getByTestId("line-name-0")).toHaveValue("پایه موبایل");
  expect(screen.getByTestId("line-quantity-0")).toHaveValue("2");
  expect(screen.getByTestId("line-name-1")).toHaveValue("مجسمه");

  fireEvent.change(screen.getByTestId("line-quantity-0"), { target: { value: "4" } });
  fireEvent.change(screen.getByTestId("order-customer"), {
    target: { value: "مشتری ویرایش‌شده" },
  });
  fireEvent.click(screen.getByTestId("line-add"));
  fireEvent.change(screen.getByTestId("line-name-2"), { target: { value: "قلم سوم" } });
  fireEvent.change(screen.getByTestId("line-price-2"), { target: { value: "150000" } });
  fireEvent.click(screen.getByTestId("order-submit"));

  await waitFor(() => expect(api.PATCH).toHaveBeenCalled());
  const calls = vi.mocked(api.PATCH).mock.calls as unknown as Array<
    [string, { params: { path: { order_id: string } }; body: Record<string, unknown> }]
  >;
  expect(calls[0][0]).toBe("/api/v1/orders/{order_id}");
  expect(calls[0][1].params.path.order_id).toBe("o1");
  expect(calls[0][1].body).toMatchObject({
    version_id: 1,
    customer_name: "مشتری ویرایش‌شده",
    channel: "direct",
  });
  const body = calls[0][1].body as { items: Array<Record<string, string>> };
  expect(body.items).toHaveLength(3);
  expect(body.items[0]).toMatchObject({ product_name: "پایه موبایل", quantity: "4" });
  expect(body.items[2]).toMatchObject({ product_name: "قلم سوم", unit_price: "150000" });
});

it("deletes an unconfirmed order only after an explicit confirmation", async () => {
  mount();
  fireEvent.click(await screen.findByTestId("order-o1-delete"));
  expect(api.DELETE).not.toHaveBeenCalled();
  fireEvent.click(screen.getByTestId("order-o1-delete-confirm"));
  await waitFor(() => expect(api.DELETE).toHaveBeenCalled());
  const calls = vi.mocked(api.DELETE).mock.calls as unknown as Array<
    [string, { params: { path: { order_id: string } } }]
  >;
  expect(calls[0][0]).toBe("/api/v1/orders/{order_id}");
  expect(calls[0][1].params.path.order_id).toBe("o1");
});

it("offers neither editing nor deleting once the order is confirmed", async () => {
  vi.mocked(api.GET).mockImplementation((async (path: string) => ({
    data: path === "/api/v1/orders" ? [{ ...ORDER, status: "CONFIRMED" }] : data[path],
    response: new Response(),
  })) as typeof api.GET);
  mount();
  await screen.findByTestId("order-o1");
  expect(screen.queryByTestId("order-o1-edit")).not.toBeInTheDocument();
  expect(screen.queryByTestId("order-o1-delete")).not.toBeInTheDocument();
});

it("adds design hours and a per-line variable to the saved line", async () => {
  const post = vi
    .spyOn(api, "POST")
    .mockResolvedValue({ data: ORDER, response: new Response() } as never);
  mount();
  fireEvent.mouseDown(screen.getByTestId("orders-tab-form"), { button: 0, ctrlKey: false });
  await screen.findByTestId("line-0");
  fireEvent.change(screen.getByTestId("line-name-0"), { target: { value: "پایه موبایل" } });
  fireEvent.change(screen.getByTestId("line-price-0"), { target: { value: "200000" } });
  fireEvent.change(screen.getByTestId("order-customer"), { target: { value: "مشتری" } });

  // «هزینهٔ طراحی»: ۳ ساعت × نرخ ۵۰٬۰۰۰ = ۱۵۰٬۰۰۰
  fireEvent.click(await screen.findByTestId("line-design-add-0"));
  fireEvent.change(screen.getByTestId("line-design-hours-0"), { target: { value: "3" } });
  await waitFor(() => expect(screen.getByTestId("line-charges-0")).toHaveTextContent("۱۵۰٬۰۰۰"));

  // «افزودن متغیر»: تعداد ضرب‌در مبلغ تنظیمات
  fireEvent.change(screen.getByTestId("line-variable-add-0"), { target: { value: "pack" } });
  fireEvent.change(screen.getByTestId("line-variable-amount-0-1"), {
    target: { value: "2" },
  });
  expect(screen.getByTestId("line-charges-0")).toHaveTextContent("۱٬۴۰۰٬۰۰۰");

  fireEvent.click(screen.getByTestId("order-submit"));
  await waitFor(() => expect(post).toHaveBeenCalled());
  const body = (
    post.mock.calls as unknown as Array<[string, { body: Record<string, unknown> }]>
  )[0][1].body as { items: Array<{ charges: Array<Record<string, string>> }> };
  expect(body.items[0].charges).toEqual([
    expect.objectContaining({ kind: "DESIGN", hours: "3" }),
    expect.objectContaining({ kind: "VARIABLE", variable_id: "pack", quantity: "2", amount: "0" }),
  ]);
});

it("applies fixed and percentage discounts to products plus charges and saves the chosen mode", async () => {
  const post = vi
    .spyOn(api, "POST")
    .mockResolvedValue({ data: ORDER, response: new Response() } as never);
  mount();
  fireEvent.mouseDown(screen.getByTestId("orders-tab-form"), { button: 0, ctrlKey: false });
  await screen.findByTestId("line-0");
  fireEvent.change(screen.getByTestId("line-name-0"), { target: { value: "پایه" } });
  fireEvent.change(screen.getByTestId("line-price-0"), { target: { value: "200000" } });
  fireEvent.change(screen.getByTestId("order-customer"), { target: { value: "مشتری" } });
  fireEvent.click(await screen.findByTestId("line-design-add-0"));
  fireEvent.change(screen.getByTestId("line-design-hours-0"), { target: { value: "3" } });
  // ۲۰۰٬۰۰۰ کالا + ۱۵۰٬۰۰۰ طراحی = ۳۵۰٬۰۰۰
  fireEvent.change(screen.getByTestId("order-discount-value"), { target: { value: "۱۰۰۰۰۰" } });
  expect(screen.getByTestId("order-final-total")).toHaveTextContent("۲۵۰٬۰۰۰");
  fireEvent.change(screen.getByTestId("order-discount-type"), { target: { value: "PERCENT" } });
  expect(screen.getByTestId("order-discount-value")).toHaveValue("");
  fireEvent.change(screen.getByTestId("order-discount-value"), { target: { value: "۱۰" } });
  expect(screen.getByTestId("order-discount")).toHaveTextContent("۳۵٬۰۰۰");
  expect(screen.getByTestId("order-final-total")).toHaveTextContent("۳۱۵٬۰۰۰");
  fireEvent.click(screen.getByTestId("order-submit"));
  await waitFor(() => expect(post).toHaveBeenCalled());
  const body = (post.mock.calls[0][1] as unknown as { body: Record<string, unknown> }).body;
  expect(body).toMatchObject({ discount_type: "PERCENT", discount_value: "10" });
  await waitFor(() =>
    expect(screen.getByTestId("orders-tab-list")).toHaveAttribute("aria-selected", "true"),
  );
  fireEvent.mouseDown(screen.getByTestId("orders-tab-form"), { button: 0, ctrlKey: false });
  expect(screen.getByTestId("order-discount-value")).toHaveValue("");
  expect(screen.getByTestId("order-discount-type")).toHaveValue("AMOUNT");
});

it("rejects invalid discounts and preserves a saved discount while editing", async () => {
  const saved = {
    ...ORDER,
    discount_type: "PERCENT",
    discount_value: "10.0000",
    discount_amount: "90000",
  };
  vi.mocked(api.GET).mockImplementation((async (path: string) => ({
    data: path === "/api/v1/orders" ? [saved] : data[path],
    response: new Response(),
  })) as typeof api.GET);
  mount();
  fireEvent.click(await screen.findByTestId("order-o1-edit"));
  expect(screen.getByTestId("order-discount-type")).toHaveValue("PERCENT");
  expect(screen.getByTestId("order-discount-value")).toHaveValue("10.0000");
  expect(screen.getByTestId("order-final-total")).toHaveTextContent("۸۱۰٬۰۰۰");
  fireEvent.change(screen.getByTestId("order-discount-value"), { target: { value: "101" } });
  expect(screen.getByTestId("order-discount-error")).toHaveTextContent("۱۰۰");
  expect(screen.getByTestId("order-submit")).toBeDisabled();
  fireEvent.change(screen.getByTestId("order-discount-value"), { target: { value: "-1" } });
  expect(screen.getByTestId("order-submit")).toBeDisabled();
  fireEvent.change(screen.getByTestId("order-discount-type"), { target: { value: "AMOUNT" } });
  fireEvent.change(screen.getByTestId("order-discount-value"), { target: { value: "900001" } });
  expect(screen.getByTestId("order-discount-error")).toHaveTextContent("بیشتر از جمع سفارش");
  expect(screen.getByTestId("order-submit")).toBeDisabled();
  fireEvent.change(screen.getByTestId("order-discount-value"), { target: { value: "90000" } });
  expect(screen.getByTestId("order-final-total")).toHaveTextContent("۸۱۰٬۰۰۰");
  fireEvent.click(screen.getByTestId("order-submit"));
  await waitFor(() => expect(api.PATCH).toHaveBeenCalled());
  const body = (
    vi.mocked(api.PATCH).mock.calls[0][1] as unknown as { body: Record<string, unknown> }
  ).body;
  expect(body).toMatchObject({ discount_type: "AMOUNT", discount_value: "90000" });
});

it("keeps a draft intact while switching tabs", async () => {
  mount();
  fireEvent.mouseDown(screen.getByTestId("orders-tab-form"), { button: 0 });
  fireEvent.change(screen.getByTestId("order-customer"), { target: { value: "مشتری" } });
  fireEvent.change(screen.getByTestId("line-name-0"), { target: { value: "بتمن" } });
  fireEvent.mouseDown(screen.getByTestId("orders-tab-list"), { button: 0 });
  expect(screen.queryByTestId("line-name-0")).not.toBeInTheDocument();
  fireEvent.mouseDown(screen.getByTestId("orders-tab-form"), { button: 0 });
  expect(screen.getByTestId("order-customer")).toHaveValue("مشتری");
  expect(screen.getByTestId("line-name-0")).toHaveValue("بتمن");
});

it("restores the selected row, keeps other data and replaces old calculated one-time costs", async () => {
  const charge = (name: string, amount: string) => ({
    kind: "VARIABLE",
    variable_id: "",
    name,
    quantity: "",
    hours: "",
    amount,
    legacy: true,
  });
  const line = (name: string) => ({
    inventory_item_id: "",
    product_name: name,
    variant: "plain",
    quantity: "2",
    unit_price: "100",
    unit_cost: "0",
    notes: "یادداشت پیشین",
    charges: [],
  });
  sessionStorage.setItem(
    "noa.order-pricing-transfer.v1",
    JSON.stringify({
      form: {
        order_date: "2026-10-14",
        customer_name: "مشتری بتمن",
        customer_phone: "123",
        customer_address: "",
        notes: "حفظ شود",
        discount_type: "AMOUNT",
        discount_value: "10",
        items: [
          line("قلم دیگر"),
          { ...line("بتمن"), charges: [charge("دستی", "30"), charge("قیمت‌گذاری: ارسال", "50")] },
        ],
      },
      editing: null,
      lineIndex: 1,
      result: {
        quantity: "3",
        unitPrice: "4000.0000",
        unitCost: "2000.0000",
        details: "جزئیات قیمت‌گذاری:\nثابت آزمون: 100 تومان/عدد",
        oneTime: [{ name: "ارسال", amount: "100.0000" }],
      },
    }),
  );
  mount();
  expect(screen.getByTestId("orders-tab-form")).toHaveAttribute("aria-selected", "true");
  expect(screen.getByTestId("order-customer")).toHaveValue("مشتری بتمن");
  expect(screen.getByTestId("line-name-0")).toHaveValue("قلم دیگر");
  expect(screen.getByTestId("line-name-1")).toHaveValue("بتمن");
  expect(screen.getByTestId("line-price-1")).toHaveValue("4000.0000");
  expect(screen.getByTestId("line-quantity-1")).toHaveValue("3");
  expect(screen.getByTestId("line-pricing-details-1")).toHaveTextContent("یادداشت پیشین");
  expect(screen.getByTestId("line-pricing-details-1")).toHaveTextContent("ثابت آزمون");
  expect(screen.getByTestId("line-charges-1")).toHaveTextContent("دستی");
  expect(
    within(screen.getByTestId("line-charges-1")).getAllByText("قیمت‌گذاری: ارسال"),
  ).toHaveLength(1);
  expect(sessionStorage.getItem("noa.order-pricing-transfer.v1")).toBeNull();
});
