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
  /**
   * The workbook still carries the marketplace commission (B31–B35); the app
   * prices every sale as a direct sale, so this is only used to fill the
   * «مرجع بازارگاه» rows on the pricing page. Defaults to `direct`.
   */
  channel?: "direct" | "marketplace";
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
    (inputs.channel ?? "direct") === "marketplace"
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

// -------------------------------------------- owner-defined price additions ---
/**
 * The owner's own constants (added on the «قیمت‌گذاری» page), applied on top of
 * the sheet-exact breakdown. `computePrice` itself is untouched: the workbook
 * parity is a hard constraint, so the extra costs live in this separate step.
 */
export type CustomMethod = "PER_UNIT" | "PER_BATCH" | "PERCENT_OF_COST" | "PERCENT_OF_PRICE";

export interface CustomConstantInput {
  name: string;
  method: CustomMethod;
  value: MoneyLike;
  is_active: boolean;
}

export interface CustomConstantLine {
  name: string;
  method: CustomMethod;
  /** Per-unit effect of this constant, in the same unit as the breakdown. */
  amount: Decimal;
}

export interface CustomPriceResult {
  lines: CustomConstantLine[];
  /** Sum of every line — what one unit gains on top of the base price. */
  perUnit: Decimal;
  /** «قیمت فروش هر عدد محصول» + every line (the app's final price). */
  unitFinalPrice: Decimal;
  batchFinalPrice: Decimal;
}

/**
 * Turn one custom constant into a per-unit amount.
 *
 * - `PER_UNIT`         the value itself;
 * - `PER_BATCH`        the value split over the run size;
 * - `PERCENT_OF_COST`  a percentage of the unit production cost;
 * - `PERCENT_OF_PRICE` a percentage of «قیمت فروش هر عدد محصول» (the row the
 *   final price is based on).
 *
 * Percentages are always taken from the *sheet* amounts, never from a total
 * that already contains other custom constants, so the order of the rows can
 * never change the money.
 */
export function customConstantAmount(
  constant: CustomConstantInput,
  base: PriceBreakdown,
  quantity: MoneyLike,
): Decimal {
  const value = parseNum(constant.value);
  if (value.isNegative()) throw new Error("ثابت‌های قیمت‌گذاری نباید منفی باشند");
  switch (constant.method) {
    case "PER_UNIT":
      return value;
    case "PER_BATCH": {
      const q = parseNum(quantity);
      if (q.lte(0)) throw new Error("تیراژ باید بزرگ‌تر از صفر باشد");
      return value.div(q);
    }
    case "PERCENT_OF_COST":
      return base.unitProductionCost.times(value).div(100);
    case "PERCENT_OF_PRICE":
      return base.unitSalePrice.times(value).div(100);
    default:
      return new Decimal(0);
  }
}

export function applyCustomConstants(
  base: PriceBreakdown,
  constants: readonly CustomConstantInput[],
  quantity: MoneyLike,
): CustomPriceResult {
  const active = constants.filter((constant) => constant.is_active);
  const lines = active.map((constant) => ({
    name: constant.name,
    method: constant.method,
    amount: customConstantAmount(constant, base, quantity),
  }));
  const perUnit = lines.reduce((sum, line) => sum.plus(line.amount), new Decimal(0));
  const unitFinalPrice = base.unitSalePrice.plus(perUnit);
  return {
    lines,
    perUnit,
    unitFinalPrice,
    batchFinalPrice: unitFinalPrice.times(parseNum(quantity)),
  };
}

// ------------------------------------------------------- owner variables ---
/**
 * A *variable* is a number the owner re-enters for each job («نرخ دلار امروز»,
 * «اجرت پرسنل»). Unlike a constant, it carries a **scope**:
 *
 * - `PER_UNIT`  (جزیی) — the number lands on every piece;
 * - `PER_ORDER` (کلی)  — the number lands on the order as a whole, either added
 *   once to the total (`ONE_TIME`) or spread over the quantity (`SPLIT`).
 *
 * Percent bases are always taken from the sheet amounts, never from a running
 * total, so the order of the rows can never change the money.
 */
