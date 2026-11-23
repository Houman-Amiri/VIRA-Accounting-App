import { describe, expect, it } from "vitest";
import {
  DEFAULT_CONSTANTS,
  applyVariables,
  computePrice,
  variableEffect,
  type PriceBreakdown,
  type PriceConstants,
  type VariableInput,
} from "@/lib/priceCalc";

/**
 * A variable is a number the owner re-enters per job. What matters here is
 * *where* it lands: on every piece (جزیی) or on the whole order (کلی) — and, for
 * the latter, whether it is added once to the total or spread over the quantity.
 */
const CONSTANTS: PriceConstants = { ...DEFAULT_CONSTANTS };
const INPUTS = {
  weightG: "250",
  printHours: "4",
  quantity: "10",
  variant: "plain" as const,
  channel: "marketplace" as const,
};

function base(): PriceBreakdown {
  return computePrice(INPUTS, CONSTANTS);
}

const variable = (patch: Partial<VariableInput>): VariableInput => ({
  name: "متغیر",
  scope: "PER_UNIT",
  basis: "AMOUNT",
  allocation: "SPLIT",
  value: "1000",
  is_active: true,
  ...patch,
});

describe("pricing variables", () => {
  it("does nothing at all when the owner has no variables", () => {
    const result = applyVariables(base(), [], "10");
    expect(result.lines).toEqual([]);
    expect(result.perUnit.toFixed(4)).toBe("0.0000");
    expect(result.oneTime.toFixed(4)).toBe("0.0000");
    expect(result.perUnit.plus(base().unitFinalPrice).toFixed(4)).toBe(
      base().unitFinalPrice.toFixed(4),
    );
  });

  it("adds a per-piece amount to the unit price and to the total", () => {
    const line = variableEffect(variable({ value: "1500" }), base(), "10");
    expect(line.perUnit.toFixed(4)).toBe("1500.0000");
    expect(line.orderTotal.toFixed(4)).toBe("15000.0000");
    expect(line.oneTime).toBe(false);
  });

  it("adds a whole-order amount once, without touching the unit price", () => {
    const line = variableEffect(
      variable({ scope: "PER_ORDER", allocation: "ONE_TIME", value: "200000" }),
      base(),
      "10",
    );
    expect(line.perUnit.toFixed(4)).toBe("0.0000");
    expect(line.orderTotal.toFixed(4)).toBe("200000.0000");
    expect(line.oneTime).toBe(true);
  });

  it("spreads a whole-order amount over the quantity", () => {
    const line = variableEffect(
      variable({ scope: "PER_ORDER", allocation: "SPLIT", value: "200000" }),
      base(),
      "10",
    );
    expect(line.perUnit.toFixed(4)).toBe("20000.0000");
    expect(line.orderTotal.toFixed(4)).toBe("200000.0000");
    expect(line.oneTime).toBe(false);
  });

  it("applies the amount once per count («۲ محموله × ۱۵۰٬۰۰۰»)", () => {
    const line = variableEffect(
      variable({ scope: "PER_ORDER", allocation: "ONE_TIME", value: "150000", count: "2" }),
      base(),
      "10",
    );
    expect(line.count.toFixed(0)).toBe("2");
    expect(line.amount.toFixed(4)).toBe("300000.0000");
    expect(line.perUnit.toFixed(4)).toBe("0.0000");
    expect(line.orderTotal.toFixed(4)).toBe("300000.0000");
    expect(line.oneTime).toBe(true);
  });

  it("multiplies the count on a per-piece variable too", () => {
    const line = variableEffect(variable({ value: "1200", count: "3" }), base(), "10");
    expect(line.amount.toFixed(4)).toBe("3600.0000");
    expect(line.perUnit.toFixed(4)).toBe("3600.0000");
    expect(line.orderTotal.toFixed(4)).toBe("36000.0000");
  });

  it("multiplies the count on percentage variables", () => {
    const line = variableEffect(
      variable({
        scope: "PER_ORDER",
        basis: "PERCENT_OF_COST",
        allocation: "SPLIT",
        value: "5",
        count: "2",
      }),
      base(),
      "10",
    );
    // ۵٪ × ۲ = ۱۰٪ از بهای تمام‌شدهٔ هر عدد
    expect(line.amount.toFixed(4)).toBe("10.0000");
    expect(line.perUnit.toFixed(4)).toBe(base().unitProductionCost.times("0.1").toFixed(4));
  });

  it("treats a missing count as one, permits zero and rejects negative counts", () => {
    expect(variableEffect(variable({ value: "1500" }), base(), "10").count.toFixed(0)).toBe("1");
    expect(
      variableEffect(variable({ value: "1500", count: "0" }), base(), "10").perUnit.isZero(),
    ).toBe(true);
    expect(() => variableEffect(variable({ value: "1500", count: "-2" }), base(), "10")).toThrow(
      "تعداد متغیر نمی‌تواند منفی باشد",
    );
  });

  it("takes a percentage of the production cost per piece", () => {
    const sheet = base();
    const line = variableEffect(variable({ basis: "PERCENT_OF_COST", value: "7.5" }), base(), "10");
    expect(line.perUnit.toFixed(4)).toBe(sheet.unitProductionCost.times(7.5).div(100).toFixed(4));
  });

  it("takes a whole-order percentage of «قیمت فروش هر عدد محصول»", () => {
    const sheet = base();
    const line = variableEffect(
      variable({
        scope: "PER_ORDER",
        allocation: "ONE_TIME",
        basis: "PERCENT_OF_PRICE",
        value: "9",
      }),
      base(),
      "10",
    );
    const expectedTotal = sheet.unitSalePrice.times(9).div(100).times(10);
    expect(line.orderTotal.toFixed(4)).toBe(expectedTotal.toFixed(4));
    expect(line.perUnit.isZero()).toBe(true);
  });

  it("keeps the total honest when one-time and per-piece variables meet", () => {
    const result = applyVariables(
      base(),
      [
        variable({ name: "بسته‌بندی", value: "1000" }),
        variable({ name: "مالیات", scope: "PER_ORDER", allocation: "ONE_TIME", value: "50000" }),
      ],
      "10",
    );
    expect(result.perUnit.toFixed(4)).toBe("1000.0000");
    expect(result.oneTime.toFixed(4)).toBe("50000.0000");
    const unitFinal = base().unitFinalPrice.plus(result.perUnit);
    expect(unitFinal.times(10).plus(result.oneTime).toFixed(4)).toBe(
      base().unitFinalPrice.times(10).plus(10000).plus(50000).toFixed(4),
    );
  });

  it("does not depend on the order of the rows", () => {
    const a = variable({ name: "الف", scope: "PER_ORDER", allocation: "SPLIT", value: "30000" });
    const b = variable({ name: "ب", basis: "PERCENT_OF_COST", value: "5" });
    const forward = applyVariables(base(), [a, b], "7");
    const backward = applyVariables(base(), [b, a], "7");
    expect(forward.perUnit.toFixed(6)).toBe(backward.perUnit.toFixed(6));
    expect(forward.oneTime.toFixed(6)).toBe(backward.oneTime.toFixed(6));
  });

  it("ignores a switched-off variable", () => {
    const result = applyVariables(base(), [variable({ is_active: false })], "10");
    expect(result.lines).toEqual([]);
    expect(result.perUnit.isZero()).toBe(true);
  });

  it("refuses a negative value or a quantity of zero", () => {
    expect(() => variableEffect(variable({ value: "-1" }), base(), "10")).toThrow();
    expect(() => variableEffect(variable({ value: "10" }), base(), "0")).toThrow();
  });
});
