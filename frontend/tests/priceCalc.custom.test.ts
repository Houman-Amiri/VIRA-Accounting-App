import { describe, expect, it } from "vitest";
import {
  DEFAULT_CONSTANTS,
  applyCustomConstants,
  computePrice,
  customConstantAmount,
  type CustomConstantInput,
  type PriceBreakdown,
  type PriceConstants,
} from "@/lib/priceCalc";

/**
 * The owner can now add his own constants on the «قیمت‌گذاری» page. These tests
 * pin two promises:
 *
 *   1. with no custom constants the calculator is *exactly* the workbook model
 *      (nothing about `computePrice` may drift), and
 *   2. each of the four calculation methods does what its Persian hint says.
 */
const CONSTANTS: PriceConstants = {
  ...DEFAULT_CONSTANTS,
  filamentPerGram: "3000",
  electricityPerKwh: "1400",
  depreciationPerHour: "10000",
  profitFactor: "2.5",
  chainPerUnit: "8000",
  shipmentPerBatch: "150000",
  labelPerUnit: "8000",
};

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

const custom = (patch: Partial<CustomConstantInput>): CustomConstantInput => ({
  name: "ثابت",
  method: "PER_UNIT",
  value: "0",
  is_active: true,
  ...patch,
});

describe("custom pricing constants", () => {
  it("leaves the workbook price untouched when the owner has no constants", () => {
    const result = applyCustomConstants(base(), [], "10");
    expect(result.lines).toEqual([]);
    expect(result.perUnit.toFixed(4)).toBe("0.0000");
    expect(result.unitFinalPrice.toFixed(4)).toBe(base().unitFinalPrice.toFixed(4));
    expect(result.batchFinalPrice.toFixed(4)).toBe(base().batchFinalPrice.toFixed(4));
  });

  it("adds a fixed amount per piece", () => {
    const result = applyCustomConstants(base(), [custom({ value: "12000" })], "10");
    expect(result.lines[0].amount.toFixed(4)).toBe("12000.0000");
    expect(result.unitFinalPrice.toFixed(4)).toBe(base().unitFinalPrice.plus(12000).toFixed(4));
    expect(result.batchFinalPrice.toFixed(4)).toBe(result.unitFinalPrice.times(10).toFixed(4));
  });

  it("splits a per-shipment amount over the run size", () => {
    const result = applyCustomConstants(
      base(),
      [custom({ method: "PER_BATCH", value: "50000" })],
      "10",
    );
    expect(result.lines[0].amount.toFixed(4)).toBe("5000.0000");
  });

  it("takes a percentage of the unit production cost", () => {
    const sheet = base();
    const result = applyCustomConstants(
      base(),
      [custom({ method: "PERCENT_OF_COST", value: "10" })],
      "10",
    );
    expect(result.lines[0].amount.toFixed(4)).toBe(
      sheet.unitProductionCost.times(10).div(100).toFixed(4),
    );
  });

  it("takes a percentage of the sheet's unit price, not of the running total", () => {
    const sheet = base();
    const result = applyCustomConstants(
      base(),
      [
        custom({ method: "PERCENT_OF_PRICE", value: "10" }),
        custom({ name: "دومی", method: "PERCENT_OF_PRICE", value: "10" }),
      ],
      "10",
    );
    const each = sheet.unitFinalPrice.times(10).div(100);
    expect(result.lines[0].amount.toFixed(4)).toBe(each.toFixed(4));
    expect(result.lines[1].amount.toFixed(4)).toBe(each.toFixed(4));
    expect(result.perUnit.toFixed(4)).toBe(each.times(2).toFixed(4));
  });

  it("does not depend on the order of the rows", () => {
    const a = custom({ name: "الف", method: "PER_BATCH", value: "50000" });
    const b = custom({ name: "ب", method: "PERCENT_OF_COST", value: "7.5" });
    const forward = applyCustomConstants(base(), [a, b], "10");
    const backward = applyCustomConstants(base(), [b, a], "10");
    expect(forward.unitFinalPrice.toFixed(6)).toBe(backward.unitFinalPrice.toFixed(6));
    expect(forward.perUnit.toFixed(6)).toBe(backward.perUnit.toFixed(6));
  });

  it("ignores switched-off constants entirely", () => {
    base();
    const result = applyCustomConstants(
      base(),
      [custom({ value: "9999", is_active: false })],
      "10",
    );
    expect(result.lines).toEqual([]);
    expect(result.unitFinalPrice.toFixed(4)).toBe(base().unitFinalPrice.toFixed(4));
  });

  it("refuses a negative value or a run size of zero", () => {
    expect(() => applyCustomConstants(base(), [custom({ value: "-1" })], "10")).toThrow();
    expect(() =>
      customConstantAmount(custom({ method: "PER_BATCH", value: "1000" }), base(), "0"),
    ).toThrow();
  });

  it("keeps four decimal places of a fractional share", () => {
    const result = applyCustomConstants(
      base(),
      [custom({ method: "PER_BATCH", value: "10000" })],
      "3",
    );
    expect(result.lines[0].amount.toFixed(4)).toBe("3333.3333");
    // the stored 4-decimal value is not rounded a second time when totalling
    expect(result.perUnit.toFixed(4)).toBe("3333.3333");
  });
});
