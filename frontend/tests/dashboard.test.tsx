import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { api } from "@/api/client";
import { DashboardPage } from "@/routes/dashboard";
import {
  chartToman,
  dashboardDate,
  inventoryValue,
  tehranDay,
  trialDifference,
} from "@/lib/dashboard";
import { faNumber } from "@/lib/fa";

const mocks = vi.hoisted(() => ({ navigate: vi.fn(), chart: vi.fn() }));
vi.mock("@tanstack/react-router", () => ({ useNavigate: () => mocks.navigate }));
vi.mock("@/api/client", async (original) => ({
  ...(await original<typeof import("@/api/client")>()),
  api: { GET: vi.fn() },
}));
vi.mock("@/components/echart", () => ({
  EChart: (props: Record<string, unknown>) => {
    mocks.chart(props);
    return <div data-testid={props["data-testid"] as string} />;
  },
}));

const data: Record<string, unknown> = {
  "/api/v1/reports/trial-balance": [{ debit: "1000.0001", credit: "1000.0001" }],
  "/api/v1/reports/balance-sheet": {
    total_assets: "8000",
    total_liabilities: "1000",
    total_equity: "5000",
    retained_earnings: "2000",
  },
  "/api/v1/reports/income-statement": {
    total_income: "3000",
    total_expenses: "1000",
    net_income: "2000",
  },
  "/api/v1/reports/cash-flow": { closing_balance: "4000" },
  "/api/v1/warehouse/summary": {
    total_value: "1200",
    items: [{ id: "stock", name: "فیلامنت آزمایشی", unit: "G", quantity: "2", unit_price: "600" }],
  },
  "/api/v1/warehouse/alarms": [
    {
      item_id: "stock",
      name: "فیلامنت آزمایشی",
      unit: "G",
      quantity: "2",
      min_quantity: "3",
      suggested_supplier: "فروشندهٔ پیشنهادی",
    },
  ],
  "/api/v1/production/summary": {
    planned: 1,
    in_progress: 2,
    filament_grams_planned: "12.5",
    jobs: [
      {
        id: "job",
        job_number: 7,
        product_name: "مدل آزمایشی",
        status: "PLANNED",
        quantity: "2.5",
        filament_grams: "10.1",
      },
    ],
  },
  "/api/v1/orders": [
    {
      id: "order",
      order_number: 8,
      order_date: "2026-10-16",
      customer_name: "مشتری آزمایشی",
      status: "NEW",
      total: "1200",
    },
  ],
  "/api/v1/orders/summary": { new: 201, confirmed: 2, total: 210 },
  "/api/v1/orders/reports/sales": { rows: [{ period: "2026-10-16", revenue: "1200" }] },
  "/api/v1/health/live": { status: "ok" },
};
const clients: QueryClient[] = [];
function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  clients.push(client);
  render(
    <QueryClientProvider client={client}>
      <DashboardPage />
    </QueryClientProvider>,
  );
  return client;
}
beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-16T12:00:00Z"));
  vi.clearAllMocks();
  vi.mocked(api.GET).mockImplementation((async (path: string) => ({
    data: data[path],
    response: new Response(),
  })) as typeof api.GET);
});
afterEach(() => {
  cleanup();
  clients.splice(0).forEach((c) => c.clear());
  vi.useRealTimers();
});

it("uses the Tehran civil day even before UTC midnight and at Nowruz", () => {
  expect(dashboardDate("2026-03-21")).toBe("۱۴۰۵/۰۱/۰۱");
  expect(tehranDay(new Date("2026-03-20T21:00:00Z"))).toBe("2026-03-21");
  expect(tehranDay(new Date("2026-10-15T21:00:00Z"))).toBe("2026-10-16");
});
it("keeps money exact until plotting, with one unit conversion", () => {
  expect(chartToman("12345.6789")).toBe(1234.56789);
  expect(chartToman("12345.6789", "TOMAN")).toBe(12345.6789);
  expect(inventoryValue({ quantity: "100000000000.0001", unit_price: "3.0001" })).toBe(
    "300010000000.0003",
  );
  expect(trialDifference([{ debit: "9999999999999.9999", credit: "9999999999999.9998" }])).toBe(
    "0.0001",
  );
});

