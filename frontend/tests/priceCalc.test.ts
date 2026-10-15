/**
 * The pricing engine must reproduce `قیمت نهایی.xlsx` exactly.
 *
 * Reference values come from the *sheet itself* (Annex A of MASTER_PROMPT.md):
 * with B3=3000, B4=1400, B5=10000, B6=2.5, B7=13.1, B9=8000, B10=150000,
 * B23=8000, buffer=10% and B13=240 g / B14=10 h / B15=1:
 *   B35 (ساده)      = 2,760,748.5
 *   E35 (زنجیردار)  = 2,785,630.5
 */
import { describe, expect, it } from "vitest";
import {
  BREAKDOWN_ROWS,
  computePrice,
  DEFAULT_CONSTANTS,
  parseNum,
  SALE_ROWS,
  SHEET_EXPECTED,
  SHEET_EXAMPLE_INPUTS,
  type PriceInputs,
} from "@/lib/priceCalc";

const SHEET: PriceInputs = SHEET_EXAMPLE_INPUTS;

describe("price calculator — exact Excel parity", () => {
  it("reproduces the sheet's B-column numbers line by line (ساده)", () => {
    const r = computePrice(SHEET);
    expect(r.unitFilamentCost.toFixed()).toBe("720000"); // B18 = 240×3000
    expect(r.unitEnergyCost.toFixed()).toBe("14000"); // B19 = 1400×10
    expect(r.unitDepreciationCost.toFixed()).toBe("100000"); // B20 = 10000×10
    expect(r.unitBaseProduction.toFixed()).toBe("834000"); // B25
    expect(r.unitChainCost.toFixed()).toBe("0");
    expect(r.batchShipment.toFixed()).toBe("150000"); // B21 = B10
    expect(r.unitShippingShare.toFixed()).toBe("150000"); // B22 = B21/1
    expect(r.unitLabelCost.toFixed()).toBe("8000"); // B23
    expect(r.unitDeliveryCost.toFixed()).toBe("158000"); // B24 = B23+B22
    expect(r.batchSalePrice.toFixed()).toBe("2085000"); // B28 = B25×B6
    expect(r.unitSalePrice.toFixed()).toBe("2085000"); // B29
    expect(r.unitCommission.toFixed()).toBe("273135"); // B31 = B29×13.1%
    expect(r.unitWithCommission.toFixed()).toBe("2358135"); // B33
    expect(r.unitWithLabel.toFixed()).toBe("2366135"); // B34
    expect(r.unitBuffer.toFixed()).toBe("236613.5"); // B34×10%
    expect(r.unitFinalPrice.toFixed()).toBe("2760748.5"); // B35 ← the number
    expect(r.unitFinalPrice.toFixed()).toBe(SHEET_EXPECTED.plain);
    expect(r.batchFinalPrice.toFixed()).toBe("2760748.5");
  });

  it("reproduces the sheet's E-column numbers (زنجیردار)", () => {
    const r = computePrice({ ...SHEET, variant: "chain" });
    expect(r.unitChainCost.toFixed()).toBe("8000"); // B9 × 1
    expect(r.batchProductionWithChain.toFixed()).toBe("842000"); // E25
    expect(r.unitProductionWithChain.toFixed()).toBe("842000");
    expect(r.batchSalePrice.toFixed()).toBe("2105000"); // E28 = E25×B6
    expect(r.unitSalePrice.toFixed()).toBe("2105000"); // E29
    expect(r.unitCommission.toFixed()).toBe("275755"); // E31 = E29×13.1%
    expect(r.unitWithLabel.toFixed()).toBe("2388755"); // E34
    expect(r.unitFinalPrice.toFixed()).toBe("2785630.5"); // E35 ← the number
    expect(r.unitFinalPrice.toFixed()).toBe(SHEET_EXPECTED.chain);
  });

  it("keeps B2/B8 out of the formula unless explicitly enabled (sheet parity)", () => {
    const off = computePrice(SHEET, DEFAULT_CONSTANTS);
    const power = computePrice(SHEET, { ...DEFAULT_CONSTANTS, applyPrinterPower: true });
    const nylon = computePrice(SHEET, { ...DEFAULT_CONSTANTS, applyNylon: true });
    // power × hours × price = 1.3 × 10 × 1400 = 18 200 (vs 14 000 in B19)
    expect(power.unitEnergyCost.toFixed()).toBe("18200");
    expect(nylon.unitLabelCost.toFixed()).toBe("10000");
    expect(off.unitEnergyCost.toFixed()).toBe("14000");
    expect(off.unitLabelCost.toFixed()).toBe("8000");
  });

  it("treats quantity only where the sheet does (chain × qty, shipment ÷ qty)", () => {
    const r = computePrice({ ...SHEET, quantity: "10", variant: "chain" });
    expect(r.batchProductionWithChain.toFixed()).toBe("8420000"); // 10 × 842 000
    expect(r.unitProductionWithChain.toFixed()).toBe("842000"); // unchanged per unit
    expect(r.unitShippingShare.toFixed()).toBe("15000"); // 150 000 ⁄ 10
    expect(r.unitDeliveryCost.toFixed()).toBe("23000"); // 8 000 + 15 000
    expect(r.batchFinalPrice.toFixed()).toBe(r.unitFinalPrice.times(10).toFixed());
  });

  it("charges no commission on direct sales (the sheet is marketplace-only)", () => {
    const direct = computePrice({ ...SHEET, channel: "direct" });
    expect(direct.unitCommission.toFixed()).toBe("0");
    // (2 085 000 + 8 000) + 158 000 delivery + 10% buffer = 2 460 300
    expect(direct.unitFinalPrice.toFixed()).toBe("2460300");
  });

  it("parses Persian/Arabic numerals and separators instead of failing", () => {
    expect(parseNum("۲۴۰").toFixed()).toBe("240");
    expect(parseNum("٣٬٠٠٠").toFixed()).toBe("3000");
    expect(parseNum("1,200").toFixed()).toBe("1200");
    expect(parseNum("۱۲٫۵").toFixed()).toBe("12.5");
    expect(() => parseNum("abc")).toThrow();
  });

  it("rejects invalid inputs and reports every row label in the sheet's wording", () => {
    expect(() => computePrice({ ...SHEET, quantity: "0" })).toThrow();
    expect(() => computePrice({ ...SHEET, weightG: "-1" })).toThrow();
    const labels = [...BREAKDOWN_ROWS, ...SALE_ROWS].map((r) => r.label);
    expect(labels).toContain("قیمت فیلامنت مصرفی (هر عدد)");
    expect(labels).toContain("هزینه ارسال محموله (کل)");
    expect(labels).toContain("قیمت نهایی هر عدد (با لیبل، کمیسیون و ارسال)");
    expect(new Set(labels).size).toBe(labels.length); // no duplicate rows
  });
});
