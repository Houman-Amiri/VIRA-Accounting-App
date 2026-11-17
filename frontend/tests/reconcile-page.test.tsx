/**
 * تطبیق بانکی — real data, real buttons.
 *
 * The page used to render three invented rows («شرکت آریا», «پایه موبایل», …)
 * and every button only changed local state: nothing was ever saved and the
 * numbers came from nowhere. These tests pin the replacement:
 *
 *   * no invented row can appear — the page shows only what the API returned;
 *   * empty and failed requests say so, instead of looking like a healthy page;
 *   * each button reaches the endpoint that actually does the work.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const get = vi.fn();
const post = vi.fn();

vi.mock("@/api/client", () => ({
  api: {
    GET: (...args: unknown[]) => get(...args),
    POST: (...args: unknown[]) => post(...args),
  },
  parseError: vi.fn(async () => new Error("خطای سرور")),
  onUnauthorized: vi.fn(),
  getCsrfToken: vi.fn(() => null),
  getSudoToken: vi.fn(() => null),
  setSudoToken: vi.fn(),
  newIdempotencyKey: vi.fn(() => "idem-key"),
}));

vi.mock("@/components/sudo-dialog", () => ({
  useOptionalRequestSudo: () => async () => "sudo-token",
  useRequestSudo: () => async () => "sudo-token",
}));

vi.mock("@tanstack/react-router", () => ({
  Link: ({ children, ...rest }: { children: React.ReactNode }) => <a {...rest}>{children}</a>,
}));

import { ReconcilePage } from "@/routes/reconcile";

const accounts = [
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
];

const openSession = {
  id: "s-1",
  account_id: "a1020",
  statement_date: "2026-10-31",
  beginning_balance: "0.0000",
  ending_balance: "1250.5000",
  status: "OPEN",
  completed_at: null,
  created_at: "2026-10-31T00:00:00+00:00",
};

const lines = [
  {
    id: "l-1",
    account_id: "a1020",
    value_date: "2026-10-01",
    payee_raw: "Aria Co",
    description_raw: "واریز فاکتور ۱۰۲۴",
    amount_scaled: 12_505_000,
    currency: "IRR",
    category_suggestion: null,
    status: "UNMATCHED",
  },
  {
    id: "l-2",
    account_id: "a1020",
    value_date: "2026-10-03",
    payee_raw: "Pars",
    description_raw: "خرید فیلامنت",
    amount_scaled: -4_800_000,
    currency: "IRR",
    category_suggestion: null,
    status: "UNMATCHED",
  },
];

const ledger = {
  account_id: "a1020",
  code: "1020",
  name: "بانک",
  account_type: "ASSET",
  start: "2026-10-01",
  end: "2026-10-03",
  opening_balance: "0.0000",
  closing_balance: "770.5000",
  total_debit: "1250.5000",
  total_credit: "480.0000",
  rows: [
    {
      entry_id: "e-2",
      split_id: "sp-2",
      entry_number: 2,
      transaction_date: "2026-10-03",
      description: "خرید فیلامنت",
      payee: "Pars",
      debit: "0.0000",
      credit: "480.0000",
      reconciliation_status: "UNRECONCILED",
    },
    {
      entry_id: "e-1",
      split_id: "sp-1",
      entry_number: 1,
      transaction_date: "2026-10-01",
      description: "واریز فاکتور ۱۰۲۴",
      payee: "Aria Co",
      debit: "1250.5000",
      credit: "0.0000",
      reconciliation_status: "UNRECONCILED",
    },
  ],
};

const progress = { linked_total: "0.0000", expected_delta: "1250.5000", balanced: false };

interface Wire {
  accounts?: unknown;
  sessions?: unknown;
  lines?: unknown;
  ledger?: unknown;
  progress?: unknown;
  fail?: string;
}

function wire(overrides: Wire = {}) {
  get.mockImplementation(async (path: string) => {
    if (path === "/api/v1/accounts") {
      if (overrides.fail === "accounts") return { data: undefined, error: { detail: "x" } };
      return { data: overrides.accounts ?? accounts, error: undefined };
    }
    if (path === "/api/v1/reconciliation/sessions") {
      if (overrides.fail === "sessions") return { data: undefined, error: { detail: "x" } };
      return { data: overrides.sessions ?? [openSession], error: undefined };
    }
    if (path === "/api/v1/imports/lines") {
      if (overrides.fail === "lines") return { data: undefined, error: { detail: "x" } };
      return { data: overrides.lines ?? lines, error: undefined };
    }
    if (path === "/api/v1/accounts/{account_id}/ledger") {
      if (overrides.fail === "ledger") return { data: undefined, error: { detail: "x" } };
      return { data: overrides.ledger ?? ledger, error: undefined };
    }
    if (path === "/api/v1/reconciliation/sessions/{session_id}/progress") {
      if (overrides.fail === "progress") return { data: undefined, error: { detail: "x" } };
      return { data: overrides.progress ?? progress, error: undefined };
    }
    return { data: undefined, error: undefined };
  });
  post.mockResolvedValue({ data: {}, error: undefined });
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ReconcilePage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  get.mockReset();
  post.mockReset();
});

afterEach(() => {
  cleanup();
});

describe("تطبیق بانکی — data", () => {
  it("never shows an invented statement row or book line", async () => {
    wire({ lines: [], ledger: { ...ledger, rows: [] }, sessions: [] });
    renderPage();
    await screen.findByTestId("reconcile-empty-lines");
    const body = document.body.textContent ?? "";
    for (const demo of ["آریا", "پایه موبایل", "پارک", "بازارگاه", "فاکتور ۱۰۲۴ شرکت"]) {
      expect(body).not.toContain(demo);
    }
  });

  it("shows only the bank/cash account, not the payable account", async () => {
    wire();
    renderPage();
    const picker = await screen.findByTestId("reconcile-account");
    const options = within(picker).getAllByRole("option");
    expect(options.map((option) => option.textContent)).toEqual(["۱۰۲۰ — بانک"]);
  });

  it("points an empty screen at the import page instead of pretending to have rows", async () => {
    wire({ lines: [], ledger: { ...ledger, rows: [] }, sessions: [] });
    renderPage();
    const empty = await screen.findByTestId("reconcile-empty-lines");
    expect(empty).toHaveTextContent(/ورود صورت‌حساب بانکی/);
    expect(empty.querySelector("a")).toHaveAttribute("to", "/bank-import");
  });

  it("says the state is unknown when a request fails", async () => {
    wire({ fail: "lines" });
    renderPage();
    const notice = await screen.findByText(/وضعیت نامشخص/);
    expect(notice).toBeInTheDocument();
  });

  it("shows the real suggested book entry for each statement line", async () => {
    wire();
    renderPage();
    const first = await screen.findByTestId("suggestion-0");
    expect(first).toHaveTextContent("واریز فاکتور ۱۰۲۴");
    // amounts are shown unsigned per line; the difference header carries the sign
    expect(screen.getByTestId("live-difference")).toHaveTextContent("۱۲۵.۰۵");
  });
});

describe("تطبیق بانکی — buttons do real work", () => {
  it("«تأیید پیشنهاد» links the suggested split and marks the line matched", async () => {
    wire();
    renderPage();
    fireEvent.click(await screen.findByTestId("accept-0"));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    const [linkPath, linkOptions] = post.mock.calls[0];
    expect(linkPath).toBe("/api/v1/reconciliation/sessions/{session_id}/splits/{split_id}/link");
    expect(linkOptions.params.path).toEqual({ session_id: "s-1", split_id: "sp-1" });

    const [statusPath, statusOptions] = post.mock.calls[1];
    expect(statusPath).toBe("/api/v1/imports/lines/{line_id}/status");
    expect(statusOptions.params.path).toEqual({ line_id: "l-1" });
    expect(statusOptions.body).toEqual({ status: "MATCHED" });
  });

  it("«نادیده گرفتن» persists IGNORED on the statement line", async () => {
    wire();
    renderPage();
    fireEvent.click(await screen.findByTestId("ignore-0"));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    const [path, options] = post.mock.calls[0];
    expect(path).toBe("/api/v1/imports/lines/{line_id}/status");
    expect(options.params.path).toEqual({ line_id: "l-1" });
    expect(options.body).toEqual({ status: "IGNORED" });
  });

  it("«شروع تطبیق» creates a session with the entered balances", async () => {
    wire({ sessions: [] });
    renderPage();
    fireEvent.change(await screen.findByTestId("reconcile-opening"), {
      target: { value: "100.00" },
    });
    fireEvent.change(screen.getByTestId("reconcile-closing"), { target: { value: "250.00" } });
    fireEvent.click(screen.getByTestId("start-session"));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    const [path, options] = post.mock.calls[0];
    expect(path).toBe("/api/v1/reconciliation/sessions");
    expect(options.body).toMatchObject({
      account_id: "a1020",
      beginning_balance: "100.00",
      ending_balance: "250.00",
    });
    expect(options.body.statement_date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it("«تکمیل تطبیق» completes the open session when it balances", async () => {
    wire({ progress: { linked_total: "1250.5000", expected_delta: "1250.5000", balanced: true } });
    renderPage();
    const state = await screen.findByTestId("balance-state");
    expect(state).toHaveTextContent("تراز است");
    fireEvent.click(screen.getByTestId("complete-session"));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    const [path, options] = post.mock.calls[0];
    expect(path).toBe("/api/v1/reconciliation/sessions/{session_id}/complete");
    expect(options.params.path).toEqual({ session_id: "s-1" });
    expect(options.headers["Idempotency-Key"]).toBeTruthy();
  });

  it("asks before completing an unbalanced session, and the confirm button still completes", async () => {
    wire();
    renderPage();
    fireEvent.click(await screen.findByTestId("complete-session"));
    const confirm = await screen.findByTestId("confirm-complete");
    expect(confirm).toHaveTextContent(/برابر نیست/);
    expect(post).not.toHaveBeenCalled();

    fireEvent.click(within(confirm).getByTestId("confirm-complete-yes"));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post.mock.calls[0][0]).toBe("/api/v1/reconciliation/sessions/{session_id}/complete");
  });

  it("does not offer the manual link button before a bank line is selected", async () => {
    wire();
    renderPage();
    const link = await screen.findByTestId("link-0");
    expect(link).toBeDisabled();

    fireEvent.click(screen.getByTestId("select-line-0"));
    await waitFor(() => expect(screen.getByTestId("link-0")).toBeEnabled());
  });

  it("the manual «تطبیق» button links the selected row explicitly", async () => {
    wire();
    renderPage();
    fireEvent.click(await screen.findByTestId("select-line-0"));
    await waitFor(() => expect(screen.getByTestId("link-0")).toBeEnabled());
    // row 0 is the filament purchase (sp-2); the selected line is the Aria deposit
    fireEvent.click(screen.getByTestId("link-0"));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    expect(post.mock.calls[0][1].params.path).toEqual({
      session_id: "s-1",
      split_id: "sp-2",
    });
    expect(post.mock.calls[1][1].body).toEqual({ status: "MATCHED" });
  });

  it("«بازگشایی» only appears for a completed session and reopens it", async () => {
    const completed = { ...openSession, status: "COMPLETED", completed_at: "2026-10-31T10:00:00" };
    wire({ sessions: [completed] });
    renderPage();
    const reopen = await screen.findByTestId("reopen-session");
    fireEvent.click(reopen);

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post.mock.calls[0][0]).toBe("/api/v1/reconciliation/sessions/{session_id}/reopen");
    expect(post.mock.calls[0][1].params.path).toEqual({ session_id: "s-1" });
  });

  it("«انصراف از جلسه» abandons the open session", async () => {
    wire();
    renderPage();
    fireEvent.click(await screen.findByTestId("abandon-session"));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post.mock.calls[0][0]).toBe("/api/v1/reconciliation/sessions/{session_id}/abandon");
  });

  it("«تأیید همه پیشنهادها» links every high-confidence suggestion", async () => {
    wire();
    renderPage();
    const all = await screen.findByTestId("confirm-all");
    // both statement lines match their book row on amount + description
    fireEvent.click(all);
    await waitFor(() => expect(post).toHaveBeenCalledTimes(4));
    const linked = post.mock.calls.filter(([path]) => String(path).endsWith("/link"));
    expect(linked.map(([, options]) => options.params.path.split_id).sort()).toEqual([
      "sp-1",
      "sp-2",
    ]);
  });

  it("«بازگردانی» puts an ignored line back into the work list", async () => {
    wire({ lines: [{ ...lines[0], status: "IGNORED" }, lines[1]] });
    renderPage();
    fireEvent.click(await screen.findByTestId("toggle-ignored"));
    fireEvent.click(await screen.findByTestId("restore-l-1"));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post.mock.calls[0][0]).toBe("/api/v1/imports/lines/{line_id}/status");
    expect(post.mock.calls[0][1].body).toEqual({ status: "UNMATCHED" });
  });
});
