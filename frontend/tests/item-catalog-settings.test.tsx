import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { api } from "@/api/client";
import { ItemCatalogSettings } from "@/components/item-catalog-settings";
import { itemUnitLabel } from "@/lib/item-catalog";

const rows = [
  { id: "custom", name: "رزین", is_active: true, version_id: 7 },
  { id: "inactive", name: "غیرفعال قدیمی", is_active: false, version_id: 3 },
];
const clients: QueryClient[] = [];
function mount(role = "OWNER") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity }, mutations: { retry: false } },
  });
  clients.push(client);
  client.setQueryData(["session-user"], { role });
  for (const category of ["types", "units"])
    client.setQueryData(["warehouse", "catalog", category], rows);
  client.setQueryData(["warehouse", "suppliers"], rows);
  render(
    <QueryClientProvider client={client}>
      <ItemCatalogSettings />
    </QueryClientProvider>,
  );
  return client;
}
beforeEach(() => {
  vi.spyOn(api, "GET").mockResolvedValue({ data: rows, response: new Response() } as never);
});
afterEach(() => {
  cleanup();
  clients.splice(0).forEach((c) => c.clear());
  vi.restoreAllMocks();
});

it.each(["types", "units", "suppliers"])(
  "confirms deletion and sends the visible revision for %s",
  async (category) => {
    const remove = vi.spyOn(api, "DELETE").mockResolvedValue({
      data: { action: "deactivated", reason: "برای حفظ سوابق غیرفعال شد", version_id: 8 },
      response: new Response(),
    } as never);
    mount();
    const panel = within(screen.getByTestId(`catalog-${category}`));
    fireEvent.click(panel.getByRole("button", { name: "حذف رزین" }));
    expect(remove).not.toHaveBeenCalled();
    const confirmation = panel.getByRole("alertdialog");
    expect(confirmation).toHaveTextContent("سوابق");
    fireEvent.click(within(confirmation).getByRole("button", { name: "تأیید حذف" }));
    await waitFor(() => expect(remove).toHaveBeenCalledOnce());
    const path =
      category === "suppliers"
        ? "/api/v1/warehouse/suppliers/{supplier_id}"
        : "/api/v1/warehouse/catalog/{category}/{ident}";
    expect(remove).toHaveBeenCalledWith(path, {
      params: {
        path: category === "suppliers" ? { supplier_id: "custom" } : { category, ident: "custom" },
        query: { version_id: 7 },
      },
    });
    expect(await panel.findByRole("status")).toHaveTextContent("برای حفظ سوابق");
  },
);

it("adds persisted choices and reactivates instead of duplicating inactive names", async () => {
  const post = vi
    .spyOn(api, "POST")
    .mockResolvedValue({ data: {}, response: new Response() } as never);
  const patch = vi
    .spyOn(api, "PATCH")
    .mockResolvedValue({ data: {}, response: new Response() } as never);
  mount();
  const panel = within(screen.getByTestId("catalog-types"));
  fireEvent.change(panel.getByLabelText("نام نوع کالا"), { target: { value: "رزین تازه" } });
  fireEvent.click(panel.getByRole("button", { name: "افزودن" }));
  await waitFor(() =>
    expect(post).toHaveBeenCalledWith("/api/v1/warehouse/catalog/{category}", {
      params: { path: { category: "types" } },
      body: { name: "رزین تازه" },
    }),
  );
  await waitFor(() => expect(panel.getByLabelText("نام نوع کالا")).toHaveValue(""));
  fireEvent.click(panel.getByRole("button", { name: "فعال‌سازی غیرفعال قدیمی" }));
  await waitFor(() =>
    expect(patch).toHaveBeenCalledWith("/api/v1/warehouse/catalog/{category}/{ident}", {
      params: { path: { category: "types", ident: "inactive" } },
      body: { version_id: 3, is_active: true },
    }),
  );
});

it("keeps a stale confirmation visible and requires an explicit refresh", async () => {
  vi.spyOn(api, "DELETE").mockResolvedValue({
    error: {},
    response: new Response(JSON.stringify({ detail: "گزینه هم‌زمان تغییر کرده است" }), {
      status: 409,
    }),
  } as never);
  mount();
  const panel = within(screen.getByTestId("catalog-units"));
  fireEvent.click(panel.getByRole("button", { name: "حذف رزین" }));
  fireEvent.click(panel.getByRole("button", { name: "تأیید حذف" }));
  expect(await panel.findByRole("alert")).toHaveTextContent("هم‌زمان");
  expect(panel.getByRole("alertdialog")).toBeVisible();
  fireEvent.click(panel.getByRole("button", { name: "تازه‌سازی فهرست" }));
  expect(panel.queryByRole("alertdialog")).not.toBeInTheDocument();
});

it("shows auditor data without offering writable controls", () => {
  const post = vi.spyOn(api, "POST");
  mount("AUDITOR");
  expect(screen.getByText("اطلاعات پایه در حالت فقط خواندنی است.")).toBeVisible();
  for (const category of ["types", "units", "suppliers"]) {
    const panel = within(screen.getByTestId(`catalog-${category}`));
    expect(panel.getByRole("button", { name: "افزودن" })).toBeDisabled();
    expect(panel.getByRole("button", { name: "حذف رزین" })).toBeDisabled();
  }
  expect(post).not.toHaveBeenCalled();
});

it("never labels arbitrary units as pieces or grams", () => {
  expect(itemUnitLabel({ unit: "opaque", unit_name: "لیتر" })).toBe("لیتر");
  expect(itemUnitLabel({ unit: "opaque" })).toBe("opaque");
  expect(itemUnitLabel({ unit: "G" })).toBe("گرم");
});
