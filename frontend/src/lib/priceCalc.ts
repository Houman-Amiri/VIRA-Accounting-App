/**
 * Sales Price Calculations — **exact** model of `قیمت نهایی.xlsx` (Annex A of
 * MASTER_PROMPT.md). Every formula below mirrors one cell of Sheet1 so a price
 * computed here is byte-for-byte the sheet's number; all math is decimal.js,
 * never native floats. Currency: Toman.
 *
 * Cell map (see Annex A):
 *   B18 = B13*B3   filament      = weight × price/gram
 *   B19 = B4*B14   electricity   = price/kWh × hours   (B2 power is optional, off
 *                                                      by default — the sheet's
 *                                                      B19 ignores it)
 *   B20 = B5*B14   depreciation
 *   B25 = SUM(B18:B20)                 production per unit
 *   E25 = B25 + B15*B9                 + ring & chain × qty (chain variant)
 *   B21 = B10 / B22 = B21/B15          shipment, per-unit share
 *   B23 label (B8 nylon optional, off by default — unused by the sheet)
 *   B24 = B23+B22                      delivery bundle per unit
 *   B28 = (production) × B6            sale total;  B29 = B28/B15 per unit
 *   B31 = B29 × commission%            unit commission
 *   B33 = B29+B31                      with commission
 *   B34 = B33+B23                      with label
 *   B35 = B34 + B24 + B34×buffer%      FINAL unit price (E35 for chain)
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
  /** B2 — printer power (kW). Applied only when `applyPrinterPower` is true. */
  printerPowerKw: MoneyLike;
  /** B3 — filament price per gram (Toman). */
  filamentPerGram: MoneyLike;
  /** B4 — electricity price per kWh (Toman). */
  electricityPerKwh: MoneyLike;
  /** B5 — printer depreciation per hour (Toman). */
  depreciationPerHour: MoneyLike;
  /** B6 — profit factor (×cost). */
  profitFactor: MoneyLike;
  /** B7 — marketplace commission (%). */
  commissionPercent: MoneyLike;
  /** B8 — packaging nylon per unit (Toman). Applied only when `applyNylon`. */
  nylonPerUnit: MoneyLike;
  /** B9 — ring & chain per unit (Toman). */
  chainPerUnit: MoneyLike;
  /** B10 — shipment cost per batch/mahmule (Toman). */
  shipmentPerBatch: MoneyLike;
  /** B23 — label cost per unit (Toman). */
  labelPerUnit: MoneyLike;
  /** B35 — risk/return buffer (%) — the sheet's literal 10%. */
  bufferPercent: MoneyLike;
  /** Wire B2 into the electricity line (`power × hours × price`). Sheet: false. */
  applyPrinterPower: boolean;
  /** Wire B8 into the delivery bundle. Sheet: false (B8 is unused there). */
  applyNylon: boolean;
}

export const DEFAULT_CONSTANTS: PriceConstants = {
  printerPowerKw: "1.3", // B2
  filamentPerGram: "3000", // B3
  electricityPerKwh: "1400", // B4
  depreciationPerHour: "10000", // B5
  profitFactor: "2.5", // B6
  commissionPercent: "13.1", // B7
  nylonPerUnit: "2000", // B8
  chainPerUnit: "8000", // B9
  shipmentPerBatch: "150000", // B10
  labelPerUnit: "8000", // B23
  bufferPercent: "10", // B35 (unnamed literal in the sheet)
  applyPrinterPower: false,
  applyNylon: false,
};

export interface PriceInputs {
  /** B13 — product weight per unit (g). */
  weightG: MoneyLike;
  /** B14 — print time per unit (h). */
  printHours: MoneyLike;
  /** B15 — quantity (pcs). */
  quantity: MoneyLike;
  variant: "plain" | "chain";
  channel: "direct" | "marketplace";
}

