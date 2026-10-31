import { describe, expect, it } from "vitest";
import {
  invoiceFormSchema,
  invoiceTotal,
  lineAmount,
  moneyString,
  parseAmount,
} from "@/lib/invoice";

const base = {
  kind: "sale" as const,
  date: "2026-10-20",
  seller: "فروشگاه",
  buyer: "مشتری",
  note: "",
};

const line = (title: string, quantity: string, unit_price: string) => ({
  title,
  quantity,
  unit_price,
});

describe("invoice form model (item 11)", () => {
  it("multiplies exact decimals, including Persian digits and separators", () => {
    expect(moneyString(lineAmount(line("x", "3", "250000.5")))).toBe("750001.5000");
    expect(moneyString(lineAmount(line("x", "۲", "۱٬۲۵۰")))).toBe("2500.0000");
    expect(moneyString(lineAmount(line("x", "۱٫۵", "10")))).toBe("15.0000");
  });

  it("sums the lines into the grand total without rounding early", () => {
    const total = invoiceTotal([line("a", "3", "0.3333"), line("b", "3", "0.3333")]);
    expect(moneyString(total)).toBe("1.9998");
  });

  it("treats a half-filled line as zero instead of NaN", () => {
    expect(lineAmount(line("x", "2", "")).isZero()).toBe(true);
    expect(lineAmount(line("x", "", "100")).isZero()).toBe(true);
    expect(() => parseAmount("abc")).toThrow(/عدد نامعتبر/); // never silently NaN
    // the form turns that into a validation message rather than a crash
    const invalid = invoiceFormSchema.safeParse({
      ...base,
      lines: [line("کالا", "abc", "100")],
    });
    expect(invalid.success).toBe(false);
  });

  it("refuses a sale without a buyer and a purchase without a seller", () => {
    const sale = invoiceFormSchema.safeParse({
      ...base,
      buyer: "",
      lines: [line("کالا", "1", "100")],
    });
    expect(sale.success).toBe(false);
    const purchase = invoiceFormSchema.safeParse({
      ...base,
      kind: "purchase",
      seller: "  ",
      lines: [line("کالا", "1", "100")],
    });
    expect(purchase.success).toBe(false);
  });

  it("refuses an empty invoice and a non-positive line", () => {
    expect(invoiceFormSchema.safeParse({ ...base, lines: [] }).success).toBe(false);
    expect(
      invoiceFormSchema.safeParse({ ...base, lines: [line("کالا", "0", "100")] }).success,
    ).toBe(false);
    expect(invoiceFormSchema.safeParse({ ...base, lines: [line("کالا", "1", "0")] }).success).toBe(
      false,
    );
    expect(invoiceFormSchema.safeParse({ ...base, lines: [line("  ", "1", "100")] }).success).toBe(
      false,
    );
  });

  it("accepts a complete invoice of either kind", () => {
    expect(
      invoiceFormSchema.safeParse({ ...base, lines: [line("کالا", "2", "1500000")] }).success,
    ).toBe(true);
    expect(
      invoiceFormSchema.safeParse({
        ...base,
        kind: "purchase",
        seller: "تأمین‌کننده",
        lines: [line("فیلامنت", "1000", "1200")],
      }).success,
    ).toBe(true);
  });
});
