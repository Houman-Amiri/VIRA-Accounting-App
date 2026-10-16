import { describe, expect, it, vi } from "vitest";
import { inputToIso, isoToInput, tehranToday, validIso } from "@/lib/calendar";
import { faDate, faDateTime } from "@/lib/fa";

describe("civil calendar boundary", () => {
  it.each([
    ["۱۴۰۴/۰۱/۰۱", "2025-03-21"],
    ["1403/12/30", "2025-03-20"],
    ["1405/07/25", "2026-10-17"],
    ["١٤٠٥/٠٧/٢٥", "2026-10-17"],
  ])("round-trips %s without timezone conversion", (jalali, iso) => {
    expect(inputToIso(jalali, "jalali")).toBe(iso);
    expect(inputToIso(isoToInput(iso, "jalali"), "jalali")).toBe(iso);
    expect(inputToIso(isoToInput(iso, "gregorian"), "gregorian")).toBe(iso);
  });
  it.each(["1404/12/30", "1405/07/31", "1405/13/01", "1405/00/10", "bad", "1405/01/00"])(
    "rejects invalid Jalali %s",
    (raw) => {
      expect(inputToIso(raw, "jalali")).toBeNull();
    },
  );
  it.each(["2026/02/29", "2026/04/31", "0000/01/01", "2026/13/01", "2026/01/00"])(
    "rejects invalid Gregorian %s",
    (raw) => expect(inputToIso(raw, "gregorian")).toBeNull(),
  );
  it("checks Gregorian leap years and canonical storage", () => {
    expect(inputToIso("۲۰۲۴/۲/۲۹", "gregorian")).toBe("2024-02-29");
    expect(validIso("2026-2-01")).toBe(false);
    expect(faDate("2026-02-30")).toBe("—");
    expect(faDate("2026-10-17", "gregorian")).toBe("۲۰۲۶/۱۰/۱۷");
  });
  it("distinguishes instants from date-only across Tehran midnight", () => {
    expect(tehranToday(new Date("2026-10-16T20:29:59Z"))).toBe("2026-10-16");
    expect(tehranToday(new Date("2026-10-16T20:30:00Z"))).toBe("2026-10-17");
    expect(faDate("2026-10-16")).toBe("۱۴۰۵/۰۷/۲۴");
    expect(faDate("2026-10-16T20:30:00Z")).toBe("۱۴۰۵/۰۷/۲۵");
    expect(faDateTime("2026-10-16T20:30:00Z")).toBe("۱۴۰۵/۰۷/۲۵ — ۰۰:۰۰");
    expect(faDate("2026-10-17T00:00:00")).toBe("—");
  });
  it("today uses the frozen Tehran clock", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-16T21:00:00Z"));
    try {
      expect(tehranToday()).toBe("2026-10-17");
    } finally {
      vi.useRealTimers();
    }
  });
});

it.each(["UTC", "America/Los_Angeles", "Pacific/Kiritimati"])(
  "is independent of process/browser zone %s",
  (zone) => {
    const before = process.env.TZ;
    process.env.TZ = zone;
    try {
      expect(tehranToday(new Date("2026-10-16T22:00:00Z"))).toBe("2026-10-17");
      expect(faDate("2026-10-17")).toBe("۱۴۰۵/۰۷/۲۵");
      expect(faDateTime("2026-10-16T22:00:00Z", "gregorian")).toBe("۲۰۲۶/۱۰/۱۷ — ۰۱:۳۰");
    } finally {
      if (before === undefined) delete process.env.TZ;
      else process.env.TZ = before;
    }
  },
);
