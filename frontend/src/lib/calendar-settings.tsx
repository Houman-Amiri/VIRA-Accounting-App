import { z } from "zod";
/** Shared installation policy; the server/SQLite, not localStorage, is authoritative. */
import { createContext, useContext, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, parseError } from "@/api/client";
import type { Calendar } from "./calendar";

const CalendarReadSchema = z.object({
  calendar: z.enum(["jalali", "gregorian"]),
  version_id: z.number().int().nonnegative(),
  timezone: z.literal("Asia/Tehran"),
  scope: z.literal("installation"),
});
export const decodeCalendarSettings = (data: unknown) => CalendarReadSchema.parse(data);
export const CalendarContext = createContext<{
  calendar: Calendar;
  ready: boolean;
  error: string | null;
}>({ calendar: "jalali", ready: false, error: "تنظیم تقویم دریافت نشده است." });
export const useCalendar = () => useContext(CalendarContext);
export function useCalendarSettings(enabled = true) {
  return useQuery({
    queryKey: ["calendar-settings"],
    enabled,
    retry: false,
    refetchInterval: 30_000,
    queryFn: async () => {
      const res = await api.GET("/api/v1/settings/calendar");
      if (res.error) throw await parseError(res.response);
      if (!res.data) throw new Error("دریافت تنظیم تقویم ناموفق بود.");
      return decodeCalendarSettings(res.data);
    },
  });
}
export function CalendarProvider({ children, enabled }: { children: ReactNode; enabled: boolean }) {
  const query = useCalendarSettings(enabled);
  return (
    <CalendarContext.Provider
      value={{
        calendar: query.data?.calendar ?? "jalali",
        ready: !!query.data && !query.error,
        error: query.error
          ? "دریافت تنظیم تقویم ناموفق بود؛ در تنظیمات دوباره بارگذاری کنید."
          : null,
      }}
    >
      {enabled && query.error && (
        <p role="alert" className="text-destructive">
          دریافت تنظیم تقویم ناموفق است؛ ورود تاریخ تا دریافت تنظیم معتبر متوقف است.
        </p>
      )}
      {children}
    </CalendarContext.Provider>
  );
}
