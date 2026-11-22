import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
      { id: "f2", name: "PETG", color: "آبی", kind: "FILAMENT", unit: "G", quantity: "500" },
      { id: "f3", name: "PLA سفید", color: "سفید", kind: "FILAMENT", unit: "G", quantity: "250" },
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

it("picks a job's filament composition inline with its current revision", async () => {
  mount();
  await screen.findByTestId("job-j1-filaments");
  // the old «اتصال انبار» mapping panel is gone
  expect(screen.queryByTestId("job-stock-editor")).not.toBeInTheDocument();
  fireEvent.click(screen.getByTestId("job-j1-filaments"));
  fireEvent.change(screen.getByTestId("job-filament-editor-item-0"), {
    target: { value: "f" },
  });
  fireEvent.change(screen.getByTestId("job-filament-editor-grams-0"), {
    target: { value: "۱۲.۵" },
  });
  fireEvent.click(screen.getByTestId("job-filament-editor-save"));
  await waitFor(() => expect(api.PATCH).toHaveBeenCalled());
  const calls = vi.mocked(api.PATCH).mock.calls as unknown as Array<
    [string, { body: Record<string, unknown> }]
  >;
  expect(calls[0][1].body).toMatchObject({
    version_id: 1,
    filaments: [{ filament_item_id: "f", grams_per_unit: "12.5" }],
  });
  await waitFor(() => expect(screen.queryByTestId("job-filament-editor")).not.toBeInTheDocument());
});

it("retries a stale filament save with the job's fresh revision", async () => {
  const saved = {
    ...job,
    version_id: 8,
    filament_grams: "12.5",
    filament_ready: true,
    filaments: [
      {
        id: "pf1",
        filament_item_id: "f",
        filament_item_name: "فیلامنت",
        grams_per_unit: "12.5",
        grams_total: "12.5",
      },
    ],
  };
  let list: unknown[] = [job];
  vi.mocked(api.GET).mockImplementation((async (path: string) => {
    if (path === "/api/v1/production/jobs/{job_id}")
      return { data: { ...job, version_id: 8 }, response: new Response() };
    return {
      data: path === "/api/v1/production/jobs" ? list : queries[path],
      response: new Response(),
    };
  }) as typeof api.GET);
  const conflict = {
    title: "Conflict",
    status: 409,
    detail: "production job #1 was modified concurrently (expected 1, found 8)",
    code: "stale_version",
  };
  vi.mocked(api.PATCH)
    .mockResolvedValueOnce({
      error: conflict,
      response: new Response(JSON.stringify(conflict), {
        status: 409,
        headers: { "Content-Type": "application/problem+json" },
      }),
    } as never)
    .mockImplementationOnce((async () => {
      list = [saved];
      return { data: saved, response: new Response() };
    }) as typeof api.PATCH);

  mount();
  await screen.findByTestId("job-j1-filaments");
  fireEvent.click(screen.getByTestId("job-j1-filaments"));
  fireEvent.change(screen.getByTestId("job-filament-editor-item-0"), {
    target: { value: "f" },
  });
  fireEvent.change(screen.getByTestId("job-filament-editor-grams-0"), {
    target: { value: "12.5" },
  });
  fireEvent.click(screen.getByTestId("job-filament-editor-save"));

  await waitFor(() => expect(api.PATCH).toHaveBeenCalledTimes(2));
  const calls = vi.mocked(api.PATCH).mock.calls as unknown as Array<
    [string, { body: { version_id: number; filaments: unknown[] } }]
  >;
  expect(calls.map((call) => call[1].body.version_id)).toEqual([1, 8]);
  expect(calls[1][1].body.filaments).toEqual([{ filament_item_id: "f", grams_per_unit: "12.5" }]);
  await waitFor(() => expect(screen.queryByTestId("job-filament-editor")).not.toBeInTheDocument());
  expect(screen.getByTestId("job-j1-spools")).toHaveTextContent("فیلامنت");
});

