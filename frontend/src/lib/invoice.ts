/**
 * Invoice-shaped «سند» — the only entry form the user sees (item 11).
 *
 * The owner asked for a real invoice: date, seller, buyer, items, line amount
 * and grand total. Debit/credit are no longer part of the user's path; the
 * server derives the two balanced splits from the chart of accounts, so the
 * ledger invariants still hold. This module owns the client-side validation and
 * the exact (decimal.js) totals; the form keeps raw strings.
 */
import { z } from "zod";
import { validIso } from "./calendar";
import { Decimal, toDecimal } from "./money";
import { parseNum } from "./priceCalc";

export type InvoiceKind = "sale" | "purchase";

export const INVOICE_KINDS: Record<InvoiceKind, string> = {
  sale: "فاکتور فروش",
  purchase: "فاکتور خرید",
};

/** Parse a user-typed amount, tolerating Persian digits and separators. */
export function parseAmount(raw: string | null | undefined): Decimal {
  return parseNum(raw ?? "").abs();
}

export const invoiceLineSchema = z.object({
  title: z.string().trim().min(1, "نام کالا یا خدمت را وارد کنید."),
  quantity: z.string().default("1"),
  unit_price: z.string().default(""),
});

export const invoiceFormSchema = z
  .object({
    kind: z.enum(["sale", "purchase"]),
    date: z.string().refine(validIso, "تاریخ معتبر را وارد کنید."),
    seller: z.string().optional().default(""),
    buyer: z.string().optional().default(""),
    note: z.string().optional().default(""),
    lines: z.array(invoiceLineSchema).min(1, "حداقل یک ردیف کالا لازم است."),
  })
  .superRefine((invoice, ctx) => {
    if (invoice.kind === "sale" && !invoice.buyer?.trim()) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["buyer"],
        message: "نام خریدار را وارد کنید.",
      });
    }
    if (invoice.kind === "purchase" && !invoice.seller?.trim()) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["seller"],
        message: "نام فروشنده را وارد کنید.",
      });
    }
    invoice.lines.forEach((line, index) => {
      const quantity = safeAmount(line.quantity);
      if (quantity === null || quantity.lte(0)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["lines", index, "quantity"],
          message: "تعداد باید عددی بزرگ‌تر از صفر باشد.",
        });
      }
      const price = safeAmount(line.unit_price);
      if (price === null) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["lines", index, "unit_price"],
          message: "مبلغ واحد را عدد وارد کنید.",
        });
      }
    });
    if (invoiceTotal(invoice.lines).lte(0)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["lines"],
        message: "مبلغ کل باید بزرگ‌تر از صفر باشد.",
      });
    }
  });

export type InvoiceLineForm = z.infer<typeof invoiceLineSchema>;
export type InvoiceForm = z.infer<typeof invoiceFormSchema>;

function safeAmount(raw: string | null | undefined): Decimal | null {
  try {
    const value = parseAmount(raw);
    return value.isFinite() ? value : null;
  } catch {
    return null;
  }
}

/** Line amount in the form's unit (Toman); 0 for a line that is still empty. */
export function lineAmount(line: Pick<InvoiceLineForm, "quantity" | "unit_price">): Decimal {
  const quantity = safeAmount(line.quantity);
  const price = safeAmount(line.unit_price);
  if (quantity === null || price === null) return new Decimal(0);
  return quantity.times(price);
}

/** Grand total in the form's unit (Toman) — never rounded until display. */
export function invoiceTotal(
  lines: Array<Pick<InvoiceLineForm, "quantity" | "unit_price">>,
): Decimal {
  return lines.reduce((sum, line) => sum.plus(lineAmount(line)), new Decimal(0));
}

/** Amount for display/transport: fixed 4 decimals, no thousands separators. */
export function moneyString(value: Decimal): string {
  return toDecimal(value).toFixed(4);
}
