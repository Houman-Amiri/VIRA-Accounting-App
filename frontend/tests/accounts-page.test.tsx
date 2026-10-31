/**
 * حساب‌ها — the chart of accounts said in the owner's language.
 *
 * The old page was a code/name list with an empty «نوع» badge (it read `kind`,
 * which the API does not send) and a «در حال بارگذاری…» that never went away.
 * These tests pin the replacement: real balances from the trial balance, shown
 * on the human side of each account, no English account types, and honest
 * states for empty and failed loading.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const get = vi.fn();

vi.mock("@/api/client", () => ({
  api: { GET: (...args: unknown[]) => get(...args) },
  apiClient: {},
  ApiError: class ApiError extends Error {
    isStale = false;
  },
  parseError: vi.fn(async () => new Error("خطای سرور")),
  onUnauthorized: vi.fn(),
  getCsrfToken: vi.fn(() => null),
  getSudoToken: vi.fn(() => null),
  setSudoToken: vi.fn(),
}));

vi.mock("@tanstack/react-router", () => ({
  Link: ({ children, ...rest }: { children: React.ReactNode }) => <a {...rest}>{children}</a>,
}));

import { AccountsPage } from "@/routes/accounts";

const accounts = [
  {
    id: "a1010",
    code: "1010",
    name: "صندوق",
    account_type: "ASSET",
    normal_balance: "DEBIT",
    currency: "IRR",
    parent_id: null,
    path: "1010",
    is_placeholder: false,
    is_active: true,
    version_id: 1,
  },
  {
    id: "a1020",
    code: "1020",
    name: "بانک",
    account_type: "ASSET",
    normal_balance: "DEBIT",
    currency: "IRR",
    parent_id: null,
    path: "1020",
    is_placeholder: false,
    is_active: true,
    version_id: 1,
  },
  {
    id: "a2010",
    code: "2010",
    name: "حساب‌های پرداختنی",
    account_type: "LIABILITY",
    normal_balance: "CREDIT",
    currency: "IRR",
    parent_id: null,
    path: "2010",
    is_placeholder: false,
    is_active: true,
    version_id: 1,
  },
  {
    id: "a1000",
    code: "1000",
    name: "دارایی‌ها",
    account_type: "ASSET",
    normal_balance: "DEBIT",
    currency: "IRR",
    parent_id: null,
    path: "1000",
    is_placeholder: true,
    is_active: true,
    version_id: 1,
  },
];

// Rial amounts: the trial balance is signed debit − credit.
const trial = [
  {
    account_id: "a1010",
    code: "1010",
    name: "صندوق",
    account_type: "ASSET",
    normal_balance: "DEBIT",
    is_placeholder: false,
    debit: "620000000.0000",
    credit: "0.0000",
    balance: "620000000.0000",
  },
  {
    account_id: "a2010",
    code: "2010",
    name: "حساب‌های پرداختنی",
    account_type: "LIABILITY",
    normal_balance: "CREDIT",
    is_placeholder: false,
    debit: "0.0000",
    credit: "200000000.0000",
    balance: "-200000000.0000",
  },
];

function wire(overrides: { accounts?: unknown; trial?: unknown; fail?: string } = {}) {
  get.mockImplementation(async (path: string) => {
    if (path === "/api/v1/accounts") {
      if (overrides.fail === "accounts") return { data: undefined, error: { detail: "x" } };
      return { data: overrides.accounts ?? accounts, error: undefined };
    }
    if (path === "/api/v1/reports/trial-balance") {
      if (overrides.fail === "trial") return { data: undefined, error: { detail: "x" } };
      return { data: overrides.trial ?? trial, error: undefined };
    }
    return { data: null, error: undefined };
  });
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AccountsPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  get.mockReset();
});

afterEach(() => {
  cleanup();
});

describe("حساب‌ها", () => {
  it("shows what each account is in plain Persian with its real balance", async () => {
    wire();
    renderPage();
    const cash = await screen.findByTestId("accounts-row-1010");
    expect(within(cash).getByText("صندوق")).toBeInTheDocument();
    expect(within(cash).getByText(/پول نقدی که در صندوق است/)).toBeInTheDocument();
    // a code is a code, not an amount: no thousands separator
    expect(cash).toHaveTextContent("کد ۱۰۱۰");
    // 620,000,000 Rial = 62,000,000 Toman, and the unit is shown once by <Money>.
    expect(cash).toHaveTextContent("۶۲٬۰۰۰٬۰۰۰");
  });

  it("never prints an English account type or the accountants' «کمکی» badge", async () => {
    wire();
    renderPage();
    await screen.findByTestId("accounts-row-1010");
    const body = document.body.textContent ?? "";
    for (const jargon of ["ASSET", "LIABILITY", "EQUITY", "INCOME", "EXPENSE", "کمکی"]) {
      expect(body).not.toContain(jargon);
    }
    // placeholder accounts are structure, not something the owner holds
    expect(screen.queryByTestId("accounts-row-1000")).not.toBeInTheDocument();
  });

  it("shows a credit-normal balance on the side a human reads", async () => {
    wire();
    renderPage();
    const payable = await screen.findByTestId("accounts-row-2010");
    // liability stored as −200,000,000 (debit − credit) but owed: 20,000,000 Toman
    expect(payable).toHaveTextContent("۲۰٬۰۰۰٬۰۰۰");
    expect(payable).not.toHaveTextContent("−");
  });

  it("keeps untouched accounts out of the way until asked for", async () => {
    wire();
    renderPage();
    await screen.findByTestId("accounts-row-1010");
    // 1020 has no movement: hidden by default, never shown as a fake zero
    expect(screen.queryByTestId("accounts-row-1020")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("accounts-toggle-idle"));
    const bank = await screen.findByTestId("accounts-row-1020");
    expect(bank).toHaveTextContent("بدون گردش");
  });

  it("still lists everything on a fresh install where nothing has moved yet", async () => {
    wire({ trial: [] });
    renderPage();
    expect(await screen.findByTestId("accounts-row-1010")).toHaveTextContent("بدون گردش");
    expect(screen.queryByTestId("accounts-toggle-idle")).not.toBeInTheDocument();
    expect(screen.getByTestId("accounts-no-movement")).toHaveTextContent("هنوز سندی ثبت نشده است");
  });

  it("totals each section and the net position from the same rows", async () => {
    wire();
    renderPage();
    await screen.findByTestId("accounts-total-asset");
    // 62,000,000 assets − 20,000,000 liabilities = 42,000,000 Toman
    expect(screen.getByTestId("accounts-total-asset")).toHaveTextContent("۶۲٬۰۰۰٬۰۰۰");
    expect(screen.getByTestId("accounts-total-liability")).toHaveTextContent("۲۰٬۰۰۰٬۰۰۰");
    expect(screen.getByTestId("accounts-net")).toHaveTextContent("۴۲٬۰۰۰٬۰۰۰");
  });

  it("says the state is unknown when the balances cannot be loaded", async () => {
    wire({ fail: "trial" });
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent("وضعیت نامشخص است");
    expect(screen.queryByTestId("accounts-summary")).not.toBeInTheDocument();
  });

  it("stops pretending to load when there are no accounts at all", async () => {
    wire({ accounts: [], trial: [] });
    renderPage();
    expect(await screen.findByText("هنوز حسابی ساخته نشده است.")).toBeInTheDocument();
    expect(screen.queryByText("در حال بارگذاری…")).not.toBeInTheDocument();
  });
});
