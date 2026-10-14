/** Persian numerals + Jalali date formatting (presentation layer only). */
import { describe, expect, it } from "vitest";
import { faDate, faDigits, faNumber } from "@/lib/fa";

describe("Persian formatting", () => {
  it("converts digits to Persian numerals", () => {
    expect(faDigits("1250")).toBe("۱۲۵۰");
    expect(faDigits("2026/10/14")).toBe("۲۰۲۶/۱۰/۱۴");
    expect(faDigits(42)).toBe("۴۲");
  });

  it("groups thousands with Persian separators", () => {
    expect(faNumber("1250500")).toBe("۱٬۲۵۰٬۵۰۰");
    expect(faNumber("1234.56")).toBe("۱٬۲۳۴.۵۶");
    expect(faNumber("-1234567")).toBe("-۱٬۲۳۴٬۵۶۷");
  });

  it("formats Gregorian instants as Jalali dates", () => {
    // 2026-10-14 = 1405/07/22 (midday UTC keeps the civil date across zones)
    expect(faDate("2026-10-14T12:00:00Z")).toBe("۱۴۰۵/۰۷/۲۲");
    // Known conversion: 2025-03-21 = 1404/01/01 (Nowruz)
    expect(faDate("2025-03-21T12:00:00Z")).toBe("۱۴۰۴/۰۱/۰۱");
  });

  it("returns a dash for invalid dates", () => {
    expect(faDate("not-a-date")).toBe("—");
  });
});
