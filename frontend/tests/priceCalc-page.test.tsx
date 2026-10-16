import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { renderWithPricing } from "./helpers/pricing";
import { PriceCalcPage } from "@/routes/price-calc";

// Includes Persian RTL formatting and the real Money component (no pricing mocks).
afterEach(cleanup);

describe("pricing page — literal Excel model", () => {
  it("renders the actual cached workbook amounts without cell addresses", () => {
    renderWithPricing(<PriceCalcPage />);
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
    const row = screen.getByTestId(`row-${key}`);
    expect(within(row).getAllByRole("cell")).toHaveLength(3);
    expect(row).toHaveClass(`bg-${color}-100`, `dark:bg-${color}-900/40`, "font-semibold");
    fireEvent.change(screen.getByTestId("input-qty"), { target: { value: "10" } });
    expect(row).toHaveClass(`bg-${color}-100`, `dark:bg-${color}-900/40`);
  });

  it("does not color unrelated rows or the derived batch final price", () => {
    renderWithPricing(<PriceCalcPage />);
    const batchFinal = screen.getByTestId("row-batchFinalPrice");
    expect(batchFinal).toHaveClass("bg-muted/40");
    expect(batchFinal).not.toHaveClass("bg-red-100");
    expect(screen.getByTestId("row-filamentCost")).toHaveAttribute("class", "border-t");
  });

  it("recalculates quantity > 1 and Persian input using authored formulas", () => {
    renderWithPricing(<PriceCalcPage />);
    fireEvent.change(screen.getByLabelText(/تیراژ/), { target: { value: "۱۰" } });
    const row = within(screen.getByTestId("row-unitFinalPrice"));
    expect(row.getByText("۲۹۱٬۱۹۴.۸۵")).toBeInTheDocument();
    expect(row.getByText("۳۱۱٬۱۹۴.۸۵")).toBeInTheDocument();
    expect(
      within(screen.getByTestId("row-productionTotal")).getByText("۹۱۴٬۰۰۰"),
    ).toBeInTheDocument();
  });

  it("resets only product inputs, keeping the saved pricing constants", () => {
    const { client } = renderWithPricing(<PriceCalcPage />, { filamentPerGram: "4000.0000" });
    fireEvent.change(screen.getByTestId("input-qty"), { target: { value: "10" } });
    fireEvent.change(screen.getByTestId("select-channel"), { target: { value: "direct" } });
    fireEvent.click(screen.getByRole("button", { name: "بازنشانی ورودی‌ها" }));
    expect(screen.getByTestId("input-qty")).toHaveValue("1");
    expect(screen.getByTestId("select-channel")).toHaveValue("marketplace");
    expect(
      within(screen.getByTestId("row-productionTotal")).getByText("۱٬۰۷۴٬۰۰۰"),
    ).toBeInTheDocument();
    expect(client.getQueryData(["pricing-settings"])).toMatchObject({
      filamentPerGram: "4000.0000",
    });
    expect(screen.queryByTestId("const-filamentPerGram")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "تغییر ثابت‌ها در تنظیمات" })).toHaveAttribute(
      "href",
      "/settings",
    );
  });

  it("keeps shared commission, unavailable chain amount and moved constant editors", () => {
    renderWithPricing(<PriceCalcPage />);
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
    fireEvent.change(screen.getByTestId("input-qty"), { target: { value: "0" } });
    expect(screen.getByText(/ورودی نامعتبر است/)).toBeInTheDocument();
    expect(screen.queryByTestId("row-unitFinalPrice")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "بازنشانی ورودی‌ها" }));
    expect(screen.getByTestId("row-unitFinalPrice")).toBeInTheDocument();
  });
});
