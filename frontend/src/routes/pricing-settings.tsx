/**
 * قیمت‌گذاری — every pricing setting in one place.
 *
 * Two groups, in the owner's language:
 *
 *   ۱) ثابت‌های اصلی — the seven values the workbook `قیمت نهایی.xlsx` is built
 *      on (price of a filament gram, electricity, depreciation, profit factor,
 *      chain, shipment, label). They feed the calculator exactly as before.
 *   ۲) ثابت‌های من — costs the owner adds himself («بسته‌بندی»، «کارمزد پست»، …)
 *      and for each one he chooses *how it is calculated*: a fixed amount per
 *      piece, a fixed amount per shipment, a percentage of the production cost,
 *      or a percentage of the selling price.
 *
 * Nothing here rewrites a saved price: the constants are read by the calculator
 * the next time it runs, and the effect of every row is shown live at the top so
 * the owner can see exactly what his change does before he relies on it.
 */
import * as React from "react";
import { Link } from "@tanstack/react-router";
import { Money } from "@/components/money";
import { QueryNotice } from "@/components/query-notice";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { faNumber } from "@/lib/fa";
import { DEFAULT_CONSTANTS, computePrice, parseNum, type PriceBreakdown } from "@/lib/priceCalc";
import {
  CUSTOM_METHODS,
  CUSTOM_METHOD_LABEL,
  PRICING_FIELDS,
  pricingConstants,
  useCreateCustomConstant,
  useCustomConstants,
  useDeleteCustomConstant,
  usePricingSettings,
  useSavePricingSettings,
  useUpdateCustomConstant,
  type CustomConstant,
  type CustomMethod,
  type EditableConstant,
} from "@/lib/pricing-settings";

/** A small, honest sample so the owner can watch his constants act. */
const PREVIEW = { weightG: "250", printHours: "4", quantity: "10" } as const;