export interface PriceBreakdown {
  // --- هزینهها (B18..B25/E25) ---
  unitFilamentCost: Decimal; // B18
  unitEnergyCost: Decimal; // B19
  unitDepreciationCost: Decimal; // B20
  unitBaseProduction: Decimal; // B25
  unitChainCost: Decimal; // B9 share of E25
  unitProductionWithChain: Decimal; // E25 per unit
  batchProductionWithChain: Decimal; // E25
  batchShipment: Decimal; // B21
  unitShippingShare: Decimal; // B22
  unitLabelCost: Decimal; // B23 (+ optional nylon)
  unitDeliveryCost: Decimal; // B24
  // --- قیمت فروش و کمیسیون (B28..B34) ---
  batchSalePrice: Decimal; // B28/E28
  unitSalePrice: Decimal; // B29/E29
  unitCommission: Decimal; // B31
  unitWithCommission: Decimal; // B33/E33
  unitWithLabel: Decimal; // B34/E34
  unitBuffer: Decimal; // B34 × buffer%
  // --- نتیجه (B35/E35) ---
  unitFinalPrice: Decimal; // B35/E35
  batchFinalPrice: Decimal; // × quantity
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

  const filamentPerGram = parseNum(c.filamentPerGram);
  const electricityPerKwh = parseNum(c.electricityPerKwh);
  const depreciationPerHour = parseNum(c.depreciationPerHour);
  const profitFactor = parseNum(c.profitFactor);
  const commissionPercent = parseNum(c.commissionPercent);
  const chainPerUnit = parseNum(c.chainPerUnit);
  const shipmentPerBatch = parseNum(c.shipmentPerBatch);
  const labelPerUnit = parseNum(c.labelPerUnit);
  const bufferPercent = parseNum(c.bufferPercent);
  const nylonPerUnit = c.applyNylon ? parseNum(c.nylonPerUnit) : new Decimal(0);

  // ---- B18/B19/B20/B25 — production cost per unit -------------------------
  const unitFilamentCost = w.times(filamentPerGram); // B18 = B13*B3
  const energyPrice = c.applyPrinterPower
    ? parseNum(c.printerPowerKw).times(electricityPerKwh) // B2 wired in (opt-in)
    : electricityPerKwh; // B19 = B4*B14 — as authored
  const unitEnergyCost = energyPrice.times(t);
  const unitDepreciationCost = depreciationPerHour.times(t); // B20 = B5*B14
  const unitBaseProduction = unitFilamentCost
    .plus(unitEnergyCost)
    .plus(unitDepreciationCost); // B25

  // ---- E25 — ring & chain × qty (chain variant) ---------------------------
  const unitChainCost = inputs.variant === "chain" ? chainPerUnit : new Decimal(0);
  const unitProductionWithChain = unitBaseProduction.plus(unitChainCost);
  const batchProductionWithChain = unitProductionWithChain.times(q); // E25

  // ---- B21/B22/B23/B24 — packaging & shipment ----------------------------
  const batchShipment = shipmentPerBatch; // B21 = B10
  const unitShippingShare = batchShipment.div(q); // B22 = B21/B15
  const unitLabelCost = labelPerUnit.plus(nylonPerUnit); // B23 (+ optional B8)
  const unitDeliveryCost = unitLabelCost.plus(unitShippingShare); // B24 = B23+B22

  // ---- B28/B29 — sale price with the profit factor ------------------------
  const batchSalePrice = batchProductionWithChain.times(profitFactor); // B28
  const unitSalePrice = batchSalePrice.div(q); // B29 = B28/B15

  // ---- B31/B33/B34 — commission, label ------------------------------------
  const unitCommission =
    inputs.channel === "marketplace"
      ? unitSalePrice.times(commissionPercent).div(100) // B31
      : new Decimal(0);
  const unitWithCommission = unitSalePrice.plus(unitCommission); // B33
  const unitWithLabel = unitWithCommission.plus(unitLabelCost); // B34

