import { CalendarContext } from "@/lib/calendar-settings";
/**
 * Replacement for the old «debit ≠ credit» form rule (Phase 8 e2e chase).
 *
 * Item 11 of the owner's change list removed بدهکار/بستانکار from the user's
 * path, so the rule under test is now the invoice one: the user fills items and
 * the grand total, and the entry is posted as one balanced invoice. The ledger's
 * zero-balance rule itself is still covered by `journal.test.ts` and the backend
 * suite — it just is no longer a form field.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const post = vi.fn(async () => ({
  data: { entry: { id: "e1", entry_number: 7 }, total: "3000000.0000", lines: [] },
  error: undefined,
}));

vi.mock("@/api/client", () => ({
  api: {
    GET: vi.fn(async () => ({ data: [], error: undefined })),
    POST: (...args: unknown[]) => post(...(args as [])),
  },
  apiClient: {},
  ApiError: class ApiError extends Error {},
  parseError: vi.fn(async () => ({ status: 500, detail: "x" })),
  onUnauthorized: vi.fn(),
  getCsrfToken: vi.fn(() => null),
  getSudoToken: vi.fn(() => null),
  setSudoToken: vi.fn(),
  newIdempotencyKey: vi.fn(() => "idem-test"),
}));

vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => () => undefined,
}));

import { JournalNewPage } from "@/routes/journal-new";

function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <CalendarContext.Provider value={{ calendar: "jalali", ready: true, error: null }}>
        <JournalNewPage />
      </CalendarContext.Provider>
    </QueryClientProvider>,
  );
}

/** Fill one full invoice line and return the running total element. */
function fillLine(
  index: number,
  values: { title?: string; quantity?: string; price?: string } = {},
): void {
  fireEvent.change(screen.getByTestId(`invoice-title-${index}`), {
    target: { value: values.title ?? "مجسمه" },
  });
  fireEvent.change(screen.getByTestId(`invoice-quantity-${index}`), {
    target: { value: values.quantity ?? "1" },
  });
  fireEvent.change(screen.getByTestId(`invoice-price-${index}`), {
    target: { value: values.price ?? "1000000" },
  });
}

describe("new entry page — invoice form", () => {
  afterEach(() => {
    cleanup();
    post.mockClear();
  });

  it("has no debit/credit input anywhere on the user's path", () => {
    mount();
    expect(screen.queryByTestId("split-account-0")).not.toBeInTheDocument();
    expect(screen.queryByTestId("split-debit-0")).not.toBeInTheDocument();
    expect(screen.queryByTestId("split-credit-0")).not.toBeInTheDocument();
    expect(screen.queryByTestId("auto-balance")).not.toBeInTheDocument();
    expect(screen.queryByTestId("balance-error")).not.toBeInTheDocument();
    // The guide may *explain* that the user does not have to type them; no
    // input, label or option may ask for them.
    const asksForLedgerSides = screen
      .getAllByRole("textbox")
      .some((el) => /بدهکار|بستانکار/.test(el.getAttribute("aria-label") ?? ""));
    expect(asksForLedgerSides).toBe(false);
    expect(screen.queryByText("بدهکار")).not.toBeInTheDocument();
    expect(screen.queryByText("بستانکار")).not.toBeInTheDocument();
    // the invoice fields the owner asked for are all present
    for (const id of ["invoice-kind", "entry-date", "invoice-seller", "invoice-buyer"]) {
      expect(screen.getByTestId(id)).toBeInTheDocument();
    }
    expect(screen.getAllByTestId(/^invoice-line-/)).toBeTruthy();
  });

  it("computes each line amount and the grand total exactly", async () => {
    mount();
    fillLine(0, { quantity: "3", price: "250000.5" });
    await waitFor(() =>
      expect(screen.getByTestId("invoice-line-total-0")).toHaveTextContent("۷۵۰٬۰۰۱.۵"),
    );
    fireEvent.click(screen.getByTestId("invoice-add-line"));
    fillLine(1, { title: "جاکلیدی", quantity: "2", price: "1000" });
    await waitFor(() =>
      expect(screen.getByTestId("invoice-grand-total")).toHaveTextContent("۷۵۲٬۰۰۱.۵"),
    );
    expect(screen.getByTestId("invoice-line-count")).toHaveTextContent("۲");
  });

  it("requires the counterparty that belongs to the chosen kind", async () => {
    mount();
    fillLine(0);
    fireEvent.change(screen.getByTestId("invoice-kind"), { target: { value: "purchase" } });
    // A purchase without a seller is not an invoice: nothing is sent.
    fireEvent.click(screen.getByTestId("submit-entry"));
    await waitFor(() => expect(post).not.toHaveBeenCalled());
    fireEvent.change(screen.getByTestId("invoice-seller"), { target: { value: "تأمین‌کننده" } });
    fireEvent.click(screen.getByTestId("submit-entry"));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    const [, options] = post.mock.calls[0] as unknown as [
      string,
      { body: { kind: string; seller: string } },
    ];
    expect(options.body.kind).toBe("purchase");
    expect(options.body.seller).toBe("تأمین‌کننده");
  });

  it("still refuses an empty or zero-priced invoice", async () => {
    mount();
    expect(screen.getByTestId("submit-entry")).toBeDisabled();
    fillLine(0, { price: "" });
    await waitFor(() => expect(screen.getByTestId("submit-entry")).toBeDisabled());
    fillLine(0, { price: "0" });
    await waitFor(() => expect(screen.getByTestId("submit-entry")).toBeDisabled());
    fillLine(0, { price: "۱۰۰۰" }); // Persian digits are accepted
    await waitFor(() => expect(screen.getByTestId("submit-entry")).toBeEnabled());
  });

  it("posts the invoice in Rials and shows the created entry number", async () => {
    mount();
    fireEvent.change(screen.getByTestId("invoice-buyer"), { target: { value: "آقای مشتری" } });
    fillLine(0, { title: "مجسمه", quantity: "2", price: "1500000" });
    fireEvent.click(screen.getByTestId("submit-entry"));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    const [path, options] = post.mock.calls[0] as unknown as [
      string,
      {
        body: {
          kind: string;
          buyer: string;
          lines: Array<{ title: string; quantity: string; unit_price: string }>;
        };
      },
    ];
    expect(path).toBe("/api/v1/journal-entries/invoice");
    expect(options.body.kind).toBe("sale");
    expect(options.body.buyer).toBe("آقای مشتری");
    expect(options.body.lines).toEqual([
      { title: "مجسمه", quantity: "2.0000", unit_price: "15000000.0000" }, // Tomans ×10 → Rials
    ]);
    await waitFor(() =>
      expect(screen.getByTestId("entry-created")).toHaveTextContent("سند شمارهٔ"),
    );
    // a fresh blank invoice is ready for the next entry
    expect(screen.getByTestId("invoice-title-0")).toHaveValue("");
  });
});