function errText(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

/** Preview the effect of every custom constant without saving anything. */
function Preview({
  base,
  constants,
}: {
  base: PriceBreakdown;
  constants: CustomConstant[];
}): React.JSX.Element {
  const quantity = PREVIEW.quantity;
  const rows = constants
    .filter((constant) => constant.is_active)
    .map((constant) => {
      const value = parseNum(constant.value);
      let amount = parseNum("0");
      if (constant.method === "PER_UNIT") amount = value;
      else if (constant.method === "PER_BATCH") amount = value.div(quantity);
      else if (constant.method === "PERCENT_OF_COST")
        amount = base.unitProductionCost.times(value).div(100);
      else amount = base.unitFinalPrice.times(value).div(100);
      return { constant, amount };
    });
  const total = rows.reduce((sum, row) => sum.plus(row.amount), parseNum("0"));
  return (
    <Card data-testid="pricing-preview">
      <CardHeader className="pb-2">
        <CardTitle className="text-base">اثر ثابت‌ها روی یک نمونه</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <p className="text-xs text-muted-foreground">
          نمونهٔ محاسبه: {faNumber(PREVIEW.weightG)} گرم فیلامنت، {faNumber(PREVIEW.printHours)}{" "}
          ساعت پرینت، تیراژ {faNumber(quantity)} عدد. این فقط برای دیدن اثر است و چیزی ذخیره
          نمی‌کند.
        </p>
        <div className="flex items-center justify-between border-b pb-1">
          <span>قیمت نهایی هر عدد بدون ثابت‌های من</span>
          <Money value={base.unitFinalPrice} currency="TOMAN" hideCurrency />
        </div>
        {rows.map(({ constant, amount }) => (
          <div
            key={constant.id}
            className="flex items-center justify-between text-xs text-muted-foreground"
            data-testid={`preview-row-${constant.id}`}
          >
            <span>
              {constant.name}
              <span className="mx-1 text-[10px]">({CUSTOM_METHOD_LABEL[constant.method]})</span>
            </span>
            <span className="flex items-center gap-1">
              <span className="text-muted-foreground">+</span>
              <Money value={amount} currency="TOMAN" hideCurrency />
            </span>
          </div>
        ))}
        <div className="flex items-center justify-between border-t pt-1 font-semibold">
          <span>قیمت نهایی هر عدد</span>
          <Money value={base.unitFinalPrice.plus(total)} currency="TOMAN" hideCurrency />
        </div>
      </CardContent>
    </Card>
  );
}

export function PricingSettingsPage(): React.JSX.Element {
  const settings = usePricingSettings();
  const saveSettings = useSavePricingSettings();
  const customs = useCustomConstants();
  const createCustom = useCreateCustomConstant();
  const updateCustom = useUpdateCustomConstant();
  const deleteCustom = useDeleteCustomConstant();

  const [draft, setDraft] = React.useState<Partial<Record<EditableConstant, string>>>({});
  const [revision, setRevision] = React.useState<number | null>(null);
  const [settingsMessage, setSettingsMessage] = React.useState<string | null>(null);
  const [settingsError, setSettingsError] = React.useState<string | null>(null);

  const [newName, setNewName] = React.useState("");
  const [newMethod, setNewMethod] = React.useState<CustomMethod>("PER_UNIT");
  const [newValue, setNewValue] = React.useState("");
  const [customError, setCustomError] = React.useState<string | null>(null);
  const [editing, setEditing] = React.useState<{
    id: string;
    name: string;
    method: CustomMethod;
    value: string;
  } | null>(null);

  const constants = React.useMemo(
    () => (settings.data ? pricingConstants(settings.data) : null),
    [settings.data],
  );
  const previewBase = React.useMemo<PriceBreakdown | null>(() => {
    if (!constants) return null;
    try {
      return computePrice({ ...PREVIEW, variant: "plain", channel: "marketplace" }, constants);
    } catch {
      return null;
    }
  }, [constants]);

  const edit = (key: EditableConstant, value: string): void => {
    setRevision((current) => current ?? settings.data?.version_id ?? null);
    setDraft((current) => ({ ...current, [key]: value }));
    setSettingsMessage(null);
    setSettingsError(null);
  };

  async function submitSettings(event: React.FormEvent): Promise<void> {
    event.preventDefault();
    if (!settings.data) return;
    setSettingsError(null);
    setSettingsMessage(null);
    try {
      const body = Object.fromEntries(
        PRICING_FIELDS.map(([key]) => {
          const raw = draft[key] ?? settings.data[key];
          if (!String(raw).trim()) throw new Error("همهٔ ثابت‌ها را وارد کنید.");
          const amount = parseNum(raw);
          const max = key === "profitFactor" ? "1000" : "1000000000000";
          if (amount.isNegative() || amount.gt(max) || amount.decimalPlaces() > 4) {
            throw new Error("ثابت‌ها باید نامنفی، در محدودهٔ مجاز و حداکثر چهار رقم اعشار باشند.");
          }
          return [key, amount.toFixed(4)];
        }),
      ) as Record<EditableConstant, string>;
      await saveSettings.mutateAsync({
        ...body,
        version_id: revision ?? settings.data.version_id,
      });
      setDraft({});
      setRevision(null);
      setSettingsMessage("ثابت‌های اصلی ذخیره شدند.");
    } catch (error) {
      setSettingsError(errText(error, "ذخیرهٔ ثابت‌ها ناموفق بود."));
    }
  }

  async function addConstant(event: React.FormEvent): Promise<void> {
    event.preventDefault();
    setCustomError(null);
    try {
      const name = newName.trim();
      if (!name) throw new Error("برای ثابت جدید یک نام بنویسید.");
      const value = parseNum(newValue);
      if (String(newValue).trim() === "") throw new Error("مقدار ثابت را وارد کنید.");
      if (value.isNegative()) throw new Error("مقدار ثابت نمی‌تواند منفی باشد.");
      if (newMethod.startsWith("PERCENT") && value.gt(1000)) {
        throw new Error("درصد نمی‌تواند از ۱۰۰۰ بیشتر باشد.");
      }
      await createCustom.mutateAsync({
        name,
        method: newMethod,
        value: value.toFixed(4),
        is_active: true,
      });
      setNewName("");
      setNewValue("");
      setNewMethod("PER_UNIT");
    } catch (error) {
      setCustomError(errText(error, "افزودن ثابت ناموفق بود."));
    }
  }

  async function saveEdit(): Promise<void> {
    if (!editing) return;
    setCustomError(null);
    try {
      const name = editing.name.trim();
      if (!name) throw new Error("نام ثابت نمی‌تواند خالی باشد.");
      const value = parseNum(editing.value);
      if (String(editing.value).trim() === "") throw new Error("مقدار ثابت را وارد کنید.");
      if (value.isNegative()) throw new Error("مقدار ثابت نمی‌تواند منفی باشد.");
      await updateCustom.mutateAsync({
        id: editing.id,
        patch: { name, method: editing.method, value: value.toFixed(4) },
      });
      setEditing(null);
    } catch (error) {
      setCustomError(errText(error, "ذخیرهٔ ثابت ناموفق بود."));
    }
  }

  const customList = customs.data ?? [];
  const busy =
    createCustom.isPending ||
    updateCustom.isPending ||
    deleteCustom.isPending ||
    saveSettings.isPending;

  return (
    <div className="mx-auto max-w-5xl space-y-4" dir="rtl" data-testid="pricing-settings-page">
      <header className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-xl font-bold">قیمت‌گذاری</h1>
          <p className="mt-1 text-xs text-muted-foreground">
            همهٔ اعداد ماشین‌حساب قیمت، در یک صفحه: هفت ثابت اصلی و ثابت‌هایی که خودتان اضافه
            می‌کنید.
          </p>
        </div>
        <Link
          to="/price-calc"
          className="rounded-md border px-3 py-1.5 text-sm text-primary hover:bg-accent"
        >
          محاسبه‌گر قیمت
        </Link>
      </header>

      {customError && (
        <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {customError}
        </p>
      )}

      {/* ------------------------------------------------ the seven built-ins --- */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-base">
            ثابت‌های اصلی
            <Badge variant="secondary">مبنای محاسبهٔ قبلی</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <QueryNotice query={settings} />
          {settings.data && (
            <form onSubmit={(event) => void submitSettings(event)} className="space-y-4">
              <p className="text-xs text-muted-foreground">
                تغییرات روی محاسبات جدید اثر می‌گذارد؛ قیمت‌های قبلی و اسناد ثبت‌شده تغییر نمی‌کنند.
              </p>
              <fieldset disabled={saveSettings.isPending} className="grid gap-3 sm:grid-cols-2">
                {PRICING_FIELDS.map(([key, label]) => (
                  <div key={key} className="space-y-1">
                    <Label htmlFor={`pricing-${key}`} className="text-xs">
                      {label}
                    </Label>
                    <Input
                      id={`pricing-${key}`}
                      data-testid={`const-${key}`}
                      className="num"
                      inputMode="decimal"
                      required
                      value={draft[key] ?? settings.data[key]}
                      onChange={(event) => edit(key, event.target.value)}
                    />
                  </div>
                ))}
              </fieldset>
              {settingsError && (
                <p role="alert" className="text-sm text-destructive">
                  {settingsError}
                </p>
              )}
              {settingsMessage && (
                <p role="status" data-testid="pricing-saved" className="text-sm text-positive">
                  {settingsMessage}
                </p>
              )}
              <div className="flex flex-wrap gap-2">
                <Button type="submit" disabled={saveSettings.isPending}>
                  {saveSettings.isPending ? "در حال ذخیره…" : "ذخیرهٔ ثابت‌های اصلی"}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  disabled={saveSettings.isPending}
                  onClick={() => {
                    setRevision((current) => current ?? settings.data?.version_id ?? null);
                    setDraft(
                      Object.fromEntries(
                        PRICING_FIELDS.map(([key]) => [key, DEFAULT_CONSTANTS[key]]),
                      ) as Record<EditableConstant, string>,
                    );
                    setSettingsMessage(null);
                    setSettingsError(null);
                  }}
                >
                  مقادیر پیش‌فرض
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  disabled={saveSettings.isPending}
                  onClick={() => {
                    setDraft({});
                    setRevision(null);
                    setSettingsError(null);
                    setSettingsMessage(null);
                    void settings.refetch();
                  }}
                >
                  لغو تغییرها
                </Button>
              </div>
            </form>
          )}
        </CardContent>
      </Card>

      {/* -------------------------------------------------- owner's constants --- */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">ثابت‌های من</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-xs text-muted-foreground">
            هر هزینه‌ای که در محاسبهٔ قبلی نبود را اینجا اضافه کنید و بگویید چطور حساب شود. این
            مبالغ به قیمت فروش هر عدد اضافه می‌شوند.
          </p>
          <QueryNotice query={customs} />

          {customs.isSuccess && customList.length === 0 && (
            <p className="rounded-md bg-muted px-3 py-2 text-sm" data-testid="custom-empty">
              هنوز ثابت سفارشی ندارید. اولین مورد را از فرم پایین اضافه کنید (مثلاً «هزینهٔ
              پسته‌بندی»).
            </p>
          )}

          {customList.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm" aria-label="ثابت‌های قیمت‌گذاری من">
                <thead>
                  <tr className="border-b text-xs text-muted-foreground">
                    <th scope="col" className="py-2 text-start font-medium">
                      نام
                    </th>
                    <th scope="col" className="py-2 text-start font-medium">
                      نحوهٔ محاسبه
                    </th>
                    <th scope="col" className="py-2 text-start font-medium">
                      مقدار
                    </th>
                    <th scope="col" className="py-2 text-start font-medium">
                      وضعیت
                    </th>
                    <th scope="col" className="py-2 text-end font-medium">
                      کارها
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {customList.map((constant) => {
                    const isEditing = editing?.id === constant.id;
                    return (
                      <tr
                        key={constant.id}
                        data-testid={`custom-row-${constant.id}`}
                        className="border-b"
                      >
                        <td className="py-2">
                          {isEditing ? (
                            <Input
                              aria-label="نام ثابت سفارشی"
                              data-testid={`custom-edit-name-${constant.id}`}
                              className="h-8 text-xs"
                              value={editing.name}
                              onChange={(event) =>
                                setEditing({ ...editing, name: event.target.value })
                              }
                            />
                          ) : (
                            constant.name
                          )}
                        </td>
                        <td className="py-2">
                          {isEditing ? (
                            <select
                              aria-label="نحوهٔ محاسبه"
                              data-testid={`custom-method-${constant.id}`}
                              className="h-8 w-full rounded-md border border-input bg-background px-2 text-xs text-foreground"
                              value={editing.method}
                              onChange={(event) =>
                                setEditing({
                                  ...editing,
                                  method: event.target.value as CustomMethod,
                                })
                              }
                            >
                              {CUSTOM_METHODS.map((method) => (
                                <option key={method.value} value={method.value}>
                                  {method.label}
                                </option>
                              ))}
                            </select>
                          ) : (
                            <span className="text-xs">{CUSTOM_METHOD_LABEL[constant.method]}</span>
                          )}
                        </td>
                        <td className="num py-2">
                          {isEditing ? (
                            <Input
                              aria-label="مقدار ثابت سفارشی"
                              data-testid={`custom-value-${constant.id}`}
                              className="num h-8 w-28 text-xs"
                              inputMode="decimal"
                              value={editing.value}
                              onChange={(event) =>
                                setEditing({ ...editing, value: event.target.value })
                              }
                            />
                          ) : constant.method.startsWith("PERCENT") ? (
                            <>{faNumber(constant.value)}٪</>
                          ) : (
                            <Money value={constant.value} currency="TOMAN" hideCurrency />
                          )}
                        </td>
                        <td className="py-2">
                          <Badge variant={constant.is_active ? "success" : "outline"}>
                            {constant.is_active ? "فعال" : "خاموش"}
                          </Badge>
                        </td>
                        <td className="py-2">
                          <div className="flex flex-wrap items-center justify-end gap-1">
                            {isEditing ? (
                              <>
                                <Button
                                  size="sm"
                                  data-testid={`custom-save-${constant.id}`}
                                  disabled={busy}
                                  onClick={() => void saveEdit()}
                                >
                                  ذخیره
                                </Button>
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  onClick={() => {
                                    setEditing(null);
                                    setCustomError(null);
                                  }}
                                >
                                  لغو
                                </Button>
                              </>
                            ) : (
                              <>
                                <Button
                                  size="sm"
                                  variant="outline"
                                  data-testid={`custom-edit-${constant.id}`}
                                  onClick={() =>
                                    setEditing({
                                      id: constant.id,
                                      name: constant.name,
                                      method: constant.method,
                                      value: constant.value,
                                    })
                                  }
                                >
                                  ویرایش
                                </Button>
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  data-testid={`custom-toggle-${constant.id}`}
                                  disabled={busy}
                                  onClick={() =>
                                    void updateCustom.mutateAsync({
                                      id: constant.id,
                                      patch: { is_active: !constant.is_active },
                                    })
                                  }
                                >
                                  {constant.is_active ? "خاموش کن" : "روشن کن"}
                                </Button>
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  className="text-destructive"
                                  data-testid={`custom-delete-${constant.id}`}
                                  disabled={busy}
                                  onClick={() => void deleteCustom.mutateAsync(constant.id)}
                                >
                                  حذف
                                </Button>
                              </>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          <form
            onSubmit={(event) => void addConstant(event)}
            className="space-y-3 rounded-lg border bg-muted/30 p-3"
            data-testid="custom-add-form"
          >
            <p className="text-sm font-medium">افزودن ثابت جدید</p>
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="space-y-1">
                <Label htmlFor="custom-name" className="text-xs">
                  نام ثابت
                </Label>
                <Input
                  id="custom-name"
                  data-testid="custom-name"
                  className="h-9"
                  placeholder="مثلاً هزینهٔ بسته‌بندی"
                  value={newName}
                  onChange={(event) => setNewName(event.target.value)}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="custom-method" className="text-xs">
                  نحوهٔ محاسبه
                </Label>
                <select
                  id="custom-method"
                  data-testid="custom-method"
                  className="flex h-9 w-full rounded-md border border-input bg-background px-2 text-sm text-foreground"
                  value={newMethod}
                  onChange={(event) => setNewMethod(event.target.value as CustomMethod)}
                >
                  {CUSTOM_METHODS.map((method) => (
                    <option key={method.value} value={method.value}>
                      {method.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-1">
                <Label htmlFor="custom-value" className="text-xs">
                  {newMethod.startsWith("PERCENT") ? "درصد" : "مبلغ (تومان)"}
                </Label>
                <Input
                  id="custom-value"
                  data-testid="custom-value"
                  className="num h-9"
                  inputMode="decimal"
                  value={newValue}
                  onChange={(event) => setNewValue(event.target.value)}
                />
              </div>
            </div>
            <p className="text-xs text-muted-foreground" data-testid="custom-method-hint">
              {CUSTOM_METHODS.find((method) => method.value === newMethod)?.hint}
            </p>
            <Button type="submit" data-testid="custom-add" disabled={busy}>
              افزودن ثابت
            </Button>
          </form>
        </CardContent>
      </Card>

      {previewBase && <Preview base={previewBase} constants={customList} />}

      <p className="border-t pt-3 text-[11px] leading-5 text-muted-foreground">
        قیمت‌های ذخیره‌شده روی سفارش‌ها و کارهای تولید تغییر نمی‌کنند. این صفحه فقط اعداد ماشین‌حساب
        را برای محاسبات بعدی تنظیم می‌کند.
      </p>
    </div>
  );
}
