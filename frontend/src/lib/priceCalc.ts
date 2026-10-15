/**
 * Literal model of `قیمت نهایی.xlsx` (Sheet1), selected by the user in repair
 * phase 4. Do NOT silently normalize dimensional quirks:
 * - B25 is NOT multiplied by quantity; E25 = B25 + quantity * chain cost.
 * - B31 uses literal 13.1%, not B7, and BOTH B33/E33 reuse that plain commission.
 * - BOTH B35/E35 reuse the plain B34 * 10% buffer; B2/B8 are unused.
 * All money arithmetic is decimal.js. Only fixed-scale API/display boundaries
 * round. Direct sales are an explicit extension (commission zero), not XLSX.
 */
import Decimal from "decimal.js";
import { toDecimal, type MoneyLike } from "./money";

/** Numbers may arrive from inputs as "۲۴۰", "1,200" or "12.5" — normalize. */
export function parseNum(value: MoneyLike | null | undefined): Decimal {
  if (value === null || value === undefined) return new Decimal(0);
  if (typeof value === "number" || value instanceof Decimal) return toDecimal(value);
  let text = String(value).trim();
  if (!text) return new Decimal(0);
  // Persian ۰-۹ / Arabic ٠-٩ digits → ASCII
  text = text.replace(/[۰-۹]/g, (d) => String("۰۱۲۳۴۵۶۷۸۹".indexOf(d)));
  text = text.replace(/[٠-٩]/g, (d) => String("٠١٢٣٤٥٦٧٨٩".indexOf(d)));
  // Persian decimal separator ٫ / Arabic ٬ thousands / , as thousands / spaces
  text = text.replace(/٫/g, ".").replace(/[٬,\s]/g, "");
  if (!/^-?\d*\.?\d*$/.test(text) || text === "-" || text === ".") {
    throw new Error(`عدد نامعتبر: ${String(value)}`);
  }
  return toDecimal(text);
}

export interface PriceConstants {
  printerPowerKw: MoneyLike; // B2: defined but unused in the workbook
  filamentPerGram: MoneyLike; // B3
  electricityPerKwh: MoneyLike; // B4
  depreciationPerHour: MoneyLike; // B5
  profitFactor: MoneyLike; // B6 (multiplier, not percent)
  commissionPercent: MoneyLike; // B7: defined but B31 hardcodes 13.1%
  nylonPerUnit: MoneyLike; // B8: defined but unused in the workbook
  chainPerUnit: MoneyLike; // B9
  shipmentPerBatch: MoneyLike; // B10
  labelPerUnit: MoneyLike; // B23
}

export const DEFAULT_CONSTANTS: PriceConstants = {
  printerPowerKw: "1.3",
  filamentPerGram: "3000",
  electricityPerKwh: "1400",
  depreciationPerHour: "10000",
  profitFactor: "2.5",
  commissionPercent: "13.1",
  nylonPerUnit: "2000",
  chainPerUnit: "8000",
  shipmentPerBatch: "150000",
  labelPerUnit: "8000",
};

export interface PriceInputs {
  /** B13/B14 are used as entered, never automatically multiplied by B15. */
  weightG: MoneyLike;
  printHours: MoneyLike;
  quantity: MoneyLike; // B15
  variant: "plain" | "chain";
  channel: "direct" | "marketplace";
}

export interface PriceBreakdown {
  filamentCost: Decimal; // B18
  energyCost: Decimal; // B19
  depreciationCost: Decimal; // B20
  baseProduction: Decimal; // B25
  productionTotal: Decimal; // B25 or E25
  /** Derived per-unit snapshot for orders/jobs; NOT a separate Excel cell. */
  unitProductionCost: Decimal; // (B25 or E25) / B15
  batchShipment: Decimal; // B21
  unitShippingShare: Decimal; // B22
  unitLabelCost: Decimal; // B23
  unitDeliveryCost: Decimal; // B24
  batchSalePrice: Decimal; // B28/E28
  unitSalePrice: Decimal; // B29/E29
  unitCommission: Decimal; // B31 (shared for both variants)
  saleWithDelivery: Decimal; // B32 only (no E32 in the workbook)
  unitWithCommission: Decimal; // B33/E33
  unitWithLabel: Decimal; // B34/E34
  unitBuffer: Decimal; // B34 * 10%, shared by both variants
  unitFinalPrice: Decimal; // B35/E35
  batchFinalPrice: Decimal; // derived: unit final * quantity
}