it("shows five real KPIs, three plots, supplier/action links, and correct order units", async () => {
  mount();
  await waitFor(() => expect(screen.getByTestId("kpi-assets")).toHaveTextContent(faNumber("800")));
  expect(screen.getByLabelText("شاخص‌های کلیدی").children).toHaveLength(5);
  expect(screen.getByTestId("kpi-equity")).toHaveTextContent(faNumber("700"));
  // item 10: the warehouse-value card and the 8-item value chart are gone
  expect(screen.queryByTestId("kpi-stock")).not.toBeInTheDocument();
  expect(screen.queryByText("ارزش موجودی انبار")).not.toBeInTheDocument();
  expect(screen.queryByTestId("chart-stock")).not.toBeInTheDocument();
  expect(screen.queryByText(/ارزش ۸ قلم/)).not.toBeInTheDocument();
  expect(screen.getByTestId("kpi-cash")).toHaveTextContent(faNumber("800"));
  expect(screen.getByTestId("dash-order-order")).toHaveTextContent(faNumber("1,200"));
  expect(screen.getByTestId("alert-orders")).toHaveTextContent(faNumber("203"));
  expect(screen.getByTestId("alert-stock")).toHaveTextContent("فروشندهٔ پیشنهادی");
  expect(screen.getByTestId("dash-job-job")).toHaveTextContent(faNumber("25.25"));
  for (const id of ["chart-structure", "chart-pnl", "chart-sales"])
    expect(screen.getByTestId(id)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "رسیدگی به موجودی" }));
  expect(mocks.navigate).toHaveBeenCalledWith({ to: "/warehouse" });
  expect(
    (vi.mocked(api.GET).mock.calls as unknown as Array<[string]>).some(
      ([path]) => path === "/api/v1/system/check-updates",
    ),
  ).toBe(false);
});

it("requests consistent as-of/year-to-date periods and only cash/bank prefixes", async () => {
  mount();
  await screen.findByTestId("chart-sales");
  const calls = vi.mocked(api.GET).mock.calls as unknown as Array<
    [string, { params?: { query: Record<string, string> } }?]
  >;
  const params = (path: string) =>
    calls.filter(([p]) => p === path).map(([, opts]) => opts?.params?.query);
  expect(params("/api/v1/reports/trial-balance")).toEqual([{ as_of: "2026-10-16" }]);
  expect(params("/api/v1/reports/balance-sheet")).toEqual([{ as_of: "2026-10-16" }]);
  expect(params("/api/v1/reports/income-statement")).toEqual([
    { start: "2026-03-21", end: "2026-10-16" },
  ]);
  expect(params("/api/v1/reports/cash-flow").map((q) => q?.cash_prefix)).toEqual(["101", "102"]);
  expect(params("/api/v1/orders/reports/sales")).toEqual([
    { period: "daily", date_from: "2026-09-17", date_to: "2026-10-16" },
  ]);
});

it("converts plot values only once and fills all 30 dates without altering revenue", async () => {
  mount();
  await screen.findByTestId("chart-sales");
  const props = (id: string) =>
    mocks.chart.mock.calls
      .map(([p]) => p)
      .reverse()
      .find((p) => p["data-testid"] === id);
  const theme = { primary: "#123", muted: "#456", border: "#789" };
  expect(props("chart-structure").buildOption(theme).series[0].data).toEqual([800, 100, 700]);
  expect(props("chart-pnl").buildOption(theme).series[0].data).toEqual([300, 100, 200]);
  const daily = props("chart-sales").buildOption(theme).series[0].data;
  expect(daily).toHaveLength(30);
  expect(daily[29]).toBe(1200);
  expect(daily.slice(0, 29).every((v: number) => v === 0)).toBe(true);
});

it("loading has no money, healthy alert, empty-queue claim or plot", () => {
  vi.mocked(api.GET).mockImplementation(() => new Promise(() => {}));
  mount();
  expect(screen.getAllByRole("status").length).toBeGreaterThan(1);
  expect(screen.getByTestId("kpi-assets")).not.toHaveTextContent("تومان");
  expect(screen.queryByText("تراز بدهکار و بستانکار برابر است.")).not.toBeInTheDocument();
  expect(screen.queryByText("هنوز سفارشی ثبت نشده است.")).not.toBeInTheDocument();
  expect(screen.queryByTestId("chart-structure")).not.toBeInTheDocument();
});