  // ---- B35 — final: + delivery + buffer -----------------------------------
  const unitBuffer = unitWithLabel.times(bufferPercent).div(100);
  const unitFinalPrice = unitWithLabel.plus(unitDeliveryCost).plus(unitBuffer); // B35
  const batchFinalPrice = unitFinalPrice.times(q);

  return {
    unitFilamentCost,
    unitEnergyCost,
    unitDepreciationCost,
    unitBaseProduction,
    unitChainCost,
    unitProductionWithChain,
    batchProductionWithChain,
    batchShipment,
    unitShippingShare,
    unitLabelCost,
    unitDeliveryCost,
    batchSalePrice,
    unitSalePrice,
    unitCommission,
    unitWithCommission,
    unitWithLabel,
    unitBuffer,
    unitFinalPrice,
    batchFinalPrice,
  };
}

/** Breakdown rows in the sheet's own order and wording (A.3 + A.4). */
export const BREAKDOWN_ROWS: ReadonlyArray<{
  key: keyof PriceBreakdown;
  label: string;
  cell: string;
  strong?: boolean;
}> = [
  { key: "unitFilamentCost", label: "قیمت فیلامنت مصرفی (هر عدد)", cell: "B18" },
  { key: "unitEnergyCost", label: "هزینه برق مصرفی (هر عدد)", cell: "B19" },
  { key: "unitDepreciationCost", label: "هزینه استهلاک پرینت (هر عدد)", cell: "B20" },
  { key: "unitBaseProduction", label: "جمع هزینه‌های تولید (هر عدد)", cell: "B25" },
  { key: "unitChainCost", label: "حلقه و زنجیر (هر عدد)", cell: "B9" },
  {
    key: "unitProductionWithChain",
    label: "جمع هزینه‌های تولید با زنجیر (هر عدد)",
    cell: "E25",
  },
  { key: "batchShipment", label: "هزینه ارسال محموله (کل)", cell: "B21" },
  { key: "unitShippingShare", label: "هزینه بسته‌بندی و ارسال هر عدد", cell: "B22" },
  { key: "unitLabelCost", label: "هزینه لیبل (هر عدد)", cell: "B23" },
  { key: "unitDeliveryCost", label: "جمع هزینه‌های ارسال یک عدد", cell: "B24" },
];

/** Final rows (kept separate so RTL table headers stay readable). */
export const SALE_ROWS: ReadonlyArray<{
  key: keyof PriceBreakdown;
  label: string;
  cell: string;
  strong?: boolean;
}> = [
  { key: "batchSalePrice", label: "قیمت فروش کل (با ضریب سود)", cell: "B28" },
  { key: "unitSalePrice", label: "قیمت فروش هر عدد", cell: "B29" },
  { key: "unitCommission", label: "کمیسیون بازارگاه (هر عدد)", cell: "B31" },
  { key: "unitWithCommission", label: "قیمت هر عدد با کمیسیون", cell: "B33" },
  { key: "unitWithLabel", label: "قیمت هر عدد با لیبل", cell: "B34" },
  { key: "unitBuffer", label: "بافر ریسک و مرجوعی", cell: "B35 ×٪" },
  {
    key: "unitFinalPrice",
    label: "قیمت نهایی هر عدد (با لیبل، کمیسیون و ارسال)",
    cell: "B35",
    strong: true,
  },
  { key: "batchFinalPrice", label: "قیمت نهایی کل (× تیراژ)", cell: "B35×B15", strong: true },
];

/** The sheet's own example (B13=240 g, B14=10 h, B15=1) — for verification. */
export const SHEET_EXAMPLE_INPUTS: PriceInputs = {
  weightG: "240",
  printHours: "10",
  quantity: "1",
  variant: "plain",
  channel: "marketplace",
};

/** Expected B35/E35 for `SHEET_EXAMPLE_INPUTS` with `DEFAULT_CONSTANTS`. */
export const SHEET_EXPECTED = {
  plain: "2760748.5",
  chain: "2785630.5",
} as const;
