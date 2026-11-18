import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
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
  Link: ({ to, children }: { to: string; children: React.ReactNode }) => (
    <a href={to}>{children}</a>
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
