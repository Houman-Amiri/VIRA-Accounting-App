/**
 * Fiscal year & Jalali report dating (Phase 7 §3).
 *
 * The V.I.R.A fiscal year is the full Iranian calendar year: it starts on
 * 1 Farvardin and ends on 29/30 Esfand.  All report date ranges and PDF/print
 * headers use Jalali (Persian) dates via lib/fa — never Gregorian.
 */
import { toGregorian, toJalaali } from "jalaali-js";

import { faDigits } from "./fa";

export const FISCAL_YEAR_START = { month: 1, day: 1 } as const; // 1 Farvardin

export interface JalaliYearRange {
  /** ISO gregorian date of 1 Farvardin (inclusive). */
  startIso: string;
  /** ISO gregorian date of last Esfand day (inclusive). */
  endIso: string;
  /** Jalali year number, e.g. 1405. */
  year: number;
  /** Persian display label, e.g. "۱۴۰۵". */
  label: string;
}

function iso(gy: number, gm: number, gd: number): string {
  return `${gy}-${String(gm).padStart(2, "0")}-${String(gd).padStart(2, "0")}`;
}

/** Full Jalali year range starting 1 Farvardin. */
export function jalaliYear(jy: number): JalaliYearRange {
  const start = toGregorian(jy, FISCAL_YEAR_START.month, FISCAL_YEAR_START.day);
  const next = toGregorian(jy + 1, FISCAL_YEAR_START.month, FISCAL_YEAR_START.day);
  const endDate = new Date(Date.UTC(next.gy, next.gm - 1, next.gd));
  endDate.setUTCDate(endDate.getUTCDate() - 1); // last day of Esfand
  return {
    startIso: iso(start.gy, start.gm, start.gd),
    endIso: endDate.toISOString().slice(0, 10),
    year: jy,
    label: faDigits(jy),
  };
}

/** The Jalali (fiscal) year containing the given ISO gregorian date. */
export function fiscalYearFor(isoDate: string): JalaliYearRange {
  const [y, m, d] = isoDate.split("-").map(Number);
  const j = toJalaali(y, m, d);
  return jalaliYear(j.jy);
}

/** Default report range: the fiscal year containing today. */
export function currentFiscalYear(todayIso: string): JalaliYearRange {
  return fiscalYearFor(todayIso);
}
