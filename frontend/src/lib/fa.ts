/**
 * Persian presentation: numerals (۰-۹), Jalali dates (date-fns-jalali),
 * currency labels. Internal values stay machine-readable; Persian
 * formatting is applied ONLY at the presentation layer.
 */
import { format as jalaliFormat } from "date-fns-jalali";

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

/** Format an ISO date (YYYY-MM-DD or timestamp) as a Jalali date string. */
export function faDate(iso: string | Date): string {
  const date = typeof iso === "string" ? new Date(iso) : iso;
  if (Number.isNaN(date.getTime())) return "—";
  return faDigits(jalaliFormat(date, "yyyy/MM/dd"));
}

/** Jalali date + time (Persian). */
export function faDateTime(iso: string | Date): string {
  const date = typeof iso === "string" ? new Date(iso) : iso;
  if (Number.isNaN(date.getTime())) return "—";
  return `${faDigits(jalaliFormat(date, "yyyy/MM/dd"))} — ${faDigits(jalaliFormat(date, "HH:mm"))}`;
}

/** Today's Jalali date (for defaults). */
export function faToday(): string {
  return faDigits(jalaliFormat(new Date(), "yyyy/MM/dd"));
}

/** Current Jalali year, e.g. ۱۴۰۴ (for fiscal labels). */
export function faJalaliYear(date: Date = new Date()): string {
  return faDigits(jalaliFormat(date, "yyyy"));
}
