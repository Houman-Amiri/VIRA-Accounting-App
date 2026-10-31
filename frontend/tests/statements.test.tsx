import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { api } from "@/api/client";
import { StatementsPage, balanceSheetDifference } from "@/routes/statements";

vi.mock("@/api/client", async (original) => ({
  ...(await original<typeof import("@/api/client")>()),
  api: { GET: vi.fn() },
}));
vi.mock("@/components/echart", () => ({
  EChart: (props: Record<string, unknown>) => <div data-testid={props["data-testid"] as string} />,
}));

const node = (over: Record<string, unknown>) => ({
  account_id: over.code as string,
  code: "1000",
  name: "حساب",
  account_type: "ASSET",
  is_placeholder: false,
  amount: "0.0000",
  children: [],
  ...over,
});

const reports: Record<string, unknown> = {
  "/api/v1/reports/balance-sheet": {
    as_of: "2026-10-31",
    assets: [
      node({
        code: "1",
        name: "دارایی‌ها",
        account_type: "ASSET",
        is_placeholder: true,
        amount: "90000000",
        children: [
          node({ code: "1010", name: "صندوق", amount: "40000000" }),
          node({ code: "1020", name: "بانک", amount: "50000000" }),
        ],
      }),
    ],
    liabilities: [
      node({
        code: "2010",
        name: "حساب‌های پرداختنی",
        account_type: "LIABILITY",
        amount: "20000000",
      }),
    ],
    equity: [node({ code: "3010", name: "سرمایه", account_type: "EQUITY", amount: "60000000" })],
    total_assets: "90000000.0000",
    total_liabilities: "20000000.0000",
    total_equity: "60000000.0000",
    retained_earnings: "10000000.0000",
  },
  "/api/v1/reports/income-statement": {
    period_start: "2026-03-21",
    period_end: "2026-10-31",
    income: [
      node({ code: "4010", name: "درآمد فروش", account_type: "INCOME", amount: "30000000" }),
    ],
    expenses: [node({ code: "5040", name: "اجاره", account_type: "EXPENSE", amount: "5000000" })],
    total_income: "30000000.0000",
    total_expenses: "5000000.0000",
    net_income: "25000000.0000",
  },
  "/api/v1/reports/cash-flow": {
    period_start: "2026-03-21",
    period_end: "2026-10-31",
    opening_balance: "10000000.0000",
    closing_balance: "40000000.0000",
    inflows: "35000000.0000",
    outflows: "5000000.0000",
    net_change: "30000000.0000",
  },
  "/api/v1/reports/trial-balance": [
    {
      account_id: "a1",
      code: "1010",
      name: "صندوق",
      account_type: "ASSET",
      normal_balance: "DEBIT",
      is_placeholder: false,
      debit: "40000000",
      credit: "0",
      balance: "40000000",
    },
  ],
};

function wire(table: Record<string, unknown> = reports) {
  vi.mocked(api.GET).mockImplementation((async (path: string, init?: unknown) => {
    const key = Object.keys(table).find((p) => path.startsWith(p));
    if (!key) return { data: null, response: new Response() };
    const prefix = (init as { params?: { query?: { cash_prefix?: string } } } | undefined)?.params
      ?.query?.cash_prefix;
    const value = table[key] as Record<string, unknown>;
    if (prefix === "102")
      return { data: { ...value, closing_balance: "50000000.0000" }, response: new Response() };
    return { data: value, response: new Response() };
  }) as never);
}

