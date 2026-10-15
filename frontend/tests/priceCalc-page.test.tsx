import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { PriceCalcPage } from "@/routes/price-calc";

// Includes Persian RTL formatting and the real Money component (no pricing mocks).
afterEach(cleanup);

describe("pricing page — literal Excel model", () => {
  it("renders the actual cached B35/E35 with distinct cell addresses", () => {
    render(<PriceCalcPage />);
    const row = within(screen.getByTestId("row-unitFinalPrice"));
    expect(row.getByText("B35")).toBeInTheDocument();
    expect(row.getByText("E35")).toBeInTheDocument();
    expect(row.getByText("۲٬۷۶۰٬۷۴۸.۵")).toBeInTheDocument();
    expect(row.getByText("۲٬۷۸۰٬۷۴۸.۵")).toBeInTheDocument();
    expect(screen.getByTestId("sheet-policy")).toHaveTextContent("بدون ضرب خودکار");
  });

  it("recalculates quantity > 1 and Persian input using authored formulas", () => {
    render(<PriceCalcPage />);
    fireEvent.change(screen.getByLabelText(/تیراژ/), { target: { value: "۱۰" } });
    const row = within(screen.getByTestId("row-unitFinalPrice"));
    expect(row.getByText("۲۹۱٬۱۹۴.۸۵")).toBeInTheDocument();
    expect(row.getByText("۳۱۱٬۱۹۴.۸۵")).toBeInTheDocument();
    expect(
      within(screen.getByTestId("row-productionTotal")).getByText("۹۱۴٬۰۰۰"),
    ).toBeInTheDocument();
  });

  it("resets constants AND product inputs when restoring the workbook example", () => {
    render(<PriceCalcPage />);
    fireEvent.change(screen.getByTestId("const-filamentPerGram"), { target: { value: "9999" } });
    fireEvent.change(screen.getByTestId("input-qty"), { target: { value: "10" } });
    fireEvent.change(screen.getByTestId("select-channel"), { target: { value: "direct" } });
    fireEvent.click(screen.getByRole("button", { name: "مقادیر نمونهٔ اکسل" }));
    expect(screen.getByTestId("const-filamentPerGram")).toHaveValue("3000");
    expect(screen.getByTestId("input-qty")).toHaveValue("1");
    expect(screen.getByTestId("select-channel")).toHaveValue("marketplace");
    expect(
      within(screen.getByTestId("row-unitFinalPrice")).getByText("۲٬۷۸۰٬۷۴۸.۵"),
    ).toBeInTheDocument();
  });

  it("does not invent E31 or E32 and keeps unused workbook constants read-only", () => {
    render(<PriceCalcPage />);
    const commission = within(screen.getByTestId("row-unitCommission"));
    expect(commission.getAllByText("B31")).toHaveLength(2);
    const delivery = within(screen.getByTestId("row-saleWithDelivery"));
    expect(delivery.getAllByText("—")).toHaveLength(2);
    for (const key of ["printerPowerKw", "commissionPercent", "nylonPerUnit"]) {
      expect(screen.getByTestId(`const-${key}`)).toHaveAttribute("readonly");
    }
  });

  it("shows invalid input rather than an obsolete price, and can recover", () => {
    render(<PriceCalcPage />);
    fireEvent.change(screen.getByTestId("input-qty"), { target: { value: "0" } });
    expect(screen.getByText(/ورودی نامعتبر است/)).toBeInTheDocument();
    expect(screen.queryByTestId("row-unitFinalPrice")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "مقادیر نمونهٔ اکسل" }));
    expect(screen.getByTestId("row-unitFinalPrice")).toBeInTheDocument();
  });
});
