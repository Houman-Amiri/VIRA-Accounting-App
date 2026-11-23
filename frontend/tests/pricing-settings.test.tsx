import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { api } from "@/api/client";
import { renderWithPricing, SETTINGS } from "./helpers/pricing";
import { PricingSettingsPage } from "@/routes/pricing-settings";
import { PriceCalcPage } from "@/routes/price-calc";
import type { CustomConstant, PricingVariable } from "@/lib/pricing-settings";

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

const RATE: PricingVariable = {
  id: "v1",
  name: "نرخ دلار",
  scope: "PER_UNIT",
  basis: "PERCENT_OF_COST",
  allocation: "SPLIT",
  value: "7.5000",
  is_active: true,
  is_design_rate: false,
  position: 1,
  created_at: "2026-10-16T00:00:00Z",
  updated_at: "2026-10-16T00:00:00Z",
};

/** Render the pricing page with the owner's constants and variables cached. */
function renderPricingPage(customs: CustomConstant[] = [], variables: PricingVariable[] = []) {
  return renderWithPricing(<PricingSettingsPage />, {}, true, customs, variables);
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

describe("pricing variables", () => {
  it("lists a variable with its scope, basis and default value", () => {
    renderPricingPage([], [RATE]);
    const row = within(screen.getByTestId(`variable-row-${RATE.id}`));
    expect(row.getByText("نرخ دلار")).toBeInTheDocument();
    expect(row.getByText("جزیی (هر عدد)")).toBeInTheDocument();
    expect(row.getByText("درصدی از بهای تمام‌شده")).toBeInTheDocument();
    expect(row.getByText("۷.۵۰۰۰٪")).toBeInTheDocument();
    expect(row.getByText("فعال")).toBeInTheDocument();
  });

  it("shows the whole-order allocation only for a کلی variable", () => {
    renderPricingPage([], [{ ...RATE, id: "v2", scope: "PER_ORDER", allocation: "ONE_TIME" }]);
    const row = within(screen.getByTestId("variable-row-v2"));
    expect(row.getByText("کلی (کل سفارش)")).toBeInTheDocument();
    expect(row.getByText("یک‌جا روی جمع کل سفارش")).toBeInTheDocument();
    // a per-piece variable never shows the allocation choice as a row detail
    renderPricingPage([], [RATE]);
    expect(within(screen.getByTestId(`variable-row-${RATE.id}`)).queryByText(/یک‌جا/)).toBeNull();
  });

  it("adds a variable through POST with the normalized allocation", async () => {
    const post = vi
      .spyOn(api, "POST")
      .mockResolvedValue({ data: { ...RATE, id: "new" }, response: new Response() } as never);
    renderPricingPage();
    expect(screen.getByTestId("variables-empty")).toBeInTheDocument();
    fireEvent.change(screen.getByTestId("variable-name"), { target: { value: "  نرخ دلار  " } });
    fireEvent.change(screen.getByTestId("variable-basis"), {
      target: { value: "PERCENT_OF_COST" },
    });
    fireEvent.change(screen.getByTestId("variable-value"), { target: { value: "۷٫۵" } });
    fireEvent.click(screen.getByTestId("variable-submit"));
    await waitFor(() => expect(post).toHaveBeenCalled());
    expect(post).toHaveBeenCalledWith("/api/v1/settings/pricing/variables", {
      body: {
        name: "نرخ دلار",
        scope: "PER_UNIT",
        basis: "PERCENT_OF_COST",
        allocation: "SPLIT",
        value: "7.5000",
        is_active: true,
        is_design_rate: false,
      },
    });
  });

  it("offers the یکی/تقسیم choice only when the scope is کلی", async () => {
    const post = vi
      .spyOn(api, "POST")
      .mockResolvedValue({ data: RATE, response: new Response() } as never);
    renderPricingPage();
    expect(screen.queryByTestId("variable-allocation")).not.toBeInTheDocument();
    fireEvent.change(screen.getByTestId("variable-scope"), { target: { value: "PER_ORDER" } });
    expect(screen.getByTestId("variable-allocation")).toBeInTheDocument();
    fireEvent.change(screen.getByTestId("variable-name"), { target: { value: "مالیات" } });
    fireEvent.change(screen.getByTestId("variable-basis"), {
      target: { value: "PERCENT_OF_PRICE" },
    });
    fireEvent.change(screen.getByTestId("variable-allocation"), {
      target: { value: "ONE_TIME" },
    });
    fireEvent.change(screen.getByTestId("variable-value"), { target: { value: "9" } });
    fireEvent.click(screen.getByTestId("variable-submit"));
    await waitFor(() => expect(post).toHaveBeenCalled());
    expect(post).toHaveBeenCalledWith("/api/v1/settings/pricing/variables", {
      body: {
        name: "مالیات",
        scope: "PER_ORDER",
        basis: "PERCENT_OF_PRICE",
        allocation: "ONE_TIME",
        value: "9.0000",
        is_active: true,
        is_design_rate: false,
      },
    });
  });

  it("refuses a blank name or a negative default", async () => {
    const post = vi.spyOn(api, "POST");
    renderPricingPage();
    fireEvent.change(screen.getByTestId("variable-value"), { target: { value: "10" } });
    fireEvent.click(screen.getByTestId("variable-submit"));
    expect(await screen.findByRole("alert")).toHaveTextContent("نام");
    fireEvent.change(screen.getByTestId("variable-name"), { target: { value: "نرخ" } });
    fireEvent.change(screen.getByTestId("variable-value"), { target: { value: "-2" } });
    fireEvent.click(screen.getByTestId("variable-submit"));
    expect(await screen.findByRole("alert")).toHaveTextContent("منفی");
    expect(post).not.toHaveBeenCalled();
  });

  it("edits a variable through PATCH", async () => {
    const patch = vi
      .spyOn(api, "PATCH")
      .mockResolvedValue({ data: RATE, response: new Response() } as never);
    renderPricingPage([], [RATE]);
    fireEvent.click(screen.getByTestId(`variable-edit-${RATE.id}`));
    expect(screen.getByTestId("variable-name")).toHaveValue("نرخ دلار");
    fireEvent.change(screen.getByTestId("variable-value"), { target: { value: "10" } });
    fireEvent.click(screen.getByTestId("variable-submit"));
    await waitFor(() => expect(patch).toHaveBeenCalled());
    expect(patch).toHaveBeenCalledWith("/api/v1/settings/pricing/variables/{variable_id}", {
      params: { path: { variable_id: RATE.id } },
      body: {
        name: "نرخ دلار",
        scope: "PER_UNIT",
        basis: "PERCENT_OF_COST",
        allocation: "SPLIT",
        value: "10.0000",
        is_design_rate: false,
      },
    });
  });

  it("marks a money variable as the design-hour rate", async () => {
    const post = vi
      .spyOn(api, "POST")
      .mockResolvedValue({ data: RATE, response: new Response() } as never);
    renderPricingPage();
    fireEvent.change(screen.getByTestId("variable-name"), { target: { value: "طراحی" } });
    fireEvent.change(screen.getByTestId("variable-value"), { target: { value: "50000" } });
    // نرخ طراحی فقط با مبنای «مبلغ» معنا دارد؛ با درصد، جعبه خاموش می‌شود.
    fireEvent.change(screen.getByTestId("variable-basis"), {
      target: { value: "PERCENT_OF_COST" },
    });
    expect(within(screen.getByTestId("variable-design-rate")).getByRole("checkbox")).toBeDisabled();
    fireEvent.change(screen.getByTestId("variable-basis"), { target: { value: "AMOUNT" } });
    fireEvent.click(within(screen.getByTestId("variable-design-rate")).getByRole("checkbox"));

    fireEvent.click(screen.getByTestId("variable-submit"));
    await waitFor(() => expect(post).toHaveBeenCalled());
    expect(post).toHaveBeenCalledWith("/api/v1/settings/pricing/variables", {
      body: expect.objectContaining({ is_design_rate: true, value: "50000.0000" }),
    });
  });

  it("turns a variable off and deletes it", async () => {
    const patch = vi.spyOn(api, "PATCH").mockResolvedValue({
      data: { ...RATE, is_active: false },
      response: new Response(),
    } as never);
    const del = vi.spyOn(api, "DELETE").mockResolvedValue({
      data: undefined,
      response: new Response(null, { status: 204 }),
    } as never);
    renderPricingPage([], [RATE]);
    fireEvent.click(screen.getByTestId(`variable-toggle-${RATE.id}`));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith("/api/v1/settings/pricing/variables/{variable_id}", {
        params: { path: { variable_id: RATE.id } },
        body: { is_active: false },
      }),
    );
    fireEvent.click(screen.getByTestId(`variable-delete-${RATE.id}`));
    await waitFor(() =>
      expect(del).toHaveBeenCalledWith("/api/v1/settings/pricing/variables/{variable_id}", {
        params: { path: { variable_id: RATE.id } },
      }),
    );
  });

  it("shows the variable in the sample preview", () => {
    renderPricingPage([PACKAGING], [RATE]);
    const preview = within(screen.getByTestId("pricing-preview"));
    expect(preview.getByTestId("preview-variable-نرخ دلار")).toHaveTextContent("نرخ دلار");
    expect(preview.getByText("جمع نمونه (۱۰ عدد)")).toBeInTheDocument();
  });
});

it("displays monetary variable amounts without decimals, keeping exact values when editing", () => {
  const variable = {
    ...RATE,
    id: "m",
    name: "اجرت",
    basis: "AMOUNT" as const,
    value: "700000.4500",
  };
  renderPricingPage([], [variable]);
  expect(screen.getByTestId("variable-row-m")).toHaveTextContent("۷۰۰٬۰۰۰");
  expect(screen.getByTestId("variable-row-m")).not.toHaveTextContent("۷۰۰٬۰۰۰.۴۵");
  fireEvent.click(screen.getByTestId("variable-edit-m"));
  expect(screen.getByTestId("variable-value")).toHaveValue("700000.45");
});
