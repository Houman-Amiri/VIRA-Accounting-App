/** Client money math — decimal.js exactness, API string round-trip. */
import { describe, expect, it } from "vitest";
import { Decimal, balance, isZero, sumMoney, toDecimal, toMoneyString } from "@/lib/money";

describe("money math (decimal.js, never float)", () => {
  it("parses API 4-decimal strings exactly", () => {
    expect(toDecimal("1250.5000").toFixed(4)).toBe("1250.5000");
    expect(toDecimal("0.0001").toFixed(4)).toBe("0.0001");
  });

  it("serializes to fixed 4-decimal API representation", () => {
    expect(toMoneyString("12.5")).toBe("12.5000");
    expect(toMoneyString("0")).toBe("0.0000");
    expect(toMoneyString("-3.1")).toBe("-3.1000");
  });

  it("sums exactly where binary floats fail (0.1+0.2)", () => {
    const total = sumMoney(["0.1000", "0.2000"]);
    expect(total.toFixed(4)).toBe("0.3000");
    expect(total.equals(0.3)).toBe(true);
  });

  it("aggregates large volumes without precision loss", () => {
    const many = Array.from({ length: 10_000 }, () => "0.0001");
    expect(sumMoney(many).toFixed(4)).toBe("1.0000");
  });

  it("computes signed balances", () => {
    expect(balance("10.0000", "4.0000").toFixed(4)).toBe("6.0000");
    expect(isZero(balance("4.0000", "4.0000"))).toBe(true);
  });

  it("rejects non-finite values", () => {
    expect(() => toDecimal("abc")).toThrow();
  });

  it("uses banker's rounding at the 4th decimal (parity with backend)", () => {
    // ROUND_HALF_EVEN: 0.00005 → 0.0000; 0.00015 → 0.0002
    expect(new Decimal("0.00005").toDecimalPlaces(4).toFixed(4)).toBe("0.0000");
    expect(new Decimal("0.00015").toDecimalPlaces(4).toFixed(4)).toBe("0.0002");
    expect(new Decimal("0.00025").toDecimalPlaces(4).toFixed(4)).toBe("0.0002");
  });
});
