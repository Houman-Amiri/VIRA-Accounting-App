/**
 * ماشین‌حساب قیمت‌گذاری — صفحهٔ «قیمت گذاری».
 *
 * The table mirrors `قیمت نهایی.xlsx` row by row: the same labels, the same
 * order, and the same B/E columns (ساده / زنجیردار) — so every number can be
 * checked against the sheet cell printed next to it. All math in
 * `@/lib/priceCalc` (decimal.js, sheet-exact).
 */
import * as React from "react";
import {
  BREAKDOWN_ROWS,
  computePrice,
  DEFAULT_CONSTANTS,
  SALE_ROWS,
  SHEET_EXPECTED,
  SHEET_EXAMPLE_INPUTS,
  type PriceBreakdown,
  type PriceConstants,
  type PriceInputs,
} from "@/lib/priceCalc";
import { Money } from "@/components/money";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const CONSTANT_FIELDS: ReadonlyArray<[keyof PriceConstants, string, string]> = [
  ["filamentPerGram", "قیمت هر گرم فیلامنت", "B3"],
  ["electricityPerKwh", "قیمت هر کیلووات برق", "B4"],
  ["depreciationPerHour", "استهلاک پرینتر در هر ساعت", "B5"],
  ["profitFactor", "ضریب سود (×)", "B6"],
  ["commissionPercent", "کمیسیون بازارگاه (٪)", "B7"],
  ["chainPerUnit", "حلقه و زنجیر", "B9"],
  ["shipmentPerBatch", "هزینه ارسال محموله", "B10"],
  ["labelPerUnit", "هزینه لیبل", "B23"],
  ["printerPowerKw", "توان مصرفی پرینتر (کیلووات)", "B2"],
  ["nylonPerUnit", "نایلون بسته‌بندی", "B8"],
];

