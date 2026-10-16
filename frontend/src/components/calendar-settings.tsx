import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, parseError } from "@/api/client";
import { decodeCalendarSettings, useCalendarSettings } from "@/lib/calendar-settings";
import type { Calendar } from "@/lib/calendar";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { Button } from "./ui/button";
import { Label } from "./ui/label";

export function CalendarSettingsCard() {
  const query = useCalendarSettings();
  const cache = useQueryClient();
  const [draft, setDraft] = useState<{ calendar: Calendar; version_id: number } | null>(null);
  const save = useMutation({
    mutationFn: async () => {
      if (!draft) throw new Error("ابتدا تقویم را انتخاب کنید.");
      const res = await api.PUT("/api/v1/settings/calendar", { body: draft });
      if (res.error) throw await parseError(res.response);
      if (!res.data) throw new Error("ذخیرهٔ تقویم ناموفق بود.");
      return decodeCalendarSettings(res.data);
    },
    onSuccess: (data) => {
      cache.setQueryData(["calendar-settings"], data);
      setDraft(null);
    },
  });
  return (
    <Card id="calendar-settings">
      <CardHeader>
        <CardTitle>تاریخ و تقویم</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-muted-foreground">
          این تنظیم در دیتابیسِ همین نصب برای همهٔ کاربران ذخیره می‌شود؛ فقط مالک و دفتردار
          می‌توانند تغییرش دهند. زبان فارسی و RTL ثابت‌اند. امروز و ساعت‌ها بر اساس Asia/Tehran
          هستند؛ روزِ اسناد و سال مالی تغییر نمی‌کنند.
        </p>
        {query.isPending ? (
          <p role="status">دریافت تنظیم تقویم…</p>
        ) : query.error ? (
          <p role="alert">دریافت تنظیم تقویم ناموفق بود.</p>
        ) : (
          query.data && (
            <>
              <Label htmlFor="calendar-choice">تقویم نمایش و ورود تاریخ</Label>
              <select
                id="calendar-choice"
                data-testid="calendar-choice"
                className="h-9 rounded-md border border-input bg-background px-2 text-foreground"
                value={draft?.calendar ?? query.data.calendar}
                disabled={save.isPending}
                onChange={(e) => {
                  setDraft({
                    calendar: e.target.value as Calendar,
                    version_id: draft?.version_id ?? query.data!.version_id,
                  });
                  save.reset();
                }}
              >
                <option value="jalali">شمسی</option>
                <option value="gregorian">میلادی</option>
              </select>
              <Button
                type="button"
                data-testid="save-calendar"
                disabled={!draft || save.isPending}
                onClick={() => save.mutate()}
              >
                ذخیرهٔ تقویم
              </Button>
            </>
          )
        )}
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            setDraft(null);
            save.reset();
            void query.refetch();
          }}
        >
          بارگذاری مجدد تقویم
        </Button>
        {save.isSuccess && <p role="status">تقویم ذخیره شد.</p>}
        {save.error && (
          <p role="alert" className="text-destructive">
            {save.error.message}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
