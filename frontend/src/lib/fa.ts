/**
 * Persian presentation: numerals (۰-۹), Jalali dates (date-fns-jalali),
 * currency labels. Internal values stay machine-readable; Persian
 * formatting is applied ONLY at the presentation layer.
 */
import { civilDate, isoToInput, tehranParts, tehranToday, type Calendar } from "./calendar";

const FA_DIGITS = ["۰", "۱", "۲", "۳", "۴", "۵", "۶", "۷", "۸", "۹"];

/** Convert ASCII digits in a string to Persian numerals. */
export function faDigits(input: string | number): string {
  return String(input).replace(/[0-9]/g, (d) => FA_DIGITS[Number(d)]);
}

/** Persian thousands separators + Persian digits (display only). */
export function faNumber(value: string | number): string {
  const [int, dec] = String(value).replace(/,/g, "").split(".");
  const grouped = int.replace(/\B(?=(\d{3})+(?!\d))/g, "٬");
  const out = dec ? `${grouped}.${dec}` : grouped;
  return faDigits(out);
}

/** Date-only stays the same civil day; timestamps are projected to Tehran. */
export function faDate(value: string | Date, calendar: Calendar = "jalali"): string {
  const civil = civilDate(value);
  return civil ? faDigits(isoToInput(civil, calendar) || "—") : "—";
}
export function faDateTime(value: string | Date, calendar: Calendar = "jalali"): string {
  const civil = civilDate(value);
  if (!civil) return "—";
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value))
    return faDate(value, calendar);
  const instant = typeof value === "string" ? new Date(value) : value;
  const p = tehranParts(instant);
  return `${faDate(civil, calendar)} — ${faDigits(`${p.hour}:${p.minute}`)}`;
}
export function faToday(calendar: Calendar = "jalali"): string {
  return faDate(tehranToday(), calendar);
}
/** Fiscal labels stay Jalali independently of display preference. */
export function faJalaliYear(date: Date = new Date()): string {
  return faDate(date).slice(0, 4);
}