/** Radix tabs activate on mouse-down, not on a bare click event. */
function openTab(name: string) {
  const tab = screen.getByRole("tab", { name });
  fireEvent.mouseDown(tab);
  fireEvent.click(tab);
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <StatementsPage />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

beforeEach(() => wire());

it("replaces the old placeholder with the real balance sheet", async () => {
  const view = renderPage();
  expect(view.container.textContent).not.toContain("Phase 5 تکمیل درخت تفکیکی");
  const table = await screen.findByRole("table", { name: "ترازنامه" });
  await within(table).findByText("صندوق");
  // every account line is rendered, including nested ones
  expect(within(table).getByTestId("stmt-node-1")).toBeInTheDocument();
  expect(within(table).getByTestId("stmt-node-1010")).toBeInTheDocument();
  expect(within(table).getByTestId("stmt-node-1020")).toBeInTheDocument();
  // totals come from the report, shown in Tomans (÷10 of the Rial value)
  expect(within(table).getByTestId("bs-total-assets")).toHaveTextContent("۹٬۰۰۰٬۰۰۰");
  expect(within(table).getByTestId("bs-total-liabilities")).toHaveTextContent("۲٬۰۰۰٬۰۰۰");
  expect(within(table).getByTestId("bs-retained-earnings")).toHaveTextContent("۱٬۰۰۰٬۰۰۰");
  expect(within(table).getByTestId("bs-total-liabilities-equity")).toHaveTextContent("۹٬۰۰۰٬۰۰۰");
  expect(screen.getByTestId("bs-balanced")).toBeInTheDocument();
  expect(screen.queryByTestId("bs-imbalance")).not.toBeInTheDocument();
});

it("says so loudly when the two sides do not match", async () => {
  wire({
    ...reports,
    "/api/v1/reports/balance-sheet": {
      ...(reports["/api/v1/reports/balance-sheet"] as Record<string, unknown>),
      total_assets: "95000000.0000",
    },
  });
  renderPage();
  const alert = await screen.findByTestId("bs-imbalance");
  expect(alert).toHaveTextContent("تراز نیست");
  expect(alert).toHaveTextContent("۵۰۰٬۰۰۰");
  expect(screen.queryByTestId("bs-balanced")).not.toBeInTheDocument();
});

it("shows the income statement for the selected period", async () => {
  renderPage();
  openTab("سود و زیان");
  const table = await screen.findByRole("table", { name: "صورت سود و زیان" });
  expect(within(table).getByTestId("stmt-node-4010")).toHaveTextContent("درآمد فروش");
  expect(within(table).getByTestId("is-total-income")).toHaveTextContent("۳٬۰۰۰٬۰۰۰");
  expect(within(table).getByTestId("is-total-expenses")).toHaveTextContent("۵۰۰٬۰۰۰");
  expect(within(table).getByTestId("is-net-income")).toHaveTextContent("۲٬۵۰۰٬۰۰۰");
});

it("sums cash and bank for the cash flow and keeps receivables out", async () => {
  renderPage();
  openTab("جریان وجوه نقد");
  const table = await screen.findByRole("table", { name: "جریان وجوه نقد" });
  expect(within(table).getByTestId("cf-opening")).toHaveTextContent("۲٬۰۰۰٬۰۰۰");
  expect(within(table).getByTestId("cf-closing")).toHaveTextContent("۹٬۰۰۰٬۰۰۰");
  expect(within(table).getByTestId("cf-net")).toHaveTextContent("۶٬۰۰۰٬۰۰۰");
  // both cash groups were asked for separately, never the misleading «10» prefix
  const calls = vi.mocked(api.GET).mock.calls as unknown as Array<[unknown, unknown]>;
  const prefixes = calls
    .filter(([path]) => String(path).includes("cash-flow"))
    .map(
      ([, init]) =>
        (init as { params: { query: { cash_prefix: string } } }).params.query.cash_prefix,
    );
  expect(prefixes.sort()).toEqual(["101", "102"]);
});

it("reports an unknown state instead of a fake zero, and retries", async () => {
  vi.mocked(api.GET).mockImplementation((async () => ({
    error: { detail: "boom" },
    response: new Response(JSON.stringify({ detail: "boom" }), { status: 503 }),
  })) as never);
  renderPage();
  const alert = await screen.findByTestId("balance-sheet-state");
  expect(alert).toHaveTextContent("وضعیت نامشخص است");
  expect(screen.queryByRole("table", { name: "ترازنامه" })).not.toBeInTheDocument();
  fireEvent.click(within(alert).getByRole("button", { name: "تلاش دوباره" }));
  await waitFor(() => expect(vi.mocked(api.GET).mock.calls.length).toBeGreaterThan(4));
});

it("keeps an empty report readable instead of blank", async () => {
  wire({
    "/api/v1/reports/balance-sheet": {
      as_of: "2026-10-31",
      assets: [],
      liabilities: [],
      equity: [],
      total_assets: "0.0000",
      total_liabilities: "0.0000",
      total_equity: "0.0000",
      retained_earnings: "0.0000",
    },
  });
  renderPage();
  const table = await screen.findByRole("table", { name: "ترازنامه" });
  expect(within(table).getAllByText("داده‌ای برای نمایش وجود ندارد.")).toHaveLength(3);
  expect(screen.getByTestId("bs-balanced")).toBeInTheDocument();
});

it("never prints a fake zero for a group header, and drops empty ones", async () => {
  wire({
    ...reports,
    "/api/v1/reports/balance-sheet": {
      ...(reports["/api/v1/reports/balance-sheet"] as Record<string, unknown>),
      assets: [
        node({
          code: "1",
          name: "دارایی‌ها",
          is_placeholder: true,
          amount: "0.0000",
          children: [node({ code: "1010", name: "صندوق", amount: "62000000" })],
        }),
        node({
          code: "2",
          name: "گروه خالی",
          is_placeholder: true,
          amount: "0.0000",
          children: [],
        }),
      ],
    },
  });
  renderPage();
  const table = await screen.findByRole("table", { name: "ترازنامه" });
  const header = within(table).getByTestId("stmt-node-1");
  expect(header).toHaveTextContent("—");
  expect(header).not.toHaveTextContent("۰");
  expect(within(table).getByTestId("stmt-node-1010")).toHaveTextContent("۶٬۲۰۰٬۰۰۰");
  expect(within(table).queryByTestId("stmt-node-2")).not.toBeInTheDocument();
});

it("opens the movements behind a statement line, with the period it used", async () => {
  wire({
    ...reports,
    "/api/v1/accounts/{account_id}/ledger": {
      account_id: "a1",
      code: "1010",
      name: "صندوق",
      account_type: "ASSET",
      start: null,
      end: "2026-10-31",
      opening_balance: "0.0000",
      closing_balance: "62000000.0000",
      total_debit: "62000000.0000",
      total_credit: "0.0000",
      rows: [
        {
          entry_id: "e1",
          entry_number: 1,
          transaction_date: "2026-04-01",
          description: "سرمایه اولیه",
          payee: null,
          debit: "50000000.0000",
          credit: "0.0000",
        },
        {
          entry_id: "e3",
          entry_number: 3,
          transaction_date: "2026-06-15",
          description: "فروش نقدی",
          payee: "آقای رضایی",
          debit: "12000000.0000",
          credit: "0.0000",
        },
      ],
    },
  });
  renderPage();
  fireEvent.click(await screen.findByTestId("stmt-open-1010"));
  const drawer = await screen.findByTestId("stmt-drill");
  expect(within(drawer).getByRole("dialog", { name: "گردش حساب صندوق" })).toBeInTheDocument();
  await waitFor(() => expect(within(drawer).getAllByTestId("stmt-drill-row")).toHaveLength(2));
  // the drawer shows the movements in the order the API returns them
  const rows = within(drawer).getAllByTestId("stmt-drill-row");
  expect(rows[0]).toHaveTextContent("سرمایه اولیه");
  expect(rows[0]).toHaveTextContent("۵٬۰۰۰٬۰۰۰");
  expect(rows[1]).toHaveTextContent("آقای رضایی");
  expect(within(drawer).getByTestId("stmt-drill-closing")).toHaveTextContent("۶٬۲۰۰٬۰۰۰");

  // The drawer asks for the same cut-off the balance-sheet tab is showing.
  const calls = vi.mocked(api.GET).mock.calls as unknown as Array<
    [
      string,
      {
        params?: {
          path?: { account_id?: string };
          query?: { start?: string; end?: string };
        };
      },
    ]
  >;
  const ledgerCall = calls.find(([path]) => String(path).includes("/ledger"));
  expect(ledgerCall?.[1].params?.path?.account_id).toBe("1010");
  expect(ledgerCall?.[1].params?.query?.end).toBe("2026-10-31");

  fireEvent.click(within(drawer).getByTestId("stmt-drill-close"));
  await waitFor(() => expect(screen.queryByTestId("stmt-drill")).not.toBeInTheDocument());
});

it("closes the drill-down with Escape", async () => {
  renderPage();
  fireEvent.click(await screen.findByTestId("stmt-open-2010"));
  await screen.findByTestId("stmt-drill");
  fireEvent.keyDown(window, { key: "Escape" });
  await waitFor(() => expect(screen.queryByTestId("stmt-drill")).not.toBeInTheDocument());
});

it("computes the balance-sheet difference exactly, without floats", () => {
  expect(balanceSheetDifference("8000.0001", "1000", "5000", "2000.0001")).toBe("0.0000");
  expect(balanceSheetDifference("8000", "1000", "5000", "2000")).toBe("0.0000");
  expect(balanceSheetDifference("8000.0002", "1000", "5000", "2000")).toBe("0.0002");
});
