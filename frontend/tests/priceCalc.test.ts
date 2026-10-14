/** Sales price calculator — normalized model of قیمت نهایی.xlsx (spec §4.3). */
import { describe, expect, it } from "vitest";
import { computePrice, DEFAULT_CONSTANTS } from "@/lib/priceCalc";

describe("price calculator", () => {
  it("computes chain variant, marketplace channel per the spec example shape", () => {
    const r = computePrice({
      weightG: "30",
      printHours: "2.5",
      quantity: "10",
      variant: "chain",
      channel: "marketplace",
    });
    // unit filament = 30 × 3000 = 90 000
    expect(r.unitFilamentCost.toFixed()).toBe("90000");
    // unit energy = 1.3 × 2.5 × 1400 = 4 550
    expect(r.unitEnergyCost.toFixed()).toBe("4550");
    // unit depreciation = 2.5 × 10 000 = 25 000
    expect(r.unitDepreciationCost.toFixed()).toBe("25000");
    // chain variant adds 8 000
    expect(r.unitChainCost.toFixed()).toBe("8000");
    // production = 90 000 + 4 550 + 25 000 + 8 000 = 127 550
    expect(r.unitProductionCost.toFixed()).toBe("127550");
    expect(r.batchProductionCost.toFixed()).toBe("1275500");
    // shipping share = 150 000 / 10 = 15 000
    expect(r.unitShippingShare.toFixed()).toBe("15000");
    // delivery = 2 000 + 8 000 + 15 000 = 25 000
    expect(r.unitDeliveryCost.toFixed()).toBe("25000");
    // sale price = 127 550 × 2.5 = 318 875
    expect(r.unitSalePrice.toFixed()).toBe("318875");
    // commission = 318 875 × 13.1% = 41 772.625
    expect(r.unitCommission.toFixed()).toBe("41772.625");
    // merchandise = 360 647.625
    expect(r.merchandise.toFixed()).toBe("360647.625");
    // buffer = 36 064.7625
    expect(r.buffer.toFixed()).toBe("36064.7625");
    // final = merchandise + delivery + buffer
    expect(r.unitFinalPrice.toFixed()).toBe("421712.3875");
    expect(r.batchTotal.toFixed()).toBe("4217123.875");
  });

  it("plain/direct channel: no chain cost, no commission, no delivery line", () => {
    const r = computePrice({
      weightG: "10",
      printHours: "1",
      quantity: "5",
      variant: "plain",
      channel: "direct",
    });
    expect(r.unitChainCost.isZero()).toBe(true);
    expect(r.unitCommission.isZero()).toBe(true);
    // final = merchandise + buffer (no delivery)
    expect(r.unitFinalPrice.toFixed()).toBe(r.merchandise.plus(r.buffer).toFixed());
    // sale = (30 000 + 1 820 + 10 000) × 2.5 = 104 550
    expect(r.unitSalePrice.toFixed()).toBe("104550");
  });

  it("is exact for values that break binary floats", () => {
    const r = computePrice({
      weightG: "0.1",
      printHours: "0.1",
      quantity: "3",
      variant: "plain",
      channel: "direct",
    });
    // filament 300 + energy 1.3×0.1×1400=182 + depreciation 1000 = 1482
    expect(r.unitProductionCost.toFixed()).toBe("1482");
  });

  it("rejects invalid inputs", () => {
    expect(() =>
      computePrice({ weightG: "-1", printHours: "1", quantity: "1", variant: "plain", channel: "direct" }),
    ).toThrow();
    expect(() =>
      computePrice({ weightG: "1", printHours: "1", quantity: "0", variant: "plain", channel: "direct" }),
    ).toThrow();
  });

  it("exposes sane default constants", () => {
    expect(DEFAULT_CONSTANTS.profitFactor.toFixed()).toBe("2.5");
    expect(DEFAULT_CONSTANTS.commissionPercent.toFixed()).toBe("13.1");
    expect(DEFAULT_CONSTANTS.bufferPercent.toFixed()).toBe("10");
    expect(DEFAULT_CONSTANTS.filamentPerGram.toFixed()).toBe("3000");
  });
});
