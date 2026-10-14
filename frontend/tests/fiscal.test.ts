/** Phase 7 §3 — fiscal year = full Jalali year (1 Farvardin … Esfand 29/30). */
import { describe, expect, it } from "vitest";
import { currentFiscalYear, fiscalYearFor, jalaliYear } from "@/lib/fiscal";

describe("fiscal year (1 Farvardin start)", () => {
  it("1405 starts on 1 Farvardin 1405 = 2026-03-21", () => {
    const r = jalaliYear(1405);
    expect(r.startIso).toBe("2026-03-21");
    expect(r.endIso).toBe("2027-03-20");
    expect(r.label).toBe("۱۴۰۵");
  });

  it("maps an ISO date to its containing Jalali fiscal year", () => {
    // 2026-10-14 (today in session) is in 1405
    const r = fiscalYearFor("2026-10-14");
    expect(r.year).toBe(1405);
    expect(r.startIso <= "2026-10-14").toBe(true);
    expect(r.endIso >= "2026-10-14").toBe(true);
  });

  it("handles the year boundary (last Esfand day)", () => {
    // 1404 ends 2026-03-20; 2026-03-20 belongs to 1404
    const last = fiscalYearFor("2026-03-20");
    expect(last.year).toBe(1404);
    // next day is 1405
    const first = fiscalYearFor("2026-03-21");
    expect(first.year).toBe(1405);
  });

  it("currentFiscalYear delegates with today", () => {
    expect(currentFiscalYear("2026-10-14").year).toBe(1405);
  });
});
