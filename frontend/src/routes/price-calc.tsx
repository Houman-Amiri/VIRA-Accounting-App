/**
 * ماشین‌حساب قیمت‌گذاری — صفحهٔ «قیمت گذاری».
 *
 * The table mirrors `قیمت نهایی.xlsx` row by row: the same labels, the same
 * order and amounts (ساده / زنجیردار), without exposing worksheet addresses
 * or formulas in the report. Internal references remain in the oracle. All math in
 * `@/lib/priceCalc` (decimal.js, sheet-exact).
 */
import * as React from "react";
import {
  BREAKDOWN_ROWS,
  computePrice,
  SALE_ROWS,
  SHEET_EXAMPLE_INPUTS,
  type PriceBreakdown,
  type PriceInputs,
} from "@/lib/priceCalc";
import { Money } from "@/components/money";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/cn";
import { Link } from "@tanstack/react-router";
import { pricingConstants, usePricingSettings } from "@/lib/pricing-settings";

// Presentation only: keep the workbook formulas and numeric values unchanged.
const REPORT_ROW_HIGHLIGHTS: Partial<Record<keyof PriceBreakdown, string>> = {
  productionTotal: "bg-green-100 font-semibold dark:bg-green-900/40",
  unitSalePrice: "bg-blue-100 font-semibold dark:bg-blue-900/40",
  unitFinalPrice: "bg-red-100 font-semibold dark:bg-red-900/40",
};

export function PriceCalcPage(): React.JSX.Element {
  const settings = usePricingSettings();
  const constants = React.useMemo(
    () => (settings.data ? pricingConstants(settings.data) : null),
    [settings.data],
  );
  const [inputs, setInputs] = React.useState<PriceInputs>(SHEET_EXAMPLE_INPUTS);

  const plain = React.useMemo<PriceBreakdown | null>(() => {
    if (!constants) return null;
    try {
      return computePrice({ ...inputs, variant: "plain" }, constants);
    } catch {
      return null;
    }
  }, [inputs, constants]);

  const chain = React.useMemo<PriceBreakdown | null>(() => {
    if (!constants) return null;
    try {
      return computePrice({ ...inputs, variant: "chain" }, constants);
    } catch {
      return null;
    }
  }, [inputs, constants]);

  const rows = [...BREAKDOWN_ROWS, ...SALE_ROWS];

  if (settings.isPending) return <p role="status">در حال دریافت ثابت‌های قیمت‌گذاری…</p>;
  if (settings.error)
    return (
      <div role="alert" className="space-y-2 text-destructive">
        <p>دریافت ثابت‌های قیمت‌گذاری ناموفق بود؛ محاسبه با مقدارهای قدیمی انجام نمی‌شود.</p>
        <button onClick={() => void settings.refetch()} className="underline">
          تلاش مجدد
        </button>
      </div>
    );

  return (
    <div className="mx-auto max-w-5xl space-y-4" dir="rtl">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-bold">ماشین‌حساب قیمت‌گذاری</h1>
        {plain && (
          <Badge variant="success" data-testid="final-badge">
            قیمت نهایی هر عدد: <Money value={plain.unitFinalPrice.toFixed(4)} currency="TOMAN" />
          </Badge>
        )}
      </div>

      <Link to="/settings" className="inline-block text-sm text-primary hover:underline">
        تغییر ثابت‌ها در تنظیمات
      </Link>

      <div className="space-y-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">مشخصات محصول</CardTitle>
            <button
              type="button"
              className="text-xs text-primary underline-offset-2 hover:underline"
              onClick={() => {
                setInputs(SHEET_EXAMPLE_INPUTS);
              }}
            >
              بازنشانی ورودی‌ها
            </button>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-2">
            <div>
              <Label htmlFor="price-weight">وزن محصول (گرم)</Label>
              <Input
                className="num"
                id="price-weight"
                data-testid="input-weight"
                value={String(inputs.weightG)}
                onChange={(e) => setInputs((i) => ({ ...i, weightG: e.target.value }))}
              />
            </div>
            <div>
              <Label htmlFor="price-hours">مدت زمان پرینت (ساعت)</Label>
              <Input
                className="num"
                id="price-hours"
                data-testid="input-hours"
                value={String(inputs.printHours)}
                onChange={(e) => setInputs((i) => ({ ...i, printHours: e.target.value }))}
              />
            </div>
            <div>
              <Label htmlFor="price-qty">تیراژ (تعداد)</Label>
              <Input
                className="num"
                id="price-qty"
                data-testid="input-qty"
                value={String(inputs.quantity)}
                onChange={(e) => setInputs((i) => ({ ...i, quantity: e.target.value }))}
              />
            </div>
            <div>
              <Label htmlFor="price-channel">کانال فروش</Label>
              <select
                className="flex h-9 w-full rounded-md border border-input bg-background px-2 text-sm text-foreground"
                value={inputs.channel}
                id="price-channel"
                data-testid="select-channel"
                onChange={(e) =>
                  setInputs((i) => ({ ...i, channel: e.target.value as PriceInputs["channel"] }))
                }
              >
                <option value="marketplace">بازارگاه (با کمیسیون)</option>
                <option value="direct">فروش مستقیم (بدون کمیسیون)</option>
              </select>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">گزارش بهای تمام‌شده و قیمت نهایی</CardTitle>
        </CardHeader>
        <CardContent>
          {plain && chain ? (
            <div
              className="overflow-x-auto focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
              role="region"
              aria-label="جدول قیمت‌گذاری؛ قابل پیمایش افقی"
              tabIndex={0}
            >
              <table className="w-full text-xs sm:text-sm" aria-label="گزارش قیمت‌گذاری">
                <thead>
                  <tr className="border-b text-muted-foreground">
                    <th scope="col" className="py-2 text-start font-medium">
                      شرح ردیف
                    </th>
                    <th scope="col" className="py-2 text-start font-medium">
                      ساده (تومان)
                    </th>
                    <th scope="col" className="py-2 text-start font-medium">
                      زنجیردار (تومان)
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr
                      key={row.key}
                      className={cn(
                        "border-t",
                        REPORT_ROW_HIGHLIGHTS[row.key] ??
                          (row.strong ? "bg-muted/40 font-semibold" : undefined),
                      )}
                      data-testid={`row-${row.key}`}
                    >
                      <td className="py-2">
                        {row.key === "batchFinalPrice" ? "قیمت نهایی کل" : row.label}
                      </td>
                      <td className="py-2">
                        <Money value={plain[row.key].toFixed(4)} currency="TOMAN" hideCurrency />
                      </td>
                      <td className="py-2">
                        {row.plainOnly ? (
                          "—"
                        ) : (
                          <Money value={chain[row.key].toFixed(4)} currency="TOMAN" hideCurrency />
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="p-6 text-center text-destructive">
              ورودی نامعتبر است — مقدارها باید عدد باشند (تیراژ بزرگ‌تر از صفر).
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