export function PriceCalcPage(): React.JSX.Element {
  const [constants, setConstants] = React.useState<PriceConstants>(DEFAULT_CONSTANTS);
  const [inputs, setInputs] = React.useState<PriceInputs>(SHEET_EXAMPLE_INPUTS);

  const plain = React.useMemo<PriceBreakdown | null>(() => {
    try {
      return computePrice({ ...inputs, variant: "plain" }, constants);
    } catch {
      return null;
    }
  }, [inputs, constants]);

  const chain = React.useMemo<PriceBreakdown | null>(() => {
    try {
      return computePrice({ ...inputs, variant: "chain" }, constants);
    } catch {
      return null;
    }
  }, [inputs, constants]);

  const setConst = (key: keyof PriceConstants, raw: string): void =>
    setConstants((c) => ({ ...c, [key]: raw }));

  const rows = [...BREAKDOWN_ROWS, ...SALE_ROWS];

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

      <p className="text-xs text-muted-foreground">
        در کانال بازارگاه، فرمول‌ها عیناً از فایل <span className="num">قیمت نهایی.xlsx</span>{" "}
        برداشته شده‌اند؛ شمارهٔ سلول هر ردیف کنار آن نوشته شده تا بتوانید با اکسل تطبیق دهید. نمونهٔ
        خود فایل (۲۴۰ گرم، ۱۰ ساعت، تیراژ ۱) باید بدهد{" "}
        <span className="num">{SHEET_EXPECTED.plain}</span> تومان (ساده) و{" "}
        <span className="num">{SHEET_EXPECTED.chain}</span> تومان (زنجیردار).
      </p>

      <p
        className="rounded-md border border-border bg-muted/30 p-3 text-xs"
        data-testid="sheet-policy"
      >
        مطابق خود اکسل، وزن و زمان بدون ضرب خودکار در تیراژ وارد فرمول می‌شوند؛ قیمت فروش کل بر
        تیراژ تقسیم می‌شود. کمیسیون هر دو مدل از B31 (مدل ساده، ۱۳٫۱٪) گرفته می‌شود و بافر هر دو مدل
        از B34 ساده با نرخ ۱۰٪ گرفته می‌شود. ثابت‌های B2، B7 و B8 در فرمول‌های فایل استفاده
        نشده‌اند.
      </p>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">مشخصات محصول</CardTitle>
            <button
              type="button"
              className="text-xs text-primary underline-offset-2 hover:underline"
              onClick={() => {
                setInputs(SHEET_EXAMPLE_INPUTS);
                setConstants(DEFAULT_CONSTANTS);
              }}
            >
              مقادیر نمونهٔ اکسل
            </button>
          </CardHeader>
          <CardContent className="space-y-3">
            <div>
              <Label htmlFor="price-weight">
                وزن محصول (گرم) <span className="text-[0.7em] text-muted-foreground">B13</span>
              </Label>
              <Input
                className="num"
                id="price-weight"
                data-testid="input-weight"
                value={String(inputs.weightG)}
                onChange={(e) => setInputs((i) => ({ ...i, weightG: e.target.value }))}
              />
            </div>
            <div>
              <Label htmlFor="price-hours">
                مدت زمان پرینت (ساعت){" "}
                <span className="text-[0.7em] text-muted-foreground">B14</span>
              </Label>
              <Input
                className="num"
                id="price-hours"
                data-testid="input-hours"
                value={String(inputs.printHours)}
                onChange={(e) => setInputs((i) => ({ ...i, printHours: e.target.value }))}
              />
            </div>
            <div>
              <Label htmlFor="price-qty">
                تیراژ (تعداد) <span className="text-[0.7em] text-muted-foreground">B15</span>
              </Label>
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

        <Card>
          <CardHeader>
            <CardTitle className="text-base">ثابت‌ها</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {CONSTANT_FIELDS.map(([key, label, cell]) => (
              <div key={key} className="grid grid-cols-2 items-center gap-2">
                <Label htmlFor={`price-const-${key}`} className="text-xs">
                  {label} <span className="text-[0.9em] text-muted-foreground">{cell}</span>
                </Label>
                <Input
                  className="num h-8"
                  id={`price-const-${key}`}
                  readOnly={["printerPowerKw", "commissionPercent", "nylonPerUnit"].includes(key)}
                  aria-description={
                    ["printerPowerKw", "commissionPercent", "nylonPerUnit"].includes(key)
                      ? "در فرمول‌های اکسل استفاده نشده است؛ فقط جهت نمایش"
                      : undefined
                  }
                  data-testid={`const-${key}`}
                  value={String(constants[key])}
                  onChange={(e) => setConst(key, e.target.value)}
                />
              </div>
            ))}
            <p className="border-t pt-3 text-xs text-muted-foreground">
              توان پرینتر، کمیسیون B7 و نایلون صرفاً ثابت‌های تعریف‌شدهٔ فایل هستند و اینجا فقط
              خواندنی‌اند. فرمول B31 نرخ ثابت ۱۳٫۱٪ و فرمول نهایی بافر ثابت ۱۰٪ دارد.
            </p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">گزارش بهای تمام‌شده و قیمت نهایی</CardTitle>
        </CardHeader>
        <CardContent>
          {plain && chain ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-muted-foreground">
                    <th className="py-2 text-start font-medium">ردیف</th>
                    <th className="py-2 text-start font-medium">سلول ساده</th>
                    <th className="py-2 text-start font-medium">ساده (تومان)</th>
                    <th className="py-2 text-start font-medium">سلول زنجیردار</th>
                    <th className="py-2 text-start font-medium">زنجیردار (تومان)</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr
                      key={row.key}
                      className={row.strong ? "border-t bg-muted/40 font-semibold" : "border-t"}
                      data-testid={`row-${row.key}`}
                    >
                      <td className="py-2">{row.label}</td>
                      <td className="num py-2 text-xs text-muted-foreground">{row.cell}</td>
                      <td className="py-2">
                        <Money value={plain[row.key].toFixed(4)} currency="TOMAN" hideCurrency />
                      </td>
                      <td className="num py-2 text-xs text-muted-foreground">
                        {row.plainOnly ? "—" : (row.chainCell ?? row.cell)}
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
              <p className="pt-3 text-xs text-muted-foreground">
                فروش مستقیم، حالت تکمیلی خارج از فایل اکسل است: فقط کمیسیون صفر می‌شود و بافر ۱۰٪
                باقی می‌ماند. ردیف B32 فقط در ستون سادهٔ فایل وجود دارد. هزینهٔ ارسال محموله بین
                تعداد سفارش تقسیم می‌شود (B22 = B21 ÷ B15).
              </p>
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
