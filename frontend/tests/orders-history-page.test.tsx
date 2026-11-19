import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { api } from "@/api/client";
import { OrdersHistoryPage } from "@/routes/orders-history";
import { CalendarProvider } from "@/lib/calendar-settings";

/**
 * Item 7 of the owner's list: finished and cancelled orders move to
 * «تاریخچهٔ سفارشات»; the page reads them with status_group=history and never
 * offers a status change or a delete.
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

const DELIVERED = {
  id: "h1",
  order_number: 9,
  order_date: "2026-10-01",
  customer_name: "مشتری قدیمی",
  customer_phone: "09121111111",
  customer_address: null,
  channel: "marketplace",
  status: "DELIVERED",
  notes: null,
  version_id: 3,
  total: "500000",
  total_cost: "200000",
  profit: "300000",
  items: [
    {
      id: "i1",
      product_name: "پایه موبایل",
      variant: "plain",
      quantity: "2",
      unit_price: "250000",
      unit_cost: "100000",
      inventory_item_id: "item-1",
    },
  ],
  warnings: [],
};

const CANCELLED = {
  ...DELIVERED,
  id: "h2",
  order_number: 10,
  status: "CANCELLED",
  items: [
    {
      ...DELIVERED.items[0],
      id: "i2",
      product_name: "مجسمه",
      variant: "chain",
      quantity: "1",
    },
  ],
};

const data: Record<string, unknown> = {
  "/api/v1/orders": [DELIVERED, CANCELLED],
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
        <OrdersHistoryPage />
      </CalendarProvider>
    </QueryClientProvider>,
  );
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

it("reads only closed orders and shows their final status", async () => {
  mount();
  await screen.findByTestId("history-order-h1");
  const calls = vi.mocked(api.GET).mock.calls as unknown as Array<
    [string, { params?: { query?: Record<string, unknown> } }]
  >;
  const orderCall = calls.find(([path]) => path === "/api/v1/orders");
  expect(orderCall?.[1].params?.query).toMatchObject({ status_group: "history" });

  expect(screen.getByTestId("history-order-h1")).toHaveTextContent("تحویل‌شده");
  expect(screen.getByTestId("history-order-h2")).toHaveTextContent("لغو‌شده");
  // read-only: no status actions, no deletion, no editing
  expect(screen.queryByRole("button", { name: "حذف" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "ویرایش" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "تأییدشده" })).not.toBeInTheDocument();
});

it("expands the archived items of one order", async () => {
  mount();
  fireEvent.click(await screen.findByTestId("history-order-h2-items-toggle"));
  const panel = screen.getByTestId("history-order-h2-items");
  const lines = within(panel).getByRole("list", { name: "اقلام سفارش" });
  expect(lines).toHaveTextContent("مجسمه");
  expect(lines).toHaveTextContent("(زنجیر)");
  expect(lines).toHaveTextContent("×۱");
});

it("links back to the live orders page", async () => {
  mount();
  expect(await screen.findByTestId("orders-history-back")).toHaveAttribute("href", "/orders");
});
