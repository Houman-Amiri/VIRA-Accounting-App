import { describe, expect, it } from "vitest";
import {
  BREAKDOWN_ROWS,
  computePrice,
  DEFAULT_CONSTANTS,
  parseNum,
  SALE_ROWS,
  SHEET_EXPECTED,
  SHEET_EXAMPLE_INPUTS,
} from "@/lib/priceCalc";

const SHEET = SHEET_EXAMPLE_INPUTS;

describe("pricing policy — user-selected literal XLSX formulas", () => {
  it("reproduces the cached B35/E35 instead of the former normalized chain price", () => {
    expect(computePrice(SHEET).unitFinalPrice.toFixed()).toBe(SHEET_EXPECTED.plain);
    expect(computePrice({ ...SHEET, variant: "chain" }).unitFinalPrice.toFixed()).toBe(
      SHEET_EXPECTED.chain,
    );
    expect(SHEET_EXPECTED.chain).toBe("2780748.5");
  });

  it("shares both B31 commission and B34 buffer across the two variants", () => {
    const plain = computePrice(SHEET);
    const chain = computePrice({ ...SHEET, variant: "chain" });
    expect(chain.unitCommission.toFixed()).toBe("273135");
    expect(chain.unitCommission.eq(plain.unitCommission)).toBe(true);
    expect(chain.unitWithLabel.toFixed()).toBe("2386135"); // E34
    expect(chain.unitBuffer.toFixed()).toBe("236613.5"); // B34*10%, NOT E34
    expect(chain.unitBuffer.eq(plain.unitBuffer)).toBe(true);
  });

  it("does not wire the unused B2/B7/B8 into formulas", () => {
    const original = computePrice(SHEET);
    const changed = computePrice(SHEET, {
      ...DEFAULT_CONSTANTS,
      printerPowerKw: "99",
      commissionPercent: "99",
      nylonPerUnit: "99999",
    });
    expect(changed.energyCost.toFixed()).toBe("14000");
    expect(changed.unitLabelCost.toFixed()).toBe("8000");
    expect(changed.unitFinalPrice.eq(original.unitFinalPrice)).toBe(true);
  });

  it("preserves B25/E25/B28/E28 and their quantity divisions literally", () => {
    const plain = computePrice({ ...SHEET, quantity: "10" });
    const chain = computePrice({ ...SHEET, quantity: "10", variant: "chain" });
    expect(plain.productionTotal.toFixed()).toBe("834000"); // NOT 8,340,000
    expect(chain.productionTotal.toFixed()).toBe("914000"); // B25+10*B9
    expect(chain.unitProductionCost.toFixed()).toBe("91400"); // derived per-unit snapshot
    expect(plain.batchSalePrice.toFixed()).toBe("2085000");
    expect(plain.unitSalePrice.toFixed()).toBe("208500");
    expect(chain.unitShippingShare.toFixed()).toBe("15000");
    expect(plain.unitFinalPrice.toFixed()).toBe("291194.85");
    expect(chain.unitFinalPrice.toFixed()).toBe("311194.85");
  });

  it("keeps direct sales explicit: zero commission but the buffer remains", () => {
    const direct = computePrice({ ...SHEET, channel: "direct" });
    expect(direct.unitCommission.toFixed()).toBe("0");
    expect(direct.unitBuffer.toFixed()).toBe("209300");
    expect(direct.unitFinalPrice.toFixed()).toBe("2460300");
  });

  it("parses Persian/Arabic numerals, separators and decimals exactly", () => {
    expect(parseNum("۲۴۰").toFixed()).toBe("240");
    expect(parseNum("٣٬٠٠٠").toFixed()).toBe("3000");
    expect(parseNum("1,200").toFixed()).toBe("1200");
    expect(parseNum("۱۲٫۵").toFixed()).toBe("12.5");
    expect(
      computePrice({
        ...SHEET,
        weightG: "۲۴۰",
        printHours: "۱۰",
        quantity: "۱",
      }).unitFinalPrice.toFixed(),
    ).toBe(SHEET_EXPECTED.plain);
    for (const bad of ["abc", "NaN", "Infinity", ".", "-"]) {
      expect(() => parseNum(bad)).toThrow();
    }
  });

  it("rejects invalid quantities, negative inputs and negative costs", () => {
    for (const quantity of ["0", "-1", "NaN"])
      expect(() => computePrice({ ...SHEET, quantity })).toThrow();
    expect(() => computePrice({ ...SHEET, weightG: "-1" })).toThrow();
    expect(() => computePrice({ ...SHEET, printHours: "-1" })).toThrow();
    expect(() => computePrice(SHEET, { ...DEFAULT_CONSTANTS, filamentPerGram: "-1" })).toThrow();
  });

  it("labels actual cells separately from derived values without duplicate rows", () => {
    const rows = [...BREAKDOWN_ROWS, ...SALE_ROWS];
    expect(rows.find((r) => r.key === "productionTotal")).toMatchObject({
      cell: "B25",
      chainCell: "E25",
    });
    expect(rows.find((r) => r.key === "saleWithDelivery")).toMatchObject({
      cell: "B32",
      plainOnly: true,
    });
    expect(rows.find((r) => r.key === "unitFinalPrice")).toMatchObject({
      cell: "B35",
      chainCell: "E35",
    });
    expect(new Set(rows.map((r) => r.label)).size).toBe(rows.length);
  });
});