it("keeps a half-filled filament row instead of saving an empty composition", async () => {
  mount();
  await screen.findByTestId("job-j1-filaments");
  fireEvent.click(screen.getByTestId("job-j1-filaments"));
  fireEvent.change(screen.getByTestId("job-filament-editor-item-0"), {
    target: { value: "f" },
  });
  fireEvent.click(screen.getByTestId("job-filament-editor-save"));

  expect(await screen.findByTestId("job-filament-editor-error")).toHaveTextContent(
    "«گرم هر عدد» را وارد کنید",
  );
  expect(api.PATCH).not.toHaveBeenCalled();
  expect(screen.getByTestId("job-filament-editor")).toBeInTheDocument();
});

it("shows a rejected filament save inside the editor", async () => {
  const problem = {
    title: "Bad Request",
    status: 400,
    detail: "«فیلامنت» فیلامنت فعال با واحد گرم نیست و در تولید قابل انتخاب نیست",
    code: "invalid_item",
  };
  vi.mocked(api.PATCH).mockResolvedValue({
    error: problem,
    response: new Response(JSON.stringify(problem), {
      status: 400,
      headers: { "Content-Type": "application/problem+json" },
    }),
  } as never);

  mount();
  await screen.findByTestId("job-j1-filaments");
  fireEvent.click(screen.getByTestId("job-j1-filaments"));
  fireEvent.change(screen.getByTestId("job-filament-editor-item-0"), {
    target: { value: "f" },
  });
  fireEvent.change(screen.getByTestId("job-filament-editor-grams-0"), {
    target: { value: "12.5" },
  });
  fireEvent.click(screen.getByTestId("job-filament-editor-save"));

  expect(await screen.findByTestId("job-filament-editor-error")).toHaveTextContent(
    "فیلامنت فعال با واحد گرم نیست",
  );
  expect(screen.getByTestId("job-filament-editor")).toBeInTheDocument();
});

it("writes each spool's colour beside its name in both filament choosers", async () => {
  mount();
  await screen.findByTestId("job-j1-filaments");
  // the «ثبت کار تولید» form and the inline editor both list the same spools
  expect(screen.getAllByRole("option", { name: "PETG — رنگ آبی (۵۰۰ گرم)" })).toHaveLength(1);
  fireEvent.click(screen.getByTestId("job-j1-filaments"));
  const coloured = screen.getAllByRole("option", { name: "PETG — رنگ آبی (۵۰۰ گرم)" });
  expect(coloured).toHaveLength(2);
  // a name that already ends with the colour is not repeated
  expect(screen.queryByRole("option", { name: /PLA سفید — رنگ سفید/ })).not.toBeInTheDocument();
  expect(screen.getAllByRole("option", { name: "PLA سفید (۲۵۰ گرم)" }).length).toBeGreaterThan(0);
  // and a spool without a colour keeps its plain name
  expect(screen.getAllByRole("option", { name: "فیلامنت (۱٬۰۰۰ گرم)" }).length).toBeGreaterThan(0);
});

it("asks for the missing spools instead of disabling the finish button", async () => {
  mount();
  const finish = await screen.findByTestId("job-j1-finish");
  expect(finish).toBeEnabled();
  fireEvent.click(finish);
  expect(api.POST).not.toHaveBeenCalled();
  expect(screen.getByTestId("job-filament-editor")).toBeInTheDocument();
  expect(screen.getByTestId("production-message")).toHaveTextContent("ابتدا فیلامنت‌های مصرفی");
});

