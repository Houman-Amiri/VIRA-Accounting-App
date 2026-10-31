import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { api } from "@/api/client";
import { ProductionPage } from "@/routes/production";
import { collectOperationPages } from "@/lib/operation-pages";
import { OperationPagination } from "@/components/operation-pagination";

vi.mock("@/api/client", async (original) => ({
  ...(await original<typeof import("@/api/client")>()),
  api: { GET: vi.fn(), POST: vi.fn(), PATCH: vi.fn() },
}));
const settings = {
  filamentPerGram: "9999",
  electricityPerKwh: "1400",
  depreciationPerHour: "10000",
  profitFactor: "2.5",
  chainPerUnit: "8000",
  shipmentPerBatch: "150000",
  labelPerUnit: "8000",
  version_id: 1,
};
const lines = [
  {
    id: "l1",
    product_name: "محصول اول",
    variant: "plain",
    quantity: "2",
    weight_g: "12.5",
    print_hours: "1",
    unit_price: "123.4567",
    unit_cost: "23.4567",
  },
  {
    id: "l2",
    product_name: "محصول دوم",
    variant: "chain",
    quantity: "1",
    weight_g: "20",
    print_hours: "2",
    unit_price: "456.1234",
    unit_cost: "56.1234",
  },
];
const job = {
  id: "j1",
  job_number: 1,
  product_name: "کار قبلی",
  status: "PLANNED",
  order_id: null,
  order_item_id: null,
  filament_item_id: null,
  filament_item_name: null,
  product_item_id: null,
  product_item_name: null,
  filament_grams: "0",
  filaments: [],
  filament_ready: false,
  print_hours: "0",
  unit_cost: "0",
  quantity: "1",
  unit_price: "12",
  variant: "plain",
  channel: "direct",
  order_number: null,
  note: null,
  started_at: null,
  finished_at: null,
  created_at: "2026-10-20T00:00:00.000Z",
  updated_at: "2026-10-20T00:00:00.000Z",
  version_id: 1,
};
const queries: Record<string, unknown> = {
  "/api/v1/settings/pricing": settings,
  "/api/v1/production/jobs": [job],
  "/api/v1/production/summary": {
    planned: 1,
    in_progress: 0,
    done: 0,
    filament_grams_planned: "10",
  },
  "/api/v1/warehouse/summary": {
    items: [
      { id: "f", name: "فیلامنت", kind: "FILAMENT", unit: "G", quantity: "1000" },
      { id: "p", name: "محصول", kind: "PRODUCT", unit: "PCS", quantity: "0" },
    ],
  },
  "/api/v1/orders": [
    {
      id: "o1",
      order_number: 1,
      customer_name: "مشتری",
      status: "CONFIRMED",
      channel: "direct",
      items: lines,
    },
  ],
};
const clients: QueryClient[] = [];
function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  clients.push(client);
  render(
    <QueryClientProvider client={client}>
      <ProductionPage />
    </QueryClientProvider>,
  );
}
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.GET).mockImplementation((async (path: string) => ({
    data: queries[path],
    response: new Response(),
  })) as typeof api.GET);
  vi.mocked(api.POST).mockResolvedValue({ data: {}, response: new Response() } as never);
  vi.mocked(api.PATCH).mockResolvedValue({ data: {}, response: new Response() } as never);
});
afterEach(() => {
  cleanup();
  clients.splice(0).forEach((c) => c.clear());
});

