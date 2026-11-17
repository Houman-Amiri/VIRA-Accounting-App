import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { api } from "@/api/client";
import { renderWithPricing, SETTINGS } from "./helpers/pricing";
import { PricingSettingsPage } from "@/routes/pricing-settings";
import { PriceCalcPage } from "@/routes/price-calc";
import type { CustomConstant } from "@/lib/pricing-settings";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const PACKAGING: CustomConstant = {
  id: "c1",
  name: "هزینهٔ بسته‌بندی",
  method: "PER_UNIT",
  value: "12000.0000",
  is_active: true,
  position: 0,
  created_at: "2026-10-16T00:00:00Z",
  updated_at: "2026-10-16T00:00:00Z",
};

/** Render the pricing page with the given custom constants already cached. */
function renderPricingPage(customs: CustomConstant[] = []) {
  return renderWithPricing(<PricingSettingsPage />, {}, true, customs);
}

describe("pricing settings page", () => {
  it("saves Persian decimals through the real hook and updates the shared cache", async () => {
    const saved = { ...SETTINGS, filamentPerGram: "4000.2500", version_id: 2 };
    const put = vi
      .spyOn(api, "PUT")
      .mockResolvedValue({ data: saved, response: new Response() } as never);
    const { client } = renderWithPricing(<PricingSettingsPage />);
    fireEvent.change(screen.getByTestId("const-filamentPerGram"), {
      target: { value: "۴۰۰۰٫۲۵" },
    });
    fireEvent.click(screen.getByRole("button", { name: "ذخیرهٔ ثابت‌های اصلی" }));
    await screen.findByText("ثابت‌های اصلی ذخیره شدند.");
    const { updated_at: _timestamp, ...values } = SETTINGS;
    expect(put).toHaveBeenCalledWith("/api/v1/settings/pricing", {
      body: { ...values, filamentPerGram: "4000.2500" },
    });
    expect(client.getQueryData(["pricing-settings"])).toEqual(saved);
  });

  it.each(["-1", "abc", "0.12345", "1000000000001"])(
    "rejects invalid constants %s before sending",
    async (value) => {
      const put = vi.spyOn(api, "PUT");
      renderWithPricing(<PricingSettingsPage />);
      fireEvent.change(screen.getByTestId("const-filamentPerGram"), { target: { value } });
      fireEvent.click(screen.getByRole("button", { name: "ذخیرهٔ ثابت‌های اصلی" }));
      await screen.findByRole("alert");
      expect(put).not.toHaveBeenCalled();
    },
  );

  it("preserves the edited draft and shows the server's conflict message", async () => {
    vi.spyOn(api, "PUT").mockResolvedValue({
      error: {},
      response: new Response(
        JSON.stringify({
          code: "stale_version",
          detail: "ثابت‌ها تغییر کرده‌اند؛ دوباره بارگذاری کنید.",
        }),
        { status: 409 },
      ),
    } as never);
    renderWithPricing(<PricingSettingsPage />);
    fireEvent.change(screen.getByTestId("const-filamentPerGram"), { target: { value: "5000" } });
    fireEvent.click(screen.getByRole("button", { name: "ذخیرهٔ ثابت‌های اصلی" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("دوباره بارگذاری کنید");
    expect(screen.getByTestId("const-filamentPerGram")).toHaveValue("5000");
    expect(screen.queryByText("ثابت‌های اصلی ذخیره شدند.")).not.toBeInTheDocument();
  });

  it("does not persist defaults before explicit save", () => {
    const put = vi.spyOn(api, "PUT");
    const { client } = renderWithPricing(<PricingSettingsPage />, { filamentPerGram: "4000.0000" });
    fireEvent.click(screen.getByRole("button", { name: "مقادیر پیش‌فرض" }));
    expect(screen.getByTestId("const-filamentPerGram")).toHaveValue("3000");
    expect(client.getQueryData(["pricing-settings"])).toMatchObject({
      filamentPerGram: "4000.0000",
    });
    expect(put).not.toHaveBeenCalled();
  });

  it("shows the Persian label and the amount of every custom constant", () => {
    renderPricingPage([PACKAGING]);
    const row = within(screen.getByTestId(`custom-row-${PACKAGING.id}`));
    expect(row.getByText("هزینهٔ بسته‌بندی")).toBeInTheDocument();
    expect(row.getByText("مبلغ ثابت برای هر عدد")).toBeInTheDocument();
    expect(row.getByText("۱۲٬۰۰۰")).toBeInTheDocument();
    expect(row.getByText("فعال")).toBeInTheDocument();
  });

  it("explains how each calculation method works in the add form", () => {
    renderPricingPage();
    expect(screen.getByTestId("custom-empty")).toBeInTheDocument();
    fireEvent.change(screen.getByTestId("custom-method"), { target: { value: "PER_BATCH" } });
    expect(screen.getByTestId("custom-method-hint")).toHaveTextContent(
      "بین تعداد سفارش تقسیم می‌شود",
    );
    expect(screen.getByRole("button", { name: "افزودن ثابت" })).toBeInTheDocument();
    expect(screen.getByLabelText("مبلغ (تومان)")).toBeInTheDocument();
  });

  it("adds a trimmed custom constant through POST", async () => {
    const created = { ...PACKAGING, name: "کارمزد پست", method: "PER_BATCH" as const };
    const post = vi
      .spyOn(api, "POST")
      .mockResolvedValue({ data: created, response: new Response() } as never);
    renderPricingPage();
    fireEvent.change(screen.getByTestId("custom-name"), { target: { value: "  کارمزد پست  " } });
    fireEvent.change(screen.getByTestId("custom-method"), { target: { value: "PER_BATCH" } });
    fireEvent.change(screen.getByTestId("custom-value"), { target: { value: "۵۰٬۰۰۰" } });
    fireEvent.click(screen.getByRole("button", { name: "افزودن ثابت" }));
    await waitFor(() => expect(post).toHaveBeenCalled());
    expect(post).toHaveBeenCalledWith("/api/v1/settings/pricing/constants", {
      body: { name: "کارمزد پست", method: "PER_BATCH", value: "50000.0000", is_active: true },
    });
    await waitFor(() => expect(screen.getByTestId("custom-name")).toHaveValue(""));
  });

  it("refuses an empty name or a negative amount without calling the server", async () => {
    const post = vi.spyOn(api, "POST");
    renderPricingPage();
    fireEvent.change(screen.getByTestId("custom-value"), { target: { value: "1000" } });
    fireEvent.click(screen.getByRole("button", { name: "افزودن ثابت" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("نام");
    fireEvent.change(screen.getByTestId("custom-name"), { target: { value: "بسته‌بندی" } });
    fireEvent.change(screen.getByTestId("custom-value"), { target: { value: "-5" } });
    fireEvent.click(screen.getByRole("button", { name: "افزودن ثابت" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("منفی");
    expect(post).not.toHaveBeenCalled();
  });

  it("turns a constant off with PATCH and leaves the name alone", async () => {
    const patch = vi.spyOn(api, "PATCH").mockResolvedValue({
      data: { ...PACKAGING, is_active: false },
      response: new Response(),
    } as never);
    renderPricingPage([PACKAGING]);
    fireEvent.click(screen.getByTestId(`custom-toggle-${PACKAGING.id}`));
    await waitFor(() => expect(patch).toHaveBeenCalled());
    expect(patch).toHaveBeenCalledWith("/api/v1/settings/pricing/constants/{constant_id}", {
      params: { path: { constant_id: PACKAGING.id } },
      body: { is_active: false },
    });
  });

  it("edits name, method and value together", async () => {
    const patch = vi
      .spyOn(api, "PATCH")
      .mockResolvedValue({ data: PACKAGING, response: new Response() } as never);
    renderPricingPage([PACKAGING]);
    fireEvent.click(screen.getByTestId(`custom-edit-${PACKAGING.id}`));
    fireEvent.change(screen.getByTestId(`custom-edit-name-${PACKAGING.id}`), {
      target: { value: "بسته‌بندی" },
    });
    fireEvent.change(screen.getByTestId(`custom-method-${PACKAGING.id}`), {
      target: { value: "PERCENT_OF_PRICE" },
    });
    fireEvent.change(screen.getByTestId(`custom-value-${PACKAGING.id}`), {
      target: { value: "3" },
    });
    fireEvent.click(screen.getByTestId(`custom-save-${PACKAGING.id}`));
    await waitFor(() => expect(patch).toHaveBeenCalled());
    expect(patch).toHaveBeenCalledWith("/api/v1/settings/pricing/constants/{constant_id}", {
      params: { path: { constant_id: PACKAGING.id } },
      body: { name: "بسته‌بندی", method: "PERCENT_OF_PRICE", value: "3.0000" },
    });
  });

  it("deletes a constant through DELETE", async () => {
    const del = vi.spyOn(api, "DELETE").mockResolvedValue({
      data: undefined,
      response: new Response(null, { status: 204 }),
    } as never);
    renderPricingPage([PACKAGING]);
    fireEvent.click(screen.getByTestId(`custom-delete-${PACKAGING.id}`));
    await waitFor(() => expect(del).toHaveBeenCalled());
    expect(del).toHaveBeenCalledWith("/api/v1/settings/pricing/constants/{constant_id}", {
      params: { path: { constant_id: PACKAGING.id } },
    });
  });

  it("shows the live effect of active constants and ignores the switched-off ones", () => {
    const off: CustomConstant = { ...PACKAGING, id: "c2", name: "کارمزد پست", is_active: false };
    renderPricingPage([PACKAGING, off]);
    const preview = within(screen.getByTestId("pricing-preview"));
    expect(preview.getByTestId(`preview-row-${PACKAGING.id}`)).toHaveTextContent(
      "هزینهٔ بسته‌بندی",
    );
    expect(preview.queryByTestId(`preview-row-${off.id}`)).not.toBeInTheDocument();
  });

  it("blocks calculation rather than falling back to default prices if settings fail", async () => {
    vi.spyOn(api, "GET").mockResolvedValue({
      error: {},
      response: new Response("offline", { status: 503 }),
    } as never);
    renderWithPricing(<PriceCalcPage />, {}, false);
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("ناموفق"));
    expect(screen.queryByTestId("row-unitFinalPrice")).not.toBeInTheDocument();
  });
});
