/** Civil dates never pass through midnight UTC. Instants are projected to Tehran. */
import { isValidJalaaliDate, toGregorian, toJalaali } from "jalaali-js";
export type Calendar = "jalali" | "gregorian";
export const TEHRAN = "Asia/Tehran";
export function latinDigits(value: string): string {
  return value
    .replace(/[۰-۹]/g, (d) => String(d.charCodeAt(0) - 1776))
    .replace(/[٠-٩]/g, (d) => String(d.charCodeAt(0) - 1632));
}
const pad = (n: number) => String(n).padStart(2, "0");
export function validIso(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [y, m, d] = value.split("-").map(Number);
  if (y < 1 || m < 1 || m > 12 || d < 1) return false;
  const days = [
    31,
    y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0) ? 29 : 28,
    31,
    30,
    31,
    30,
    31,
    31,
    30,
    31,
    30,
    31,
  ];
  return d <= days[m - 1];
}
export function inputToIso(value: string, calendar: Calendar): string | null {
  const parts = latinDigits(value.trim()).match(/^(\d{4})[/-](\d{1,2})[/-](\d{1,2})$/);
  if (!parts) return null;
  let [y, m, d] = parts.slice(1).map(Number);
  if (y < 1) return null;
  try {
    if (calendar === "jalali") {
      if (!isValidJalaaliDate(y, m, d)) return null;
      const g = toGregorian(y, m, d);
      y = g.gy;
      m = g.gm;
      d = g.gd;
    }
    const iso = `${String(y).padStart(4, "0")}-${pad(m)}-${pad(d)}`;
    return validIso(iso) ? iso : null;
  } catch {
    return null;
  }
}
export function isoToInput(value: string, calendar: Calendar): string {
  if (!validIso(value)) return "";
  const [y, m, d] = value.split("-").map(Number);
  try {
    if (calendar === "gregorian") return `${String(y).padStart(4, "0")}/${pad(m)}/${pad(d)}`;
    const j = toJalaali(y, m, d);
    return `${String(j.jy).padStart(4, "0")}/${pad(j.jm)}/${pad(j.jd)}`;
  } catch {
    return "";
  }
}
export function tehranParts(instant: Date): Record<string, string> {
  return Object.fromEntries(
    new Intl.DateTimeFormat("en-CA", {
      timeZone: TEHRAN,
      calendar: "gregory",
      numberingSystem: "latn",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    })
      .formatToParts(instant)
      .map((p) => [p.type, p.value]),
  );
}
export function tehranToday(instant: Date = new Date()): string {
  const p = tehranParts(instant);
  return `${p.year.padStart(4, "0")}-${p.month}-${p.day}`;
}
export function civilDate(value: string | Date): string | null {
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value))
    return validIso(value) ? value : null;
  // Reject ambiguous timestamp strings; an instant must name UTC or an offset.
  if (typeof value === "string" && !/(Z|[+-]\d{2}:\d{2})$/.test(value)) return null;
  const instant = typeof value === "string" ? new Date(value) : value;
  return Number.isNaN(instant.getTime()) ? null : tehranToday(instant);
}
