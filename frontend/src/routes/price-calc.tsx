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
  ["bufferPercent", "بافر ریسک و مرجوعی (٪)", "B35"],
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
  const setFlag = (key: "applyPrinterPower" | "applyNylon", on: boolean): void =>
    setConstants((c) => ({ ...c, [key]: on }));

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
        همهٔ فرمول‌ها عیناً از فایل <span className="num">قیمت نهایی.xlsx</span> برداشته شده‌اند؛
        شمارهٔ سلول هر ردیف کنار آن نوشته شده تا بتوانید با اکسل تطبیق دهید. نمونهٔ خود فایل (۲۴۰
        گرم، ۱۰ ساعت، تیراژ ۱) باید بدهد <span className="num">{SHEET_EXPECTED.plain}</span> تومان
        (ساده) و <span className="num">{SHEET_EXPECTED.chain}</span> تومان (زنجیردار).
      </p>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">مشخصات محصول</CardTitle>
            <button
              type="button"
              className="text-xs text-primary underline-offset-2 hover:underline"
              onClick={() => setInputs(SHEET_EXAMPLE_INPUTS)}
            >
              مقادیر نمونهٔ اکسل
            </button>
          </CardHeader>
          <CardContent className="space-y-3">
            <div>
              <Label>
                وزن محصول (گرم) <span className="text-[0.7em] text-muted-foreground">B13</span>
              </Label>
              <Input
                className="num"
                data-testid="input-weight"
                value={String(inputs.weightG)}
                onChange={(e) => setInputs((i) => ({ ...i, weightG: e.target.value }))}
              />
            </div>
            <div>
              <Label>
                مدت زمان پرینت (ساعت){" "}
                <span className="text-[0.7em] text-muted-foreground">B14</span>
              </Label>
              <Input
                className="num"
                data-testid="input-hours"
                value={String(inputs.printHours)}
                onChange={(e) => setInputs((i) => ({ ...i, printHours: e.target.value }))}
              />
            </div>
            <div>
              <Label>
                تیراژ (تعداد) <span className="text-[0.7em] text-muted-foreground">B15</span>
              </Label>
              <Input
                className="num"
                data-testid="input-qty"
                value={String(inputs.quantity)}
                onChange={(e) => setInputs((i) => ({ ...i, quantity: e.target.value }))}
              />
            </div>
            <div>
              <Label>کانال فروش</Label>
              <select
                className="flex h-9 w-full rounded-md border border-input bg-background px-2 text-sm text-foreground"
                value={inputs.channel}
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
                <Label className="text-xs">
                  {label} <span className="text-[0.9em] text-muted-foreground">{cell}</span>
                </Label>
                <Input
                  className="num h-8"
                  data-testid={`const-${key}`}
                  value={String(constants[key])}
                  onChange={(e) => setConst(key, e.target.value)}
                />
              </div>
            ))}
            <div className="space-y-2 border-t pt-3">
              <Label className="flex items-center gap-2 text-xs font-normal">
                <input
                  type="checkbox"
                  data-testid="toggle-power"
                  checked={constants.applyPrinterPower}
                  onChange={(e) => setFlag("applyPrinterPower", e.target.checked)}
                />
                احتساب توان پرینتر در هزینهٔ برق (B2 × B14 × B4) — در اکسل اعمال نشده
              </Label>
              <Label className="flex items-center gap-2 text-xs font-normal">
                <input
                  type="checkbox"
                  data-testid="toggle-nylon"
                  checked={constants.applyNylon}
                  onChange={(e) => setFlag("applyNylon", e.target.checked)}
                />
                افزودن نایلون بسته‌بندی (B8) به بستهٔ ارسال — در اکسل اعمال نشده
              </Label>
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
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-muted-foreground">
                    <th className="py-2 text-start font-medium">ردیف</th>
                    <th className="py-2 text-start font-medium">سلول</th>
                    <th className="py-2 text-start font-medium">ساده</th>
                    <th className="py-2 text-start font-medium">زنجیردار</th>
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
                      <td className="py-2">
                        <Money value={chain[row.key].toFixed(4)} currency="TOMAN" hideCurrency />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="pt-3 text-xs text-muted-foreground">
                «بافر ریسک» و «کمیسیون» فقط در کانال بازارگاه محاسبه می‌شوند؛ در فروش مستقیم کمیسیون
                صفر است. هزینهٔ ارسال محموله بین تعداد سفارش تقسیم می‌شود (B22 = B21 ÷ B15).
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
