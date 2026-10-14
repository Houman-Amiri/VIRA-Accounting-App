/** Reproduction: journal balance rule surface in the form (Phase 8 e2e chase). */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const accounts = [
  {
    id: "acc-1",
    code: "1000",
    name: "صندوق",
    account_type: "ASSET",
    normal_balance: "DEBIT",
    is_placeholder: false,
    balance: "0.0000",
    path: "1000",
    is_active: true,
  },
  {
    id: "acc-2",
    code: "1100",
    name: "بانک",
    account_type: "ASSET",
    normal_balance: "DEBIT",
    is_placeholder: false,
    balance: "0.0000",
    path: "1100",
    is_active: true,
  },
];

vi.mock("@/api/client", () => ({
  api: {
    GET: vi.fn(async (path: string) => {
      if (path.includes("/accounts")) return { data: accounts, error: undefined };
      return { data: undefined, error: { status: 500, detail: "x" } };
    }),
    POST: vi.fn(async () => ({ data: { id: "x" }, error: undefined })),
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

describe("journal form balance rule", () => {
  afterEach(cleanup);

  it("shows the balance error when debit ≠ credit after accounts are chosen", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <JournalNewPage />
      </QueryClientProvider>,
    );
    // wait until the accounts query populated the options
    await waitFor(() => {
      const sel = screen.getByTestId("split-account-0") as HTMLSelectElement;
      expect(sel.options.length).toBeGreaterThan(1);
    });
    const sel0 = screen.getByTestId("split-account-0") as HTMLSelectElement;
    const sel1 = screen.getByTestId("split-account-1") as HTMLSelectElement;
    fireEvent.change(sel0, { target: { value: "acc-1" } });
    fireEvent.change(sel1, { target: { value: "acc-2" } });
    fireEvent.change(screen.getByTestId("split-debit-0"), { target: { value: "100" } });
    fireEvent.change(screen.getByTestId("split-credit-1"), { target: { value: "75" } });
    await waitFor(() => expect(screen.queryByTestId("balance-error")).toBeTruthy(), {
      timeout: 3000,
    });
    expect(screen.getByTestId("submit-entry")).toBeDisabled();
  });
});
