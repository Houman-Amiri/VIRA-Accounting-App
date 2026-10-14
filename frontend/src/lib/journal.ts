/**
 * Journal entry form validation — mirrors backend invariants client-side
 * (zero-balance Σdebit=Σcredit, ≥2 splits) so the form never submits an
 * unbalanced entry. All amounts are decimal.js; the form keeps raw strings.
 */
import { z } from "zod";
import { Decimal, toDecimal } from "./money";

export const splitSchema = z.object({
  account_id: z.string().min(1, "حساب را انتخاب کنید"),
  debit: z.string().default("0"),
  credit: z.string().default("0"),
  description: z.string().optional().default(""),
  cost_center_id: z.string().optional().default(""),
});

export type SplitForm = z.infer<typeof splitSchema>;

export const journalEntrySchema = z
  .object({
    date: z.string().min(1, "تاریخ را وارد کنید"),
    description: z.string().min(1, "شرح سند را وارد کنید"),
    reference: z.string().optional().default(""),
    currency_code: z.string().default("IRR"),
    splits: z.array(splitSchema).min(2, "سند باید حداقل دو ردیف داشته باشد"),
  })
  .superRefine((entry, ctx) => {
    let totalDebit = new Decimal(0);
    let totalCredit = new Decimal(0);
    entry.splits.forEach((split, i) => {
      const d = safeDecimal(split.debit);
      const c = safeDecimal(split.credit);
      if (d === null || c === null) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["splits", i, d === null ? "debit" : "credit"],
          message: "مبلغ نامعتبر است",
        });
        return;
      }
      if (d.lt(0) || c.lt(0)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["splits", i],
          message: "مبلغ منفی مجاز نیست",
        });
      }
      if (d.gt(0) && c.gt(0)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["splits", i],
          message: "هر ردیف فقط بدهکار یا بستانکار است",
        });
      }
      if (d.isZero() && c.isZero()) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["splits", i],
          message: "مبلغ ردیف نمی‌تواند صفر باشد",
        });
      }
      totalDebit = totalDebit.plus(d);
      totalCredit = totalCredit.plus(c);
    });
    if (!totalDebit.equals(totalCredit)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["splits"],
        message: `سند نامتوازن است (بدهکار ${totalDebit.toFixed()} − بستانکار ${totalCredit.toFixed()} = ${totalDebit.minus(totalCredit).toFixed()})`,
      });
    }
  });

export type JournalEntryForm = z.infer<typeof journalEntrySchema>;

function safeDecimal(raw: string): Decimal | null {
  try {
    const d = toDecimal(raw.trim() || "0");
    return d.isFinite() ? d : null;
  } catch {
    return null;
  }
}

/** Running totals for the live form footer. */
export function splitTotals(splits: Array<Pick<SplitForm, "debit" | "credit">>): {
  totalDebit: Decimal;
  totalCredit: Decimal;
  difference: Decimal;
  balanced: boolean;
} {
  let totalDebit = new Decimal(0);
  let totalCredit = new Decimal(0);
  for (const s of splits) {
    const d = safeDecimal(s.debit ?? "0");
    const c = safeDecimal(s.credit ?? "0");
    if (d) totalDebit = totalDebit.plus(d);
    if (c) totalCredit = totalCredit.plus(c);
  }
  const difference = totalDebit.minus(totalCredit);
  return { totalDebit, totalCredit, difference, balanced: difference.isZero() };
}

/**
 * Auto-balance: put the residual onto the `targetIndex` split's side
 * (the side that is currently non-zero, defaulting to credit).
 */
export function autoBalance(
  splits: Array<Pick<SplitForm, "debit" | "credit">>,
  targetIndex: number,
): Array<Pick<SplitForm, "debit" | "credit">> {
  const { difference } = splitTotals(splits);
  if (difference.isZero() || targetIndex < 0 || targetIndex >= splits.length) return splits;
  return splits.map((s, i) => {
    if (i !== targetIndex) return s;
    const d = safeDecimal(s.debit ?? "0") ?? new Decimal(0);
    const c = safeDecimal(s.credit ?? "0") ?? new Decimal(0);
    if (!d.isZero() || c.isZero()) {
      // residual on debit side
      return { debit: d.minus(difference).toFixed(4), credit: s.credit };
    }
    return { debit: s.debit, credit: c.plus(difference).toFixed(4) };
  });
}
