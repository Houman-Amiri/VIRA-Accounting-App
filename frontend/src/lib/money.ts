/**
 * Exact monetary arithmetic on the client (decimal.js).
 *
 * Native JS `number` is FORBIDDEN for monetary calculations. API payloads
 * carry money as fixed-scale strings ("1250.5000"); all live form math and
 * aggregations go through Decimal here.
 */
import Decimal from "decimal.js";

Decimal.set({ precision: 40, rounding: Decimal.ROUND_HALF_EVEN });

export const MONEY_DP = 4;

export type MoneyLike = string | number | Decimal;

/** Parse an API money string into an exact Decimal (rejects non-finite). */
export function toDecimal(value: MoneyLike | null | undefined): Decimal {
  if (value === null || value === undefined || value === "") return new Decimal(0);
  const d = new Decimal(value);
  if (!d.isFinite()) throw new Error(`invalid money value: ${String(value)}`);
  return d;
}

/** Serialize to the fixed 4-decimal API representation. */
export function toMoneyString(value: MoneyLike | null | undefined): string {
  return toDecimal(value).toFixed(MONEY_DP);
}

/** Exact sum of money values (never reduces through float). */
export function sumMoney(values: Array<MoneyLike | null | undefined>): Decimal {
  return values.reduce<Decimal>((acc, v) => acc.plus(toDecimal(v)), new Decimal(0));
}

/** Signed balance: debits minus credits. */
export function balance(debits: MoneyLike, credits: MoneyLike): Decimal {
  return toDecimal(debits).minus(toDecimal(credits));
}

/**
 * Canonical unit policy (config: `base_currency="IRR"`, `display_currency="IRT"`):
 * the ledger stores Rials (scaled ×10 000); the UI presents Tomans with
 * 1 Toman = 10 Rials — the factor is applied EXACTLY ONCE, here at the
 * presentation edge (or its inverse at form input).
 */
export const RIAL_PER_TOMAN = 10;

/** Rial amount (API/DB) → Toman amount (display). */
export function rialToToman(value: MoneyLike | null | undefined): Decimal {
  return toDecimal(value).div(RIAL_PER_TOMAN);
}

/** Toman amount (form input) → Rial amount (API/DB). */
export function tomanToRial(value: MoneyLike | null | undefined): Decimal {
  return toDecimal(value).times(RIAL_PER_TOMAN);
}

export function isZero(value: MoneyLike): boolean {
  return toDecimal(value).isZero();
}

export function abs(value: MoneyLike): Decimal {
  return toDecimal(value).abs();
}

export { Decimal };
