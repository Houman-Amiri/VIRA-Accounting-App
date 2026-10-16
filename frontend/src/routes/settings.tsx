import { CalendarSettingsCard } from "@/components/calendar-settings";
import * as React from "react";
import { Link } from "@tanstack/react-router";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { DEFAULT_CONSTANTS, parseNum } from "@/lib/priceCalc";
import {
  PRICING_FIELDS,
  usePricingSettings,
  useSavePricingSettings,
  type EditableConstant,
} from "@/lib/pricing-settings";

export function SettingsPage(): React.JSX.Element {
  const query = usePricingSettings();
  const save = useSavePricingSettings();
  const [draft, setDraft] = React.useState<Partial<Record<EditableConstant, string>>>({});
  const [error, setError] = React.useState<string | null>(null);
  const [saved, setSaved] = React.useState(false);
  // Hold the revision from when editing began; do not overwrite another user's save.
  const [revision, setRevision] = React.useState<number | null>(null);

  const edit = (key: EditableConstant, value: string) => {
    setRevision((current) => current ?? query.data?.version_id ?? null);
    setDraft((current) => ({ ...current, [key]: value }));
    setSaved(false);
    setError(null);
  };
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!query.data) return;
    setError(null);
    setSaved(false);
    try {
      const body = Object.fromEntries(
        PRICING_FIELDS.map(([key]) => {
          const raw = draft[key] ?? query.data[key];
          if (!String(raw).trim()) throw new Error("همهٔ ثابت‌ها را وارد کنید.");
          const amount = parseNum(raw);
          const max = key === "profitFactor" ? "1000" : "1000000000000";
          if (amount.isNegative() || amount.gt(max) || amount.decimalPlaces() > 4) {
            throw new Error("ثابت‌ها باید نامنفی، در محدودهٔ مجاز و حداکثر چهار رقم اعشار باشند.");
          }
          return [key, amount.toFixed(4)];
        }),
      ) as Record<EditableConstant, string>;
      await save.mutateAsync({ ...body, version_id: revision ?? query.data.version_id });
      setDraft({});
      setRevision(null);
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "ذخیرهٔ ثابت‌ها ناموفق بود.");
    }
  }
  return (
    <div className="mx-auto max-w-3xl space-y-4" dir="rtl">
      <h1 className="text-xl font-bold">تنظیمات</h1>
      <nav aria-label="بخش‌های تنظیمات" className="flex flex-wrap gap-3 text-sm">
        <a href="#calendar-settings" className="text-primary">
          تاریخ و تقویم
        </a>
        <a href="#pricing-constants" className="font-semibold text-primary">
          ثابت‌های قیمت‌گذاری
        </a>
        <Link to="/system" className="text-muted-foreground hover:text-foreground">
          سیستم و عملیات
        </Link>
      </nav>
      <CalendarSettingsCard />
      <Card id="pricing-constants">
        <CardHeader>
          <CardTitle>ثابت‌های قیمت‌گذاری</CardTitle>
        </CardHeader>
        <CardContent>
          {query.isPending ? (
            <p role="status">در حال دریافت ثابت‌ها…</p>
          ) : query.error ? (
            <div role="alert" className="space-y-2 text-destructive">
              <p>دریافت ثابت‌ها ناموفق بود؛ دوباره تلاش کنید.</p>
              <Button variant="outline" onClick={() => void query.refetch()}>
                تلاش مجدد
              </Button>
            </div>
          ) : query.data ? (
            <form onSubmit={submit} className="space-y-4">
              <p className="text-sm text-muted-foreground">
                تغییرات ذخیره‌شده در محاسبات جدید قیمت‌گذاری، سفارش و تولید استفاده می‌شوند؛
                قیمت‌های قبلی تغییر نمی‌کنند.
              </p>
              <fieldset disabled={save.isPending} className="grid gap-4 sm:grid-cols-2">
                {PRICING_FIELDS.map(([key, label]) => (
                  <div key={key} className="space-y-1">
                    <Label htmlFor={`pricing-${key}`}>{label}</Label>
                    <Input
                      id={`pricing-${key}`}
                      data-testid={`const-${key}`}
                      className="num"
                      inputMode="decimal"
                      required
                      value={draft[key] ?? query.data[key]}
                      onChange={(e) => edit(key, e.target.value)}
                    />
                  </div>
                ))}
              </fieldset>
              {error && (
                <p role="alert" className="text-sm text-destructive">
                  {error}
                </p>
              )}
              {saved && (
                <p role="status" className="text-sm text-positive">
                  ثابت‌های قیمت‌گذاری ذخیره شدند.
                </p>
              )}
              <div className="flex flex-wrap gap-2">
                <Button type="submit" disabled={save.isPending}>
                  {save.isPending ? "در حال ذخیره…" : "ذخیرهٔ تغییرات"}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  disabled={save.isPending}
                  onClick={() => {
                    setRevision((current) => current ?? query.data.version_id);
                    setDraft(
                      Object.fromEntries(
                        PRICING_FIELDS.map(([key]) => [key, String(DEFAULT_CONSTANTS[key])]),
                      ),
                    );
                    setSaved(false);
                    setError(null);
                  }}
                >
                  مقادیر پیش‌فرض
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  disabled={save.isPending}
                  onClick={() => {
                    setDraft({});
                    setRevision(null);
                    setError(null);
                    setSaved(false);
                    void query.refetch();
                  }}
                >
                  لغو و بارگذاری مجدد
                </Button>
              </div>
            </form>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
