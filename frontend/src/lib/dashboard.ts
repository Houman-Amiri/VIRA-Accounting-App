/** Dashboard projection only: exact money until the ECharts plotting boundary. */
import { rialToToman, sumMoney, toDecimal, type MoneyLike } from "@/lib/money";

/** Civil day in Tehran, not UTC (especially around Nowruz / local midnight). */
export function tehranDay(now = new Date()): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Tehran",
    calendar: "gregory",
    numberingSystem: "latn",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const part = (name: Intl.DateTimeFormatPartTypes) => parts.find((p) => p.type === name)!.value;
  return `${part("year")}-${part("month")}-${part("day")}`;
}

export function daysBefore(day: string, days: number): string {
  const date = new Date(`${day}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() - days);
  return date.toISOString().slice(0, 10);
}

export function trialDifference(rows: Array<{ debit: string; credit: string }>): string {
  return sumMoney(rows.map((r) => r.debit))
    .minus(sumMoney(rows.map((r) => r.credit)))
    .toFixed(4);
}

/** Ledger = IRR; operations/pricing = TOMAN. Convert only once. */
export function chartToman(value: MoneyLike, unit: "IRR" | "TOMAN" = "IRR"): number {
  return (unit === "IRR" ? rialToToman(value) : toDecimal(value)).toNumber();
}

export function inventoryValue(item: { quantity: string; unit_price: string }): string {
  return toDecimal(item.quantity).times(item.unit_price).toFixed(4);
}

/** A stored date-only value must not shift with the viewer's browser timezone. */
export function dashboardDate(day: string): string {
  const date = new Date(`${day}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return "—";
  const parts = new Intl.DateTimeFormat("fa-IR", {
    timeZone: "Asia/Tehran",
    calendar: "persian",
    numberingSystem: "arabext",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(date);
  const part = (name: Intl.DateTimeFormatPartTypes) => parts.find((p) => p.type === name)!.value;
  return `${part("year")}/${part("month")}/${part("day")}`;
}