export type VariableScope = "PER_UNIT" | "PER_ORDER";
export type VariableBasis = "AMOUNT" | "PERCENT_OF_COST" | "PERCENT_OF_PRICE";
export type VariableAllocation = "ONE_TIME" | "SPLIT";

export interface VariableInput {
  name: string;
  scope: VariableScope;
  basis: VariableBasis;
  allocation: VariableAllocation;
  value: MoneyLike;
  /**
   * How many times this variable applies to *this* calculation (۲ محموله،
   * ۳ قالب). Optional and never saved: the default is one.
   */
  count?: MoneyLike;
  is_active: boolean;
}

export interface VariableLine {
  name: string;
  scope: VariableScope;
  basis: VariableBasis;
  allocation: VariableAllocation;
  /** The count the owner typed for this calculation (default one). */
  count: Decimal;
  /** value × count — what one occurrence would cost × how many there are. */
  amount: Decimal;
  /** Effect on the price of one piece (zero for a one-time order amount). */
  perUnit: Decimal;
  /** Effect on the order total, whichever scope applies. */
  orderTotal: Decimal;
  /** True when the amount is added once to the total, not per piece. */
  oneTime: boolean;
}

export interface VariableResult {
  lines: VariableLine[];
  /** Sum of the per-piece effects — what one unit gains. */
  perUnit: Decimal;
  /** Sum of the amounts that only hit the order total. */
  oneTime: Decimal;
}

/** One variable's effect on a single unit and on the whole order. */
export function variableEffect(
  variable: VariableInput,
  base: PriceBreakdown,
  quantity: MoneyLike,
): VariableLine {
  const value = parseNum(variable.value);
  if (value.isNegative()) throw new Error("متغیرهای قیمت‌گذاری نباید منفی باشند");
  const count = variable.count === undefined ? new Decimal(1) : parseNum(variable.count);
  if (count.isNegative()) throw new Error("تعداد متغیر نمی‌تواند منفی باشد");
  // «۲ محموله × ۱۵۰٬۰۰۰»: the number the owner types is per occurrence.
  const amount = value.times(count);
  const q = parseNum(quantity);
  if (q.lte(0)) throw new Error("تیراژ باید بزرگ‌تر از صفر باشد");

  const perPiece =
    variable.basis === "AMOUNT"
      ? amount
      : variable.basis === "PERCENT_OF_COST"
        ? base.unitProductionCost.times(amount).div(100)
        : base.unitSalePrice.times(amount).div(100);

  if (variable.scope === "PER_UNIT") {
    return {
      name: variable.name,
      scope: variable.scope,
      basis: variable.basis,
      allocation: variable.allocation,
      count,
      amount,
      perUnit: perPiece,
      orderTotal: perPiece.times(q),
      oneTime: false,
    };
  }
  const orderTotal = variable.basis === "AMOUNT" ? amount : perPiece.times(q);
  const split = variable.allocation === "SPLIT";
  return {
    name: variable.name,
    scope: variable.scope,
    basis: variable.basis,
    allocation: variable.allocation,
    count,
    amount,
    perUnit: split ? orderTotal.div(q) : new Decimal(0),
    orderTotal,
    oneTime: !split,
  };
}

export function applyVariables(
  base: PriceBreakdown,
  variables: readonly VariableInput[],
  quantity: MoneyLike,
): VariableResult {
  const lines = variables
    .filter((variable) => variable.is_active)
    .map((variable) => variableEffect(variable, base, quantity));
  return {
    lines,
    perUnit: lines.reduce((sum, line) => sum.plus(line.perUnit), new Decimal(0)),
    oneTime: lines
      .filter((line) => line.oneTime)
      .reduce((sum, line) => sum.plus(line.orderTotal), new Decimal(0)),
  };
}
