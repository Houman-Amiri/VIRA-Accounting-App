/** Journal form validation — zero-balance superRefine + auto-balance. */
import { describe, expect, it } from "vitest";
import { autoBalance, journalEntrySchema, splitTotals } from "@/lib/journal";

const validEntry = {
  date: "2025-10-14",
  description: "خرید مواد اولیه",
  reference: "",
  currency_code: "TOMAN",
  splits: [
    { account_id: "a1", debit: "100.0000", credit: "0", description: "", cost_center_id: "" },
    { account_id: "a2", debit: "0", credit: "100.0000", description: "", cost_center_id: "" },
  ],
};

describe("journal entry schema (superRefine)", () => {
  it("accepts a balanced 2-split entry", () => {
    expect(journalEntrySchema.safeParse(validEntry).success).toBe(true);
  });

  it("rejects an unbalanced entry", () => {
    const unbalanced = structuredClone(validEntry);
    unbalanced.splits[1].credit = "80.0000";
    const result = journalEntrySchema.safeParse(unbalanced);
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues.some((i) => i.path.join(".").startsWith("splits"))).toBe(true);
    }
  });

  it("rejects fewer than 2 splits", () => {
    const one = { ...validEntry, splits: [validEntry.splits[0]] };
    expect(journalEntrySchema.safeParse(one).success).toBe(false);
  });

  it("rejects a split with both debit and credit", () => {
    const both = structuredClone(validEntry);
    both.splits[0].credit = "50.0000";
    expect(journalEntrySchema.safeParse(both).success).toBe(false);
  });

  it("rejects zero-amount splits", () => {
    const zeros = structuredClone(validEntry);
    zeros.splits[0].debit = "0";
    expect(journalEntrySchema.safeParse(zeros).success).toBe(false);
  });

  it("rejects negative amounts", () => {
    const neg = structuredClone(validEntry);
    neg.splits[0].debit = "-5.0000";
    expect(journalEntrySchema.safeParse(neg).success).toBe(false);
  });

  it("accepts multi-split entries when totals match", () => {
    const multi = {
      ...validEntry,
      splits: [
        { account_id: "a1", debit: "150.0000", credit: "0", description: "", cost_center_id: "" },
        { account_id: "a2", debit: "0", credit: "100.0000", description: "", cost_center_id: "" },
        { account_id: "a3", debit: "0", credit: "50.0000", description: "", cost_center_id: "" },
      ],
    };
    expect(journalEntrySchema.safeParse(multi).success).toBe(true);
  });
});

describe("splitTotals + autoBalance", () => {
  it("computes live totals and difference", () => {
    const t = splitTotals([
      { debit: "12.3456", credit: "0" },
      { debit: "0", credit: "12.3400" },
    ]);
    expect(t.totalDebit.toFixed(4)).toBe("12.3456");
    expect(t.totalCredit.toFixed(4)).toBe("12.3400");
    expect(t.difference.toFixed(4)).toBe("0.0056");
    expect(t.balanced).toBe(false);
  });

  it("auto-balances by adjusting the target split", () => {
    const splits = [
      { debit: "100.0000", credit: "0" },
      { debit: "0", credit: "75.0000" },
    ];
    const balanced = autoBalance(splits, 1);
    expect(splitTotals(balanced).balanced).toBe(true);
    expect(balanced[1].credit).toBe("100.0000");
  });

  it("leaves balanced entries untouched", () => {
    const splits = [
      { debit: "10", credit: "0" },
      { debit: "0", credit: "10" },
    ];
    expect(autoBalance(splits, 0)).toBe(splits);
  });
});
