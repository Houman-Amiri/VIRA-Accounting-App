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
  applyCustomConstants,
  applyVariables,
  computePrice,
  parseNum,
  SALE_ROWS,
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
import {
  pricingConstants,
  useCustomConstants,
  usePricingSettings,
  useVariables,
  VARIABLE_BASIS_LABEL,
} from "@/lib/pricing-settings";
import { faNumber } from "@/lib/fa";

/**
 * Empty by default (item 8 of the owner's change list): the calculator never
 * shows a price the user did not ask for, and it keeps no drafts — returning to
 * the page shows empty inputs again.
 */
const EMPTY_INPUTS: PriceInputs = {
  weightG: "",
  printHours: "",
  quantity: "",
  variant: "plain",
};

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
  const customs = useCustomConstants();
  const variableQuery = useVariables();
  const [inputs, setInputs] = React.useState<PriceInputs>(EMPTY_INPUTS);
  // Values typed for *this* calculation; the saved value is only the default.
  const [variableValues, setVariableValues] = React.useState<Record<string, string>>({});
  // «۲ محموله × ۱۵۰٬۰۰۰»: how many times each variable applies to this order.
  const [variableCounts, setVariableCounts] = React.useState<Record<string, string>>({});

  // «محاسبه فقط پس از ورود»: nothing is computed until weight, time and run
  // size are filled in by the user.
  const filled = [inputs.weightG, inputs.printHours, inputs.quantity].every(
    (value) => String(value).trim() !== "",
  );

  const plain = React.useMemo<PriceBreakdown | null>(() => {
    if (!constants || !filled) return null;
    try {
      // مرجع بازارگاه: همین اعداد ردیف‌های کمیسیون را پر می‌کنند؛ قیمت نهایی
      // این صفحه از «قیمت فروش هر عدد محصول» ساخته می‌شود، نه از این‌ها.
      return computePrice({ ...inputs, variant: "plain", channel: "marketplace" }, constants);
    } catch {
      return null;
    }
  }, [inputs, constants, filled]);

  const chain = React.useMemo<PriceBreakdown | null>(() => {
    if (!constants || !filled) return null;
    try {
      return computePrice({ ...inputs, variant: "chain", channel: "marketplace" }, constants);
    } catch {
      return null;
    }
  }, [inputs, constants, filled]);

  // The owner's own constants sit on top of the sheet-exact breakdown; the
  // table above keeps showing the workbook's numbers untouched.
  const added = React.useMemo(() => {
    if (!plain) return null;
    try {
      return applyCustomConstants(plain, customs.data ?? [], inputs.quantity);
    } catch {
      return null;
    }
  }, [plain, customs.data, inputs.quantity]);

  const activeVariables = React.useMemo(
    () =>
      (variableQuery.data ?? [])
        .filter((variable) => variable.is_active)
        .map((variable) => ({
          ...variable,
          value: variableValues[variable.id] ?? variable.value,
          count: variableCounts[variable.id] ?? "1",
        })),
    [variableQuery.data, variableValues, variableCounts],
  );

  const variablesApplied = React.useMemo(() => {
    if (!plain) return null;
    try {
      return applyVariables(plain, activeVariables, inputs.quantity);
    } catch {
      return null;
    }
  }, [plain, activeVariables, inputs.quantity]);

  // The app's final price hangs on one row only: «قیمت فروش هر عدد محصول»
  // (B29/E29). The marketplace rows below it stay on the page as a reference and
  // never move the number the owner actually sells at.
  const unitFinal = React.useMemo(
    () =>
      plain
        ? plain.unitSalePrice
            .plus(added ? added.perUnit : 0)
            .plus(variablesApplied ? variablesApplied.perUnit : 0)
        : null,
    [plain, added, variablesApplied],
  );
  const orderTotal = React.useMemo(() => {
    if (!unitFinal) return null;
    try {
      const quantity = parseNum(inputs.quantity);
      return unitFinal.times(quantity).plus(variablesApplied ? variablesApplied.oneTime : 0);
    } catch {
      return null;
    }
  }, [unitFinal, inputs.quantity, variablesApplied]);

  const rows = [...BREAKDOWN_ROWS, ...SALE_ROWS];
  // از «کمیسیون بازارگاه» به بعد، اعداد وابسته به بازارگاه‌اند و فقط مرجع‌اند.
  const referenceStart = rows.findIndex((row) => row.key === "unitCommission");

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
            قیمت نهایی هر عدد:{" "}
            <Money value={(unitFinal ?? plain.unitSalePrice).toFixed(4)} currency="TOMAN" />
          </Badge>
        )}
      </div>

      <Link to="/pricing-settings" className="inline-block text-sm text-primary hover:underline">
        تغییر ثابت‌های قیمت‌گذاری
      </Link>

      <div className="space-y-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">مشخصات محصول</CardTitle>
            <button
              type="button"
              className="text-xs text-primary underline-offset-2 hover:underline"
              onClick={() => {
                setInputs(EMPTY_INPUTS);
              }}
            >
              پاک کردن ورودی‌ها
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
                placeholder="مثلاً ۲۴۰"
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
                placeholder="مثلاً ۱۰"
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
                placeholder="مثلاً ۱"
                onChange={(e) => setInputs((i) => ({ ...i, quantity: e.target.value }))}
              />
            </div>
            {/* متغیرهای تنظیمات قیمت‌گذاری، کنار بقیهٔ مشخصات محصول. */}
            {activeVariables.map((variable) => (
              <div key={variable.id} data-testid={`variable-field-${variable.id}`}>
                <Label htmlFor={`price-variable-${variable.id}`}>
                  {variable.name}
                  <span className="ms-1 text-[10px] font-normal text-muted-foreground">
                    ({VARIABLE_BASIS_LABEL[variable.basis]})
                  </span>
                </Label>
                <div className="flex items-center gap-1">
                  <Input
                    aria-label={`مقدار ${variable.name}`}
                    data-testid={`variable-input-${variable.id}`}
                    className="num"
                    id={`price-variable-${variable.id}`}
                    inputMode="decimal"
                    value={variable.value}
                    onChange={(event) =>
                      setVariableValues((current) => ({
                        ...current,
                        [variable.id]: event.target.value,
                      }))
                    }
                  />
                  <span className="text-[11px] text-muted-foreground">×</span>
                  <Input
                    aria-label={`تعداد ${variable.name}`}
                    title="چند بار در این سفارش حساب شود (پیش‌فرض ۱)"
                    data-testid={`variable-count-${variable.id}`}
                    className="num w-16"
                    inputMode="numeric"
                    value={variableCounts[variable.id] ?? "1"}
                    onChange={(event) =>
                      setVariableCounts((current) => ({
                        ...current,
                        [variable.id]: event.target.value,
                      }))
                    }
                  />
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">گزارش بهای تمام‌شده و قیمت نهایی</CardTitle>
        </CardHeader>
        <CardContent>
          {plain && chain ? (
            <>
              <p
                className="pb-2 text-[11px] text-muted-foreground"
                data-testid="marketplace-reference"
              >
                ردیف‌های خاکستری پایین جدول «محاسبهٔ بازارگاه» با کمیسیون ۱۳٫۱٪ است و فقط مرجع است؛
                در قیمت نهایی اثری ندارد چون فروش مستقیم است.
              </p>
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
                    {rows.map((row, index) => (
                      <tr
                        key={row.key}
                        className={cn(
                          "border-t",
                          REPORT_ROW_HIGHLIGHTS[row.key] ??
                            (row.strong ? "bg-muted/40 font-semibold" : undefined),
                          index >= referenceStart && !REPORT_ROW_HIGHLIGHTS[row.key]
                            ? "text-muted-foreground"
                            : undefined,
                        )}
                        data-testid={`row-${row.key}`}
                      >
                        <td className="py-2 ps-1">
                          {row.key === "batchFinalPrice" ? "قیمت نهایی کل" : row.label}
                        </td>
                        <td className="py-2 ps-1">
                          <Money value={plain[row.key].toFixed(4)} currency="TOMAN" hideCurrency />
                        </td>
                        <td className="py-2 ps-1">
                          {row.plainOnly ? (
                            "—"
                          ) : (
                            <Money
                              value={chain[row.key].toFixed(4)}
                              currency="TOMAN"
                              hideCurrency
                            />
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : !filled ? (
            <p className="p-6 text-center text-muted-foreground" data-testid="price-empty">
              برای دیدن محاسبه، وزن محصول، مدت پرینت و تیراژ را وارد کنید.
            </p>
          ) : (
            <p className="p-6 text-center text-destructive">
              ورودی نامعتبر است — مقدارها باید عدد باشند (تیراژ بزرگ‌تر از صفر).
            </p>
          )}
        </CardContent>
      </Card>

      {activeVariables.length > 0 && (
        <Card data-testid="variable-lines">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">متغیرهای شما</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <p className="text-xs text-muted-foreground">
              مقدارها در «مشخصات محصول» کنار بقیهٔ ورودی‌ها وارد می‌شوند؛ این کادر فقط اثرشان را
              نشان می‌دهد و تنظیمات ذخیره‌شده را تغییر نمی‌دهد.
            </p>
            {activeVariables.map((variable) => {
              const line = variablesApplied?.lines.find((row) => row.name === variable.name);
              return (
                <div
                  key={variable.id}
                  className="flex items-center justify-between gap-2 border-b pb-1"
                  data-testid={`variable-line-${variable.id}`}
                >
                  <span className="text-xs text-muted-foreground">{variable.name}</span>
                  <span className="text-xs">
                    {line ? (
                      <>
                        {line.count.equals(1) ? null : (
                          <span className="text-muted-foreground">
                            {faNumber(line.count.toFixed(0))} ×{" "}
                          </span>
                        )}
                        {line.oneTime ? "به جمع کل: " : "هر عدد: "}
                        <Money
                          value={(line.oneTime ? line.orderTotal : line.perUnit).toFixed(4)}
                          currency="TOMAN"
                          hideCurrency
                        />
                      </>
                    ) : (
                      "—"
                    )}
                  </span>
                </div>
              );
            })}
            <div className="flex flex-wrap items-center justify-between gap-2 pt-1 font-semibold">
              <span>قیمت نهایی هر عدد</span>
              <Money value={(unitFinal ?? "0").toString()} currency="TOMAN" hideCurrency />
            </div>
            {orderTotal && (
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                <span>جمع کل سفارش ({faNumber(String(inputs.quantity))} عدد)</span>
                <Money value={orderTotal.toString()} currency="TOMAN" hideCurrency />
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {added && added.lines.length > 0 && (
        <Card data-testid="custom-lines">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">ثابت‌های شما</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {added.lines.map((line) => (
              <div key={line.name} className="flex items-center justify-between border-b pb-1">
                <span className="text-xs text-muted-foreground">{line.name}</span>
                <span>
                  + <Money value={line.amount.toFixed(4)} currency="TOMAN" hideCurrency />
                </span>
              </div>
            ))}
            <div className="flex items-center justify-between pt-1 font-semibold">
              <span>قیمت نهایی هر عدد با ثابت‌های شما</span>
              <Money value={added.unitFinalPrice.toFixed(4)} currency="TOMAN" hideCurrency />
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