it("selects any order line and preserves its old cost, price, variant and direct channel", async () => {
  mount();
  await screen.findByRole("option", { name: /مشتری/ });
  fireEvent.change(screen.getByTestId("job-order"), { target: { value: "o1" } });
  fireEvent.change(screen.getByTestId("job-order-line"), { target: { value: "l2" } });
  expect(screen.getByTestId("job-product")).toHaveValue("محصول دوم");
  expect(screen.getByTestId("job-price-snapshot")).toHaveTextContent("۴۵۶.۱۲۳۴");
  fireEvent.change(screen.getByTestId("job-spool-0-item"), { target: { value: "f" } });
  fireEvent.change(screen.getByTestId("job-spool-0-grams"), { target: { value: "12.5" } });
  fireEvent.click(screen.getByTestId("job-submit"));
  await waitFor(() => expect(api.POST).toHaveBeenCalled());
  const args = vi.mocked(api.POST).mock.calls as unknown as Array<
    [string, { body: Record<string, string> }]
  >;
  expect(args[0][1].body).toMatchObject({
    order_id: "o1",
    order_item_id: "l2",
    variant: "chain",
    channel: "direct",
    unit_cost: "56.1234",
    unit_price: "456.1234",
    filaments: [{ filament_item_id: "f", grams_per_unit: "12.5" }],
    filament_grams: "12.5",
  });
});

it("repairs a saved job's stock mapping using its current optimistic revision", async () => {
  mount();
  await screen.findByTestId("job-j1-configure");
  expect(screen.getByTestId("job-j1-finish")).toBeDisabled();
  fireEvent.click(screen.getByTestId("job-j1-configure"));
  fireEvent.click(screen.getByTestId("job-mapping-add"));
  fireEvent.change(screen.getByTestId("job-mapping-filament-0"), { target: { value: "f" } });
  fireEvent.change(screen.getByTestId("job-mapping-product"), { target: { value: "p" } });
  fireEvent.change(screen.getByTestId("job-mapping-grams-0"), { target: { value: "۱۲.۵" } });
  fireEvent.click(screen.getByTestId("job-mapping-save"));
  await waitFor(() => expect(api.PATCH).toHaveBeenCalled());
  const calls = vi.mocked(api.PATCH).mock.calls as unknown as Array<
    [string, { body: Record<string, unknown> }]
  >;
  expect(calls[0][1].body).toMatchObject({
    version_id: 1,
    product_item_id: "p",
    filaments: [{ filament_item_id: "f", grams_per_unit: "12.5" }],
  });
  await waitFor(() => expect(screen.queryByTestId("job-stock-editor")).not.toBeInTheDocument());
});

it("failed job loading never claims an empty queue and offers retry", async () => {
  vi.mocked(api.GET).mockRejectedValue(new Error("offline"));
  mount();
  await screen.findAllByRole("alert");
  expect(screen.queryByText("کار تولیدی ثبت نشده است.")).not.toBeInTheDocument();
});

it("never creates a zero-priced manual job after malformed pricing input", async () => {
  mount();
  await screen.findByTestId("job-j1-configure");
  fireEvent.change(screen.getByTestId("job-product"), { target: { value: "bad" } });
  fireEvent.change(screen.getByTestId("job-spool-0-item"), { target: { value: "f" } });
  fireEvent.change(screen.getByTestId("job-spool-0-grams"), { target: { value: "bad-number" } });
  fireEvent.click(screen.getByTestId("job-submit"));
  await waitFor(() => expect(screen.getByTestId("production-message")).toBeInTheDocument());
  expect(api.POST).not.toHaveBeenCalled();
});

it("collects older orders past the API page boundary", async () => {
  const load = vi.fn(async (offset: number) =>
    offset === 0 ? Array.from({ length: 500 }, (_, i) => i) : [500],
  );
  expect(await collectOperationPages(load)).toHaveLength(501);
  expect(load.mock.calls.map(([offset]) => offset)).toEqual([0, 500]);
});

it("pagination does not offer a missing previous or next page", () => {
  const onChange = vi.fn();
  const { rerender } = render(
    <OperationPagination page={0} next busy={false} onChange={onChange} />,
  );
  expect(screen.getByRole("button", { name: "صفحهٔ قبل" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "صفحهٔ بعد" }));
  expect(onChange).toHaveBeenCalledWith(1);
  rerender(<OperationPagination page={1} next={false} busy={false} onChange={onChange} />);
  expect(screen.getByRole("button", { name: "صفحهٔ بعد" })).toBeDisabled();
});
