/**
 * Sales Price Calculations — normalized model from `قیمت نهایی.xlsx`
 * (see docs/product-spec.md §4.3). All math is decimal.js; display formats
 * happen elsewhere. Toman throughout.
 */
import Decimal from "decimal.js";
import { toDecimal, type MoneyLike } from "./money";

export interface PriceConstants {
  /** P — printer power (kW) */
  printerPowerKw: Decimal;
  /** F — filament price per gram (Toman) */
  filamentPerGram: Decimal;
  /** E — electricity per kWh (Toman) */
  electricityPerKwh: Decimal;
  /** D — printer depreciation per hour (Toman) */
  depreciationPerHour: Decimal;
  /** R — profit multiplier (×) */
  profitFactor: Decimal;
  /** C — marketplace commission (%) */
  commissionPercent: Decimal;
  /** N — packaging nylon per unit (Toman) */
  nylonPerUnit: Decimal;
  /** CH — ring & chain per unit (Toman) */
  chainPerUnit: Decimal;
  /** S — shipment per batch (Toman) */
  shipmentPerBatch: Decimal;
  /** L — label per unit (Toman) */
  labelPerUnit: Decimal;
  /** B — risk/return buffer (%) */
  bufferPercent: Decimal;
}

export const DEFAULT_CONSTANTS: PriceConstants = {
  printerPowerKw: toDecimal(1.3),
  filamentPerGram: toDecimal(3000),
  electricityPerKwh: toDecimal(1400),
  depreciationPerHour: toDecimal(10000),
  profitFactor: toDecimal(2.5),
  commissionPercent: toDecimal(13.1),
  nylonPerUnit: toDecimal(2000),
  chainPerUnit: toDecimal(8000),
  shipmentPerBatch: toDecimal(150000),
  labelPerUnit: toDecimal(8000),
  bufferPercent: toDecimal(10),
};

export interface PriceInputs {
  /** w — product weight (g, per unit) */
  weightG: MoneyLike;
  /** t — print time (h, per unit) */
  printHours: MoneyLike;
  /** q — quantity (pcs) */
  quantity: MoneyLike;
  variant: "plain" | "chain";
  channel: "direct" | "marketplace";
}

export interface PriceBreakdown {
  unitFilamentCost: Decimal;
  unitEnergyCost: Decimal;
  unitDepreciationCost: Decimal;
  unitChainCost: Decimal;
  unitProductionCost: Decimal;
  batchProductionCost: Decimal;
  unitShippingShare: Decimal;
  unitDeliveryCost: Decimal;
  unitSalePrice: Decimal;
  unitCommission: Decimal;
  merchandise: Decimal;
  buffer: Decimal;
  unitFinalPrice: Decimal;
  batchTotal: Decimal;
}

export function computePrice(inputs: PriceInputs, c: PriceConstants = DEFAULT_CONSTANTS): PriceBreakdown {
  const w = toDecimal(inputs.weightG);
  const t = toDecimal(inputs.printHours);
  const q = toDecimal(inputs.quantity);
  if (w.isNegative() || t.isNegative() || q.lte(0)) {
    throw new Error("invalid inputs: weight/hours ≥ 0, quantity > 0");
  }

  const unitFilamentCost = w.times(c.filamentPerGram);
  const unitEnergyCost = c.printerPowerKw.times(t).times(c.electricityPerKwh);
  const unitDepreciationCost = t.times(c.depreciationPerHour);
  const unitChainCost = inputs.variant === "chain" ? c.chainPerUnit : new Decimal(0);
  const unitProductionCost = unitFilamentCost
    .plus(unitEnergyCost)
    .plus(unitDepreciationCost)
    .plus(unitChainCost);
  const batchProductionCost = unitProductionCost.times(q);

  const unitShippingShare = c.shipmentPerBatch.div(q);
  const unitDeliveryCost = c.nylonPerUnit.plus(c.labelPerUnit).plus(unitShippingShare);

  const unitSalePrice = unitProductionCost.times(c.profitFactor);
  const unitCommission =
    inputs.channel === "marketplace"
      ? unitSalePrice.times(c.commissionPercent).div(100)
      : new Decimal(0);
  const merchandise = unitSalePrice.plus(unitCommission);
  const buffer = merchandise.times(c.bufferPercent).div(100);
  const unitFinalPrice =
    inputs.channel === "marketplace"
      ? merchandise.plus(unitDeliveryCost).plus(buffer)
      : merchandise.plus(buffer);

  return {
    unitFilamentCost,
    unitEnergyCost,
    unitDepreciationCost,
    unitChainCost,
    unitProductionCost,
    batchProductionCost,
    unitShippingShare,
    unitDeliveryCost,
    unitSalePrice,
    unitCommission,
    merchandise,
    buffer,
    unitFinalPrice,
    batchTotal: unitFinalPrice.times(q),
  };
}

export const BREAKDOWN_LABELS: Record<keyof PriceBreakdown, string> = {
  unitFilamentCost: "هزینه فیلامنت مصرفی (هر عدد)",
  unitEnergyCost: "هزینه برق مصرفی (هر عدد)",
  unitDepreciationCost: "هزینه استهلاک پرینتر (هر عدد)",
  unitChainCost: "هزینه حلقه و زنجیر (هر عدد)",
  unitProductionCost: "هزینه تولید هر عدد",
  batchProductionCost: "هزینه تولید کل",
  unitShippingShare: "سهم ارسال هر عدد",
  unitDeliveryCost: "هزینه بسته‌بندی، لیبل و ارسال هر عدد",
  unitSalePrice: "قیمت فروش هر عدد",
  unitCommission: "کمیسیون بازارگاه (هر عدد)",
  merchandise: "جمع فروش + کمیسیون",
  buffer: "بافر ریسک و مرجوعی",
  unitFinalPrice: "قیمت نهایی هر عدد",
  batchTotal: "قیمت نهایی کل",
};