it("one failed query hides its stale values; other sections remain usable and retry recovers", async () => {
  const client = mount();
  await screen.findByTestId("chart-sales");
  vi.mocked(api.GET).mockImplementation((async (path: string) => {
    if (path === "/api/v1/reports/cash-flow") throw new Error("offline");
    return { data: data[path], response: new Response() };
  }) as typeof api.GET);
  await client.invalidateQueries({ queryKey: ["dashboard", "cash"] });
  await waitFor(() =>
    expect(within(screen.getByTestId("kpi-cash")).getByRole("alert")).toBeInTheDocument(),
  );
  expect(screen.getByTestId("kpi-cash")).not.toHaveTextContent(faNumber("800"));
  expect(screen.getByTestId("chart-structure")).toBeInTheDocument();
  vi.mocked(api.GET).mockImplementation((async (path: string) => ({
    data: data[path],
    response: new Response(),
  })) as typeof api.GET);
  fireEvent.click(
    within(screen.getByTestId("kpi-cash")).getByRole("button", { name: "تلاش دوباره" }),
  );
  await waitFor(() => expect(screen.getByTestId("kpi-cash")).toHaveTextContent(faNumber("800")));
});

it("failed trial/alarms/orders/production never claim healthy or empty", async () => {
  vi.mocked(api.GET).mockRejectedValue(new Error("offline"));
  mount();
  await waitFor(() =>
    expect(within(screen.getByTestId("alert-trial")).getByRole("alert")).toBeInTheDocument(),
  );
  expect(screen.queryByText("تراز بدهکار و بستانکار برابر است.")).not.toBeInTheDocument();
  expect(screen.queryByText("هیچ قلمی در حداقل موجودی یا کمتر نیست.")).not.toBeInTheDocument();
  expect(screen.queryByText("هنوز سفارشی ثبت نشده است.")).not.toBeInTheDocument();
  expect(screen.queryByText("کار تولیدی در جریان نیست.")).not.toBeInTheDocument();
  expect(screen.getByTestId("dashboard-health")).toHaveTextContent("ناموفق");
});

it("flags even a four-decimal trial difference instead of treating it as zero", async () => {
  vi.mocked(api.GET).mockImplementation((async (path: string) => ({
    data: path.endsWith("trial-balance") ? [{ debit: "1.0001", credit: "1.0000" }] : data[path],
    response: new Response(),
  })) as typeof api.GET);
  mount();
  await screen.findByText("اختلاف در تراز حسابداری");
});

it("successful empty data shows genuine zeroes and three honest empty chart panels", async () => {
  const empty: Record<string, unknown> = {
    ...data,
    "/api/v1/reports/trial-balance": [],
    "/api/v1/reports/balance-sheet": {
      total_assets: "0",
      total_liabilities: "0",
      total_equity: "0",
      retained_earnings: "0",
    },
    "/api/v1/reports/income-statement": { total_income: "0", total_expenses: "0", net_income: "0" },
    "/api/v1/reports/cash-flow": { closing_balance: "0" },
    "/api/v1/warehouse/summary": { total_value: "0", items: [] },
    "/api/v1/warehouse/alarms": [],
    "/api/v1/production/summary": {
      planned: 0,
      in_progress: 0,
      filament_grams_planned: "0",
      jobs: [],
    },
    "/api/v1/orders": [],
    "/api/v1/orders/summary": { new: 0, confirmed: 0, total: 0 },
    "/api/v1/orders/reports/sales": { rows: [] },
  };
  vi.mocked(api.GET).mockImplementation((async (path: string) => ({
    data: empty[path],
    response: new Response(),
  })) as typeof api.GET);
  mount();
  await screen.findByText("تراز بدهکار و بستانکار برابر است.");
  expect(screen.getByTestId("kpi-assets")).toHaveTextContent("۰تومان");
  expect(screen.getAllByText("برای این بازه مبلغ غیرصفر ثبت نشده است.")).toHaveLength(3);
  expect(screen.queryByTestId("chart-structure")).not.toBeInTheDocument();
  expect(screen.getByText("هنوز سفارشی ثبت نشده است.")).toBeInTheDocument();
  expect(screen.getByText("کار تولیدی در جریان نیست.")).toBeInTheDocument();
});
