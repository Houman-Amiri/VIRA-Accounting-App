/**
 * دفتر اسناد — an entry must be openable, correctable and its status changeable.
 *
 * The owner reported the page was read-only: no way to change an entry's status
 * or edit it. These tests drive the real page against a mocked API and assert
 * the calls the server needs (post / unpost / void / invoice correction).
 */
import { CalendarContext } from "@/lib/calendar-settings";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const get = vi.fn();
const post = vi.fn();
const put = vi.fn();

vi.mock("@/api/client", () => ({
  api: {
    GET: (...args: unknown[]) => get(...args),
    POST: (...args: unknown[]) => post(...args),
    PUT: (...args: unknown[]) => put(...args),
  },
  apiClient: {},
  ApiError: class ApiError extends Error {
    isStale = false;
  },
  parseError: vi.fn(async () => new Error("خطای سرور")),
  onUnauthorized: vi.fn(),
  getCsrfToken: vi.fn(() => null),
  getSudoToken: vi.fn(() => null),
  setSudoToken: vi.fn(),
  newIdempotencyKey: vi.fn(() => "idem-test"),
}));

vi.mock("@tanstack/react-router", () => ({ useNavigate: () => () => undefined }));

// The virtualized grid needs layout; render every row instead.
vi.mock("@/components/virtual-table", () => ({
  VirtualTable: ({
    columns,
    data,
    onRowClick,
  }: {
    columns: Array<{ id?: string; accessorKey?: string; cell?: (ctx: unknown) => unknown }>;
    data: Array<Record<string, unknown>>;
    onRowClick?: (row: Record<string, unknown>) => void;
  }) => (
    <table>
      <tbody>
        {data.map((row) => (
          <tr key={String(row.id)} onClick={() => onRowClick?.(row)}>
            {columns.map((column, index) => {
              const value = column.accessorKey ? row[column.accessorKey] : undefined;
              return (
                <td key={column.id ?? column.accessorKey ?? index}>
                  {column.cell
                    ? (column.cell({
                        getValue: () => value,
                        row: { original: row },
                      }) as React.ReactNode)
                    : String(value ?? "")}
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  ),
}));

import { JournalListPage } from "@/routes/journal-list";

const postedEntry = {
  id: "e-posted",
  entry_number: 1,
  transaction_date: "2026-10-20",
  posted_at: "2026-10-20T00:00:00Z",
  payee: "آقای مشتری",
  description: "فروش به آقای مشتری — 1 قلم",
  status: "POSTED",
  reversed_entry_id: null,
  metadata: {
    invoice: {
      kind: "sale",
      seller: "فروشگاه ویرا",
      buyer: "آقای مشتری",
      note: null,
      lines: [
        {
          title: "مجسمهٔ روباه",
          quantity: "2.0000",
          unit_price: "1500000.0000",
          line_total: "3000000.0000",
        },
      ],
    },
  },
  version_id: 3,
  splits: [
    {
      id: "s1",
      memo: null,
      account_id: "a1",
      debit: "3000000.0000",
      credit: "0.0000",
      currency: "IRR",
      exchange_rate: "1.00000000",
      reconciliation_status: "UNRECONCILED",
    },
    {
      id: "s2",
      memo: null,
      account_id: "a2",
      debit: "0.0000",
      credit: "3000000.0000",
      currency: "IRR",
      exchange_rate: "1.00000000",
      reconciliation_status: "UNRECONCILED",
    },
  ],
};

const draftEntry = {
  ...postedEntry,
  id: "e-draft",
  entry_number: 2,
  status: "DRAFT",
  description: "سند دستی",
  metadata: {},
  payee: null,
  version_id: 1,
  splits: [
    {
      id: "s3",
      memo: null,
      account_id: "a1",
      debit: "500.0000",
      credit: "0.0000",
      currency: "IRR",
      exchange_rate: "1.00000000",
      reconciliation_status: "UNRECONCILED",
    },
    {
      id: "s4",
      memo: null,
      account_id: "a3",
      debit: "0.0000",
      credit: "500.0000",
      currency: "IRR",
      exchange_rate: "1.00000000",
      reconciliation_status: "UNRECONCILED",
    },
  ],
};

function wire(entries: unknown[], overrides: Partial<Record<string, unknown>> = {}) {
  get.mockImplementation(async (path: string) => {
    if (path === "/api/v1/journal-entries") return { data: entries, error: undefined };
    if (path === "/api/v1/accounts")
      return {
        data: [
          { id: "a1", code: "1040", name: "حساب‌های دریافتنی" },
          { id: "a2", code: "4010", name: "درآمد فروش" },
          { id: "a3", code: "3010", name: "سرمایه" },
        ],
        error: undefined,
      };
    return { data: null, error: undefined };
  });
  post.mockImplementation(async (path: string) => ({
    data: { ...postedEntry, ...(overrides[path] as object) },
    error: undefined,
  }));
  put.mockImplementation(async (path: string) => ({
    data: { ...postedEntry, ...(overrides[path] as object) },
    error: undefined,
  }));
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <CalendarContext.Provider value={{ calendar: "jalali", ready: true, error: null }}>
        <JournalListPage />
      </CalendarContext.Provider>
    </QueryClientProvider>,
  );
}

async function openEntry(entryNumber: number) {
  fireEvent.click(await screen.findByTestId(`entry-open-${entryNumber}`));
  return screen.findByTestId("entry-drawer");
}

beforeEach(() => {
  get.mockReset();
  post.mockReset();
  put.mockReset();
});

afterEach(() => {
  cleanup();
});

describe("دفتر اسناد", () => {
  it("labels the real API statuses (posted entries are not «پیش‌نویس»)", async () => {
    wire([postedEntry, draftEntry]);
    renderPage();
    await screen.findByTestId("entry-open-1");
    expect(screen.getAllByTestId("entry-status")[0]).toHaveTextContent("ثبت‌شده");
    expect(screen.getAllByTestId("entry-status")[1]).toHaveTextContent("پیش‌نویس");
  });

  it("posts a draft into the books", async () => {
    wire([draftEntry]);
    renderPage();
    const drawer = await openEntry(2);
    fireEvent.click(within(drawer).getByTestId("entry-post"));
    await waitFor(() => expect(post).toHaveBeenCalled());
    const call = post.mock.calls.find(([path]) => String(path).includes("/post"))!;
    expect(call[0]).toBe("/api/v1/journal-entries/{entry_id}/post");
    expect((call[1] as { params: { path: { entry_id: string } } }).params.path.entry_id).toBe(
      "e-draft",
    );
  });

  it("takes a posted entry back to draft and opens the editor", async () => {
    wire([postedEntry]);
    renderPage();
    const drawer = await openEntry(1);
    fireEvent.click(within(drawer).getByTestId("entry-unpost"));
    await waitFor(() =>
      expect(post.mock.calls.some(([path]) => String(path).endsWith("/unpost"))).toBe(true),
    );
    expect(await screen.findByTestId("entry-editor")).toBeInTheDocument();
  });

  it("corrects the invoice behind a posted entry, not its debit/credit lines", async () => {
    wire([postedEntry]);
    renderPage();
    const drawer = await openEntry(1);
    // The drawer shows the paper invoice: the item, its count and its price.
    expect(within(drawer).getByText("مجسمهٔ روباه")).toBeInTheDocument();
    fireEvent.click(within(drawer).getByTestId("entry-edit"));

    const price = await screen.findByLabelText("مبلغ واحد (تومان)");
    fireEvent.change(price, { target: { value: "2500000" } });
    fireEvent.click(screen.getByTestId("entry-save"));

    await waitFor(() => expect(put).toHaveBeenCalled());
    const [path, options] = put.mock.calls[0] as [
      string,
      {
        params: { path: { entry_id: string } };
        body: {
          version_id: number;
          lines: Array<{ title: string; quantity: string; unit_price: string }>;
          buyer: string;
        };
      },
    ];
    expect(path).toBe("/api/v1/journal-entries/{entry_id}/invoice");
    expect(options.params.path.entry_id).toBe("e-posted");
    // 2 500 000 Toman typed → 25 000 000 Rials stored (the ×10 edge).
    expect(options.body.lines[0].unit_price).toBe("25000000.0000");
    expect(options.body.lines[0].quantity).toBe("2.0000");
    expect(options.body.version_id).toBe(3);
    expect(options.body.buyer).toBe("آقای مشتری");
  });

  it("corrects a hand-written entry's amount without asking for debit/credit", async () => {
    wire([draftEntry]);
    renderPage();
    const drawer = await openEntry(2);
    fireEvent.click(within(drawer).getByTestId("entry-edit"));

    const description = await screen.findByTestId("entry-description-input");
    fireEvent.change(description, { target: { value: "شرح اصلاح‌شده" } });
    // 500 Rial = 50 Toman was the old amount; both sides move together.
    const amount = screen.getByTestId("entry-amount-input");
    expect(amount).toHaveValue("50");
    fireEvent.change(amount, { target: { value: "75" } });
    fireEvent.click(screen.getByTestId("entry-save"));

    await waitFor(() => expect(put).toHaveBeenCalled());
    const [path, options] = put.mock.calls[0] as [
      string,
      {
        params: { path: { entry_id: string } };
        body: {
          description: string;
          splits: Array<{ account_id: string; debit: string; credit: string }>;
        };
      },
    ];
    expect(path).toBe("/api/v1/journal-entries/{entry_id}");
    expect(options.body.description).toBe("شرح اصلاح‌شده");
    // 75 Toman typed → 750 Rials; the two sides are mirrored, never guessed.
    expect(options.body.splits).toEqual([
      expect.objectContaining({ account_id: "a1", debit: "750.0000", credit: "0.0000" }),
      expect.objectContaining({ account_id: "a3", debit: "0.0000", credit: "750.0000" }),
    ]);
  });

  it("leaves the lines of a multi-line entry alone and says why", async () => {
    const multi = {
      ...draftEntry,
      id: "e-multi",
      entry_number: 3,
      splits: [
        ...draftEntry.splits,
        {
          id: "s5",
          account_id: "a2",
          memo: null,
          debit: "0.0000",
          credit: "500.0000",
          currency: "IRR",
          exchange_rate: "1.00000000",
          reconciliation_status: "UNRECONCILED",
        },
      ],
    };
    wire([multi]);
    renderPage();
    const drawer = await openEntry(3);
    fireEvent.click(within(drawer).getByTestId("entry-edit"));
    expect(screen.queryByTestId("entry-amount-input")).not.toBeInTheDocument();
    expect(screen.getByText(/بیش از دو ردیف/)).toBeInTheDocument();
    const description = await screen.findByTestId("entry-description-input");
    fireEvent.change(description, { target: { value: "شرح تازه" } });
    fireEvent.click(screen.getByTestId("entry-save"));
    await waitFor(() => expect(put).toHaveBeenCalled());
    const [, options] = put.mock.calls[0] as [string, { body: Record<string, unknown> }];
    expect(options.body).not.toHaveProperty("splits");
  });

  it("voids a posted entry only with a reason", async () => {
    wire([postedEntry]);
    renderPage();
    const drawer = await openEntry(1);
    fireEvent.click(within(drawer).getByTestId("entry-void"));
    const confirm = await screen.findByTestId("entry-void-confirm");
    expect(confirm).toBeDisabled();
    fireEvent.change(screen.getByTestId("entry-void-reason"), {
      target: { value: "مبلغ اشتباه بود" },
    });
    expect(confirm).toBeEnabled();
    fireEvent.click(confirm);
    await waitFor(() => expect(post).toHaveBeenCalled());
    const call = post.mock.calls.find(([path]) => String(path).endsWith("/void"))!;
    expect(
      (call[1] as { params: { path: { entry_id: string }; query: { reason: string } } }).params
        .query.reason,
    ).toBe("مبلغ اشتباه بود");
  });

  it("offers the printed invoice for an invoice-shaped entry only", async () => {
    wire([postedEntry, draftEntry]);
    renderPage();
    const invoiceDrawer = await openEntry(1);
    expect(within(invoiceDrawer).getByTestId("entry-print-invoice")).toHaveAttribute(
      "href",
      "/api/v1/journal-entries/e-posted/invoice.pdf",
    );
    fireEvent.click(within(invoiceDrawer).getByTestId("entry-drawer-close"));
    await waitFor(() => expect(screen.queryByTestId("entry-drawer")).not.toBeInTheDocument());

    const handWritten = await openEntry(2);
    expect(within(handWritten).queryByTestId("entry-print-invoice")).not.toBeInTheDocument();
  });

  it("closes with Escape", async () => {
    wire([postedEntry]);
    renderPage();
    await openEntry(1);
    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => expect(screen.queryByTestId("entry-drawer")).not.toBeInTheDocument());
  });
});
