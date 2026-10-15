/** Expected values come from the XLSX, independently of the application's engine. */
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import Decimal from "decimal.js";
import fixture from "./fixtures/pricing-workbook.json";
import { computePrice, DEFAULT_CONSTANTS, type PriceBreakdown } from "@/lib/priceCalc";

it("pins the oracle to the original workbook bytes", () => {
  const workbook = readFileSync(resolve(process.cwd(), "..", fixture.source));
  expect(createHash("sha256").update(workbook).digest("hex")).toBe(fixture.sha256);
});

const COMMON_CELLS: Record<string, keyof PriceBreakdown> = {
  B18: "filamentCost",
  B19: "energyCost",
  B20: "depreciationCost",
  B21: "batchShipment",
  B22: "unitShippingShare",
  B24: "unitDeliveryCost",
  B25: "baseProduction",
  B31: "unitCommission",
  B32: "saleWithDelivery",
};
const VARIANT_CELLS: Record<string, keyof PriceBreakdown> = {
  "25": "productionTotal",
  "28": "batchSalePrice",
  "29": "unitSalePrice",
  "33": "unitWithCommission",
  "34": "unitWithLabel",
  "35": "unitFinalPrice",
};

describe.each(fixture.scenarios)("actual workbook: $name", ({ inputs, expected }) => {
  const constants = {
    ...DEFAULT_CONSTANTS,
    printerPowerKw: inputs.B2,
    filamentPerGram: inputs.B3,
    electricityPerKwh: inputs.B4,
    depreciationPerHour: inputs.B5,
    profitFactor: inputs.B6,
    commissionPercent: inputs.B7,
    nylonPerUnit: inputs.B8,
    chainPerUnit: inputs.B9,
    shipmentPerBatch: inputs.B10,
    labelPerUnit: inputs.B23,
  };
  it.each(["plain", "chain"] as const)("reproduces every %s cell", (variant) => {
    const result = computePrice(
      {
        weightG: inputs.B13,
        printHours: inputs.B14,
        quantity: inputs.B15,
        variant,
        channel: "marketplace",
      },
      constants,
    );
    const column = variant === "plain" ? "B" : "E";
    const cells = {
      ...COMMON_CELLS,
      ...Object.fromEntries(Object.entries(VARIANT_CELLS).map(([row, key]) => [column + row, key])),
    };
    const reference: Record<string, string> = expected;
    for (const [cell, key] of Object.entries(cells)) {
      expect(result[key].toFixed(4), cell).toBe(new Decimal(reference[cell]).toFixed(4));
    }
    // Supplemental values must also use the authored totals, not a normalized model.
    expect(result.unitProductionCost.toFixed(4)).toBe(
      new Decimal(reference[column + "25"]).div(inputs.B15).toFixed(4),
    );
    expect(result.unitBuffer.toFixed(4)).toBe(new Decimal(expected.B34).times("0.1").toFixed(4));
    expect(result.batchFinalPrice.toFixed(4)).toBe(
      new Decimal(reference[column + "35"]).times(inputs.B15).toFixed(4),
    );
  });
});
