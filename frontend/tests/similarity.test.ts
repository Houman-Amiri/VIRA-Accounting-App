/** Bank reconciliation matching heuristics + confidence tiers. */
import { describe, expect, it } from "vitest";
import {
  AUTO_MATCH_THRESHOLD,
  bestMatch,
  confidenceOf,
  lcsRatio,
  scoreMatch,
  type MatchCandidate,
} from "@/lib/similarity";

describe("lcsRatio", () => {
  it("scores identical strings 1", () => {
    expect(lcsRatio("خرید فیلامنت", "خرید فیلامنت")).toBe(1);
  });
  it("scores disjoint strings 0", () => {
    expect(lcsRatio("abc", "xyz")).toBe(0);
  });
  it("is case-insensitive and partial", () => {
    expect(lcsRatio("Payment INV-1024 Acme", "payment inv-1024 acme")).toBe(1);
    const partial = lcsRatio("خرید فیلامنت PLA سفید", "فیلامنت PLA سفید — فروشنده پارس");
    expect(partial).toBeGreaterThan(0.3);
    expect(partial).toBeLessThan(1);
  });
});

describe("scoreMatch + confidence", () => {
  const line: MatchCandidate = {
    amount: "1250000.0000",
    dateIso: "2026-10-01",
    description: "واریز به ازای فاکتور ۱۰۲۴ شرکت آریا",
    refNo: "1024",
  };

  it("auto-matches amount+date+ref with close description", () => {
    const tx: MatchCandidate = {
      amount: "1250000.0000",
      dateIso: "2026-10-01",
      description: "دریافت از آریا — فاکتور ۱۰۲۴",
      refNo: "1024",
    };
    const m = scoreMatch(line, tx);
    expect(m.amountMatch).toBe(true);
    expect(m.refMatch).toBe(true);
    expect(m.score).toBeGreaterThanOrEqual(AUTO_MATCH_THRESHOLD);
    expect(confidenceOf(m)).toBe("auto");
  });

  it("flags amount mismatch below auto threshold", () => {
    const tx: MatchCandidate = {
      amount: "999999.0000",
      dateIso: "2026-10-01",
      description: "واریز به ازای فاکتور ۱۰۲۴ شرکت آریا",
      refNo: "1024",
    };
    const m = scoreMatch(line, tx);
    expect(m.amountMatch).toBe(false);
    expect(confidenceOf(m)).not.toBe("auto");
  });

  it("decays confidence with date distance", () => {
    const near = scoreMatch(line, { ...line, dateIso: "2026-10-02" });
    const far = scoreMatch(line, { ...line, dateIso: "2026-11-20" });
    expect(near.score).toBeGreaterThan(far.score);
    expect(far.dateDeltaDays).toBe(50);
  });

  it("suggests best candidate and refuses weak ones", () => {
    const txs: MatchCandidate[] = [
      { amount: "5.0000", dateIso: "2026-01-01", description: "بی‌ربط", refNo: "9" },
      {
        amount: "1250000.0000",
        dateIso: "2026-10-02",
        description: "فاکتور ۱۰۲۴ آریا",
        refNo: "1024",
      },
    ];
    const best = bestMatch(line, txs);
    expect(best).not.toBeNull();
    expect(best!.tx.refNo).toBe("1024");
    expect(best!.match.score).toBeGreaterThanOrEqual(60);

    const weak = bestMatch({ ...line, description: "؟", refNo: null }, [
      { amount: "1.0000", dateIso: "2020-01-01", description: "x" },
    ]);
    expect(weak).toBeNull();
  });
});