export function computePrice(
  inputs: PriceInputs,
  c: PriceConstants = DEFAULT_CONSTANTS,
): PriceBreakdown {
  const w = parseNum(inputs.weightG);
  const t = parseNum(inputs.printHours);
  const q = parseNum(inputs.quantity);
  if (w.isNegative() || t.isNegative()) {
    throw new Error("ورودی نامعتبر: وزن و زمان پرینت باید صفر یا بیشتر باشند");
  }
  if (q.lte(0)) throw new Error("ورودی نامعتبر: تیراژ باید بزرگ‌تر از صفر باشد");

  const costs = [
    c.filamentPerGram,
    c.electricityPerKwh,
    c.depreciationPerHour,
    c.profitFactor,
    c.chainPerUnit,
    c.shipmentPerBatch,
    c.labelPerUnit,
  ].map(parseNum);
  if (costs.some((value) => value.isNegative())) {
    throw new Error("ورودی نامعتبر: ثابت‌های هزینه و ضریب سود نباید منفی باشند");
  }
  const [
    filamentPerGram,
    electricityPerKwh,
    depreciationPerHour,
    profitFactor,
    chainPerUnit,
    shipmentPerBatch,
    labelPerUnit,
  ] = costs;

  const filamentCost = w.times(filamentPerGram); // B18 = B13*B3
  const energyCost = electricityPerKwh.times(t); // B19 = B4*B14 (NOT B2)
  const depreciationCost = depreciationPerHour.times(t); // B20 = B5*B14
  const baseProduction = filamentCost.plus(energyCost).plus(depreciationCost); // B25
  const productionTotal =
    inputs.variant === "chain"
      ? baseProduction.plus(q.times(chainPerUnit)) // E25 = B25+(B15*B9)
      : baseProduction;
  const unitProductionCost = productionTotal.div(q); // derived snapshot
  const batchShipment = shipmentPerBatch; // B21
  const unitShippingShare = batchShipment.div(q); // B22
  const unitLabelCost = labelPerUnit; // B23 (NOT B8)
  const unitDeliveryCost = unitLabelCost.plus(unitShippingShare); // B24
  const batchSalePrice = productionTotal.times(profitFactor); // B28/E28
  const unitSalePrice = batchSalePrice.div(q); // B29/E29
  const plainSalePrice = baseProduction.times(profitFactor); // B28, even for chain
  const unitCommission =
    inputs.channel === "marketplace"
      ? plainSalePrice.div(q).times("13.1").div(100) // B31 (NOT B7 or E29)
      : new Decimal(0);
  const saleWithDelivery = plainSalePrice.plus(unitDeliveryCost); // B32
  const unitWithCommission = unitSalePrice.plus(unitCommission); // B33/E33
  const unitWithLabel = unitWithCommission.plus(unitLabelCost); // B34/E34
  const plainWithLabel = plainSalePrice.div(q).plus(unitCommission).plus(unitLabelCost); // B34
  const unitBuffer = plainWithLabel.times("0.1"); // BOTH B35/E35 reference B34, not E34
  const unitFinalPrice = unitWithLabel.plus(unitDeliveryCost).plus(unitBuffer); // B35/E35
  const batchFinalPrice = unitFinalPrice.times(q); // derived, not a workbook cell

  return {
    filamentCost,
    energyCost,
    depreciationCost,
    baseProduction,
    productionTotal,
    unitProductionCost,
    batchShipment,
    unitShippingShare,
    unitLabelCost,
    unitDeliveryCost,
    batchSalePrice,
    unitSalePrice,
    unitCommission,
    saleWithDelivery,
    unitWithCommission,
    unitWithLabel,
    unitBuffer,
    unitFinalPrice,
    batchFinalPrice,
  };
}

export interface PriceRow {
  key: keyof PriceBreakdown;
  label: string;
  cell: string;
  chainCell?: string;
  plainOnly?: boolean;
  strong?: boolean;
}

/** Original sheet order, cell addresses and wording; raw costs are not per-unit. */
export const BREAKDOWN_ROWS: ReadonlyArray<PriceRow> = [
  { key: "filamentCost", label: "قیمت فیلامنت مصرفی", cell: "B18" },
  { key: "energyCost", label: "هزینه برق مصرفی", cell: "B19" },
  { key: "depreciationCost", label: "هزینه استهلاک پرینت محصول", cell: "B20" },
  { key: "batchShipment", label: "هزینه بسته‌بندی و ارسال محموله", cell: "B21" },
  { key: "unitShippingShare", label: "هزینه بسته‌بندی و ارسال هر عدد", cell: "B22" },
  { key: "unitLabelCost", label: "هزینه لیبل", cell: "B23" },
  { key: "unitDeliveryCost", label: "جمع هزینه‌های ارسال یک عدد", cell: "B24" },
  { key: "productionTotal", label: "جمع هزینه‌های تولید", cell: "B25", chainCell: "E25" },
];

export const SALE_ROWS: ReadonlyArray<PriceRow> = [
  { key: "batchSalePrice", label: "قیمت فروش کل", cell: "B28", chainCell: "E28" },
  { key: "unitSalePrice", label: "قیمت فروش هر عدد محصول", cell: "B29", chainCell: "E29" },
  { key: "unitCommission", label: "کمیسیون بازارگاه برای هر عدد (مشترک)", cell: "B31" },
  {
    key: "saleWithDelivery",
    label: "قیمت کل با هزینه ارسال بازارگاه",
    cell: "B32",
    plainOnly: true,
  },
  { key: "unitWithCommission", label: "قیمت هر عدد با کمیسیون", cell: "B33", chainCell: "E33" },
  { key: "unitWithLabel", label: "قیمت هر عدد با لیبل", cell: "B34", chainCell: "E34" },
  { key: "unitBuffer", label: "بافر ریسک و مرجوعی (۱۰٪)", cell: "B34×10%" },
  {
    key: "unitFinalPrice",
    label: "قیمت نهایی هر عدد (با لیبل، کمیسیون و ارسال)",
    cell: "B35",
    chainCell: "E35",
    strong: true,
  },
  {
    key: "batchFinalPrice",
    label: "قیمت نهایی کل (محاسبهٔ تکمیلی × تیراژ)",
    cell: "B35×B15",
    chainCell: "E35×B15",
    strong: true,
  },
];

export const SHEET_EXAMPLE_INPUTS: PriceInputs = {
  weightG: "240",
  printHours: "10",
  quantity: "1",
  variant: "plain",
  channel: "marketplace",
};

/** Independently checked against the original cached B35/E35, not normalized math. */
export const SHEET_EXPECTED = { plain: "2760748.5", chain: "2780748.5" } as const;
