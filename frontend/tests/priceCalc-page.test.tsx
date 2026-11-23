import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { renderWithPricing } from "./helpers/pricing";
import { PriceCalcPage } from "@/routes/price-calc";

// Includes Persian RTL formatting and the real Money component (no pricing mocks).
afterEach(cleanup);

/** Fill the three numeric inputs the calculator waits for (item 8). */
function fillInputs(values: { weight?: string; hours?: string; qty?: string } = {}): void {
  fireEvent.change(screen.getByTestId("input-weight"), {
    target: { value: values.weight ?? "240" },
  });
  fireEvent.change(screen.getByTestId("input-hours"), {
    target: { value: values.hours ?? "10" },
  });
  fireEvent.change(screen.getByTestId("input-qty"), { target: { value: values.qty ?? "1" } });
}

describe("pricing page — literal Excel model", () => {
  it("starts empty and computes nothing before the user fills the inputs", () => {
    renderWithPricing(<PriceCalcPage />);
    expect(screen.getByTestId("input-weight")).toHaveValue("");
    expect(screen.getByTestId("input-hours")).toHaveValue("");
    expect(screen.getByTestId("input-qty")).toHaveValue("");
    expect(screen.getByTestId("price-empty")).toBeInTheDocument();
    expect(screen.queryByTestId("row-unitFinalPrice")).not.toBeInTheDocument();
    expect(screen.queryByTestId("final-badge")).not.toBeInTheDocument();
  });

  it.each([
    { weight: "240", hours: "10" },
    { weight: "240", qty: "1" },
    { hours: "10", qty: "1" },
  ])("stays empty while any single input is missing (%o)", (partial) => {
    renderWithPricing(<PriceCalcPage />);
    for (const [testId, value] of Object.entries(partial)) {
      const map: Record<string, string> = {
        weight: "input-weight",
        hours: "input-hours",
        qty: "input-qty",
      };
      fireEvent.change(screen.getByTestId(map[testId]), { target: { value } });
    }
    expect(screen.getByTestId("price-empty")).toBeInTheDocument();
    expect(screen.queryByTestId("row-unitFinalPrice")).not.toBeInTheDocument();
  });

  it("renders the actual cached workbook amounts once the inputs are entered", () => {
    renderWithPricing(<PriceCalcPage />);
    fillInputs();
    const row = within(screen.getByTestId("row-unitFinalPrice"));
    expect(screen.getAllByRole("columnheader").map((cell) => cell.textContent)).toEqual([
      "شرح ردیف",
      "ساده (تومان)",
      "زنجیردار (تومان)",
    ]);
    const table = screen.getByRole("table");
    expect(table).not.toHaveTextContent(/(?:[BE]\d+|سلول|فرمول|×)/);
    expect(table.querySelector("[title], [aria-description]")).toBeNull();
    expect(row.getByText("۲٬۷۶۰٬۷۴۸.۵")).toBeInTheDocument();
    expect(row.getByText("۲٬۷۸۰٬۷۴۸.۵")).toBeInTheDocument();
    expect(screen.queryByTestId("sheet-policy")).not.toBeInTheDocument();
    expect(screen.queryByText(/اکسل|xlsx/)).not.toBeInTheDocument();
  });

  it.each([
    ["productionTotal", "green"],
    ["unitSalePrice", "blue"],
    ["unitFinalPrice", "red"],
  ])("highlights the whole %s row in %s without helper columns", (key, color) => {
    renderWithPricing(<PriceCalcPage />);
    fillInputs();
    const row = screen.getByTestId(`row-${key}`);
    expect(within(row).getAllByRole("cell")).toHaveLength(3);
    expect(row).toHaveClass(`bg-${color}-100`, `dark:bg-${color}-900/40`, "font-semibold");
    fireEvent.change(screen.getByTestId("input-qty"), { target: { value: "10" } });
    expect(row).toHaveClass(`bg-${color}-100`, `dark:bg-${color}-900/40`);
  });

  it("does not color unrelated rows or the derived batch final price", () => {
    renderWithPricing(<PriceCalcPage />);
    fillInputs();
    const batchFinal = screen.getByTestId("row-batchFinalPrice");
    expect(batchFinal).toHaveClass("bg-muted/40");
    expect(batchFinal).not.toHaveClass("bg-red-100");
    expect(screen.getByTestId("row-filamentCost")).toHaveAttribute("class", "border-t");
  });

  it("recalculates quantity > 1 and Persian input using authored formulas", () => {
    renderWithPricing(<PriceCalcPage />);
    fillInputs({ qty: "۱۰" });
    const row = within(screen.getByTestId("row-unitFinalPrice"));
    expect(row.getByText("۲۹۱٬۱۹۴.۸۵")).toBeInTheDocument();
    expect(row.getByText("۳۱۱٬۱۹۴.۸۵")).toBeInTheDocument();
    expect(
      within(screen.getByTestId("row-productionTotal")).getByText("۹۱۴٬۰۰۰"),
    ).toBeInTheDocument();
  });

  it("multiplies a whole-order variable by the count typed next to it", () => {
    const shipping = {
      id: "var-shipping",
      name: "کرایه ارسال",
      scope: "PER_ORDER" as const,
      basis: "AMOUNT" as const,
      allocation: "ONE_TIME" as const,
      value: "100000.0000",
      is_active: true,
      position: 0,
      created_at: "2026-10-16T00:00:00Z",
      updated_at: "2026-10-16T00:00:00Z",
    };
    renderWithPricing(<PriceCalcPage />, {}, true, [], [shipping]);
    fillInputs({ qty: "10" });

    // پیش‌فرض ۱: همان اعداد پیش از افزودن تعداد، دست‌نخورده می‌مانند.
    expect(screen.getByTestId("variable-count-var-shipping")).toHaveValue("1");
    expect(screen.getByTestId("variable-line-var-shipping")).toHaveTextContent(
      "به جمع کل: ۱۰۰٬۰۰۰",
    );
    // «قیمت فروش هر عدد محصول» با تیراژ ۱۰: ۲۰۸٬۵۰۰ → جمع کل ۲٬۱۸۵٬۰۰۰
    expect(
      screen.getByText((_, node) => node?.textContent === "جمع کل سفارش (۱۰ عدد)۲٬۱۸۵٬۰۰۰"),
    ).toBeInTheDocument();

    // «۲ محموله»: مبلغ ۱۰۰٬۰۰۰ دو بار روی جمع کل می‌نشیند.
    fireEvent.change(screen.getByTestId("variable-count-var-shipping"), {
      target: { value: "۲" },
    });
    const line = screen.getByTestId("variable-line-var-shipping");
    expect(line).toHaveTextContent("۲ ×");
    expect(line).toHaveTextContent("به جمع کل: ۲۰۰٬۰۰۰");
    expect(
      screen.getByText((_, node) => node?.textContent === "جمع کل سفارش (۱۰ عدد)۲٬۲۸۵٬۰۰۰"),
    ).toBeInTheDocument();
    // قیمت هر عدد با «یک‌جا روی جمع کل» تغییر نمی‌کند.
    expect(screen.getByTestId("final-badge")).toHaveTextContent("۲۰۸٬۵۰۰");
  });

  it("clears only product inputs, keeping the saved pricing constants", () => {
    const { client } = renderWithPricing(<PriceCalcPage />, { filamentPerGram: "4000.0000" });
    fillInputs({ qty: "10" });
    fireEvent.click(screen.getByRole("button", { name: "پاک کردن ورودی‌ها" }));
    expect(screen.getByTestId("input-qty")).toHaveValue("");
    expect(screen.getByTestId("input-weight")).toHaveValue("");
    // No sales-channel chooser anywhere: only a direct sale is priced.
    expect(screen.queryByTestId("select-channel")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("کانال فروش")).not.toBeInTheDocument();
    expect(screen.getByTestId("price-empty")).toBeInTheDocument();
    expect(client.getQueryData(["pricing-settings"])).toMatchObject({
      filamentPerGram: "4000.0000",
    });
    expect(screen.queryByTestId("const-filamentPerGram")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "تغییر ثابت‌های قیمت‌گذاری" })).toHaveAttribute(
      "href",
      "/pricing-settings",
    );
  });

  it("keeps shared commission, unavailable chain amount and moved constant editors", () => {
    renderWithPricing(<PriceCalcPage />);
    fillInputs();
    const commission = within(screen.getByTestId("row-unitCommission"));
    const amounts = commission.getAllByRole("cell").slice(1);
    expect(amounts[0].textContent).toBe(amounts[1].textContent);
    expect(amounts[0].textContent).not.toBe("");
    const delivery = within(screen.getByTestId("row-saleWithDelivery"));
    expect(delivery.getAllByText("—")).toHaveLength(1);
    for (const key of ["printerPowerKw", "commissionPercent", "nylonPerUnit"]) {
      expect(screen.queryByTestId(`const-${key}`)).not.toBeInTheDocument();
    }
  });

  it("shows invalid input rather than an obsolete price, and can recover", () => {
    renderWithPricing(<PriceCalcPage />);
    fillInputs({ qty: "0" });
    expect(screen.getByText(/ورودی نامعتبر است/)).toBeInTheDocument();
    expect(screen.queryByTestId("row-unitFinalPrice")).not.toBeInTheDocument();
    fireEvent.change(screen.getByTestId("input-qty"), { target: { value: "1" } });
    expect(screen.getByTestId("row-unitFinalPrice")).toBeInTheDocument();
  });

  it("does not restore the previous values when the page is opened again", () => {
    const first = renderWithPricing(<PriceCalcPage />);
    fillInputs({ qty: "25" });
    expect(screen.getByTestId("input-qty")).toHaveValue("25");
    first.unmount();
    renderWithPricing(<PriceCalcPage />);
    expect(screen.getByTestId("input-qty")).toHaveValue("");
    expect(screen.getByTestId("input-weight")).toHaveValue("");
    expect(screen.getByTestId("price-empty")).toBeInTheDocument();
  });
});