it("shows a rejected finish beside its own row", async () => {
  const ready = {
    ...job,
    status: "IN_PROGRESS",
    filament_ready: true,
    filament_grams: "12.5",
    filaments: [
      {
        id: "pf1",
        filament_item_id: "f",
        filament_item_name: "فیلامنت",
        grams_per_unit: "12.5",
        grams_total: "12.5",
      },
    ],
  };
  vi.mocked(api.GET).mockImplementation((async (path: string) => ({
    data: path === "/api/v1/production/jobs" ? [ready] : queries[path],
    response: new Response(),
  })) as typeof api.GET);
  const problem = {
    title: "Bad Request",
    status: 400,
    detail: "محصول «محصول» در انبار غیرفعال است؛ ابتدا آن را در انبار فعال کنید",
    code: "invalid_item",
  };
  vi.mocked(api.POST).mockResolvedValue({
    error: problem,
    response: new Response(JSON.stringify(problem), {
      status: 400,
      headers: { "Content-Type": "application/problem+json" },
    }),
  } as never);

  mount();
  fireEvent.click(await screen.findByTestId("job-j1-finish"));

  expect(await screen.findByTestId("job-j1-action-error")).toHaveTextContent(
    "در انبار غیرفعال است",
  );
  expect(screen.getByTestId("production-message")).toHaveTextContent("در انبار غیرفعال است");
});

it("finishes a job that has its filaments, and the order quantity is beside it", async () => {
  const ready = {
    ...job,
    order_number: 7,
    order_item_quantity: "5",
    quantity: "2",
    filament_ready: true,
    filaments: [
      {
        id: "pf1",
        filament_item_id: "f",
        filament_item_name: "فیلامنت",
        grams_per_unit: "10",
        unit_cost: "100",
        grams_total: "20",
      },
    ],
  };
  vi.mocked(api.GET).mockImplementation((async (path: string) => ({
    data: path === "/api/v1/production/jobs" ? [ready] : (queries as Record<string, unknown>)[path],
    response: new Response(),
  })) as typeof api.GET);
  mount();
  const row = await screen.findByTestId("job-j1");
  expect(row).toHaveTextContent("سفارش #۷");
  expect(row).toHaveTextContent("۲ عدد");
  expect(row).toHaveTextContent("از ۵ عدد سفارش");
  fireEvent.click(screen.getByTestId("job-j1-finish"));
  await waitFor(() => expect(api.POST).toHaveBeenCalled());
  const calls = vi.mocked(api.POST).mock.calls as unknown as Array<[string]>;
  expect(calls[0][0]).toBe("/api/v1/production/jobs/{job_id}/finish");
});

it("offers only active, unfinished orders for a new production job", async () => {
  const baseOrder = {
    id: "o1",
    order_number: 1,
    customer_name: "مشتری",
    channel: "direct",
    items: lines,
  };
  vi.mocked(api.GET).mockImplementation((async (path: string) => ({
    data:
      path === "/api/v1/orders"
        ? [
            { ...baseOrder, status: "CONFIRMED" },
            { ...baseOrder, id: "o2", order_number: 2, status: "READY" },
            { ...baseOrder, id: "o3", order_number: 3, status: "SHIPPED" },
            { ...baseOrder, id: "o4", order_number: 4, status: "CANCELLED" },
          ]
        : (queries as Record<string, unknown>)[path],
    response: new Response(),
  })) as typeof api.GET);
  mount();
  const select = await screen.findByTestId("job-order");
  await waitFor(() => expect(within(select).getAllByRole("option")).toHaveLength(2));
  expect(within(select).getByRole("option", { name: /#1/ })).toBeInTheDocument();
  expect(within(select).queryByRole("option", { name: /#2/ })).not.toBeInTheDocument();
});

it("failed job loading never claims an empty queue and offers retry", async () => {
  vi.mocked(api.GET).mockRejectedValue(new Error("offline"));
  mount();
  await screen.findAllByRole("alert");
  expect(screen.queryByText("کار تولیدی ثبت نشده است.")).not.toBeInTheDocument();
});

it("never creates a zero-priced manual job after malformed pricing input", async () => {
  mount();
  await screen.findByTestId("job-j1-filaments");
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
