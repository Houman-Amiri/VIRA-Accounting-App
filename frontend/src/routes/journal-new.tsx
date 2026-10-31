/**
 * سند جدید — a real invoice, not a debit/credit puzzle (item 11).
 *
 * The user fills what a paper invoice carries: date, seller, buyer, the items
 * with their own amount, and the grand total. The two balanced splits are
 * derived by the server from the chart of accounts, so the double-entry rules
 * still hold while بدهکار/بستانکار never appears on this screen.
 */
import * as React from "react";
import { useForm, useFieldArray, Controller, type SubmitHandler } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  INVOICE_KINDS,
  invoiceFormSchema,
  invoiceTotal,
  lineAmount,
  moneyString,
  parseAmount,
  type InvoiceForm,
  type InvoiceKind,
} from "@/lib/invoice";
import { Money } from "@/components/money";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useQuery } from "@tanstack/react-query";
import { api, newIdempotencyKey, parseError, ApiError } from "@/api/client";
import { clearDraft, loadDraft, registerDraft } from "@/lib/drafts";
import { trackEvent } from "@/lib/analytics";
import { faDate, faNumber } from "@/lib/fa";
import { tehranToday, validIso } from "@/lib/calendar";
import { useCalendar } from "@/lib/calendar-settings";
import { CalendarInput } from "@/components/calendar-input";
import { toMoneyString, tomanToRial } from "@/lib/money";
import { Badge } from "@/components/ui/badge";
import { CheckCircle2, Plus, Trash2 } from "lucide-react";
import { StepGuide } from "@/components/guide-steps";

type CreatedInvoice = {
  entry: { id: string; entry_number: number };
  total: string;
  lines: Array<{ title: string; line_total: string }>;
};

const emptyLine = (): InvoiceForm["lines"][number] => ({
  title: "",
  quantity: "1",
  unit_price: "",
});

const emptyForm = (date: string): InvoiceForm => ({
  kind: "sale",
  date,
  seller: "",
  buyer: "",
  note: "",
  lines: [emptyLine()],
});

export const JOURNAL_GUIDE_STEPS = [
  {
    title: "نوع سند را انتخاب کنید",
    body: "«فاکتور فروش» برای فروش به مشتری و «فاکتور خرید» برای خرید از تأمین‌کننده.",
  },
  {
    title: "تاریخ، فروشنده و خریدار",
    body: "همان چیزی که روی کاغذ فاکتور نوشته شده است.",
  },
  {
    title: "کالاها را ردیف‌به‌ردیف بنویسید",
    body: "نام کالا، تعداد و مبلغ واحد؛ مبلغ جزء و مبلغ کل خودکار حساب می‌شود.",
  },
  {
    title: "ثبت سند",
    body: "سند به‌صورت خودکار و متوازن در دفتر ثبت می‌شود؛ لازم نیست بدهکار و بستانکار را خودتان بنویسید.",
  },
];

export function JournalNewPage(): React.JSX.Element {
  const { calendar, ready: calendarReady } = useCalendar();
  const [created, setCreated] = React.useState<CreatedInvoice | null>(null);
  const [serverError, setServerError] = React.useState<string | null>(null);

  const {
    register,
    control,
    handleSubmit,
    watch,
    setValue,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<InvoiceForm>({
    resolver: zodResolver(invoiceFormSchema),
    defaultValues: emptyForm(tehranToday()),
    mode: "onChange",
  });
  const { fields, append, remove } = useFieldArray({ control, name: "lines" });

  const lines = watch("lines");
  const kind = watch("kind") as InvoiceKind;
  // Computed on every render on purpose: react-hook-form hands back the same
  // array reference while mutating it, so a useMemo keyed on `lines` would keep
  // a stale grand total.
  const total = invoiceTotal(lines ?? []);

  // Phase 5 §4 — stable Idempotency-Key for this logical submission (reused on
  // retry so the backend replays the cached response instead of duplicating).
  const idemKeyRef = React.useRef(newIdempotencyKey());

  // Phase 5 §4 — draft snapshot: restored after a 401→login round-trip.
  React.useEffect(() => {
    const saved = loadDraft<Partial<InvoiceForm>>("journal-new");
    if (saved) {
      if (saved.date && validIso(saved.date)) setValue("date", saved.date);
      if (saved.kind) setValue("kind", saved.kind);
      if (saved.seller) setValue("seller", saved.seller);
      if (saved.buyer) setValue("buyer", saved.buyer);
      if (saved.note) setValue("note", saved.note);
      if (Array.isArray(saved.lines) && saved.lines.length >= 1) {
        setValue("lines", saved.lines);
      }
    }
    return registerDraft("journal-new", () => ({
      kind: watch("kind"),
      date: watch("date"),
      seller: watch("seller"),
      buyer: watch("buyer"),
      note: watch("note"),
      lines: watch("lines"),
    }));
  }, [setValue, watch]);

  // Only used to tell the user which accounts the system will use.
  const accountsQuery = useQuery({
    queryKey: ["accounts"],
    queryFn: async () => {
      const res = await api.GET("/api/v1/accounts");
      if (res.error) throw await parseError(res.response);
      return res.data as unknown as Array<{ id: string; code: string; name: string }>;
    },
  });
  const mappingLabel = React.useMemo(() => {
    const codes = kind === "sale" ? ["1040", "4010"] : ["1030", "2010"];
    const byCode = new Map((accountsQuery.data ?? []).map((a) => [a.code, a.name]));
    return codes.map((code) => `${code} ${byCode.get(code) ?? ""}`.trim()).join(" / ");
  }, [accountsQuery.data, kind]);

  const onSubmit: SubmitHandler<InvoiceForm> = async (data) => {
    try {
      setServerError(null);
      if (!calendarReady) throw new Error("پیش از ثبت سند، تنظیم تقویم باید دریافت شود.");
      // Form amounts are Tomans (user entry); the ledger stores Rials — ×10 once.
      const body = {
        kind: data.kind,
        transaction_date: data.date,
        seller: data.seller?.trim() || null,
        buyer: data.buyer?.trim() || null,
        note: data.note?.trim() || null,
        lines: data.lines.map((line) => ({
          title: line.title.trim(),
          quantity: moneyString(parseAmount(line.quantity)),
          unit_price: toMoneyString(tomanToRial(parseAmount(line.unit_price))),
        })),
      };
      const res = await api.POST("/api/v1/journal-entries/invoice", {
        body: body as never,
        headers: { "Idempotency-Key": idemKeyRef.current },
      } as never);
      if (res.error) throw await parseError(res.response);
      idemKeyRef.current = newIdempotencyKey(); // next entry is a new operation
      clearDraft("journal-new");
      const invoice = res.data as unknown as CreatedInvoice;
      setCreated(invoice);
      reset(emptyForm(data.date));
      trackEvent("journal_entry_created", { route: "/journal/new", status: "ok" });
    } catch (e) {
      if (e instanceof ApiError && e.isStale) {
        // Phase 2 §9: compare/refresh before overwriting — never silent overwrite.
        const reload = window.confirm(
          "این رکورد هم‌زمان توسط کاربر دیگری تغییر کرده است. برای دریافت نسخه جدید بارگذاری مجدد می‌شود؟",
        );
        if (reload) window.location.reload();
        return;
      }
      setServerError(e instanceof Error ? e.message : "ثبت سند ناموفق بود.");
    }
  };

  return (
    <div className="mx-auto max-w-5xl space-y-4" dir="rtl">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-bold">سند جدید</h1>
        <Badge variant="outline" data-testid="invoice-total-badge">
          مبلغ کل: <Money value={total.toFixed(4)} currency="TOMAN" />
        </Badge>
      </div>

      <StepGuide
        id="journal-new"
        title="راهنمای ثبت سند"
        intro="این سند مثل یک فاکتور کاغذی پر می‌شود؛ ثبت دوطرفه را سیستم انجام می‌دهد."
        steps={JOURNAL_GUIDE_STEPS}
      />

      {created && (
        <p
          className="flex items-center gap-2 rounded-md bg-positive/10 px-3 py-2 text-sm"
          data-testid="entry-created"
        >
          <CheckCircle2 className="h-4 w-4 text-positive" />
          سند شمارهٔ <span className="num">{faNumber(String(created.entry.entry_number))}</span> ثبت
          شد — مبلغ کل: <Money value={created.total} currency="TOMAN" />
        </p>
      )}
      {serverError && (
        <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {serverError}
        </p>
      )}

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">اطلاعات فاکتور</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <Label htmlFor="invoice-kind">نوع سند</Label>
              <select
                id="invoice-kind"
                data-testid="invoice-kind"
                className="flex h-9 w-full rounded-md border border-input bg-background px-2 text-sm text-foreground"
                {...register("kind")}
              >
                {(Object.keys(INVOICE_KINDS) as InvoiceKind[]).map((value) => (
                  <option key={value} value={value}>
                    {INVOICE_KINDS[value]}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <Controller
                name="date"
                control={control}
                render={({ field }) => (
                  <CalendarInput
                    id="entry-date"
                    label="تاریخ"
                    required
                    value={field.value}
                    onChange={field.onChange}
                  />
                )}
              />
              <p className="mt-1 text-xs text-muted-foreground" data-testid="entry-date-preview">
                {faDate(watch("date"), calendar)}
              </p>
              {errors.date && (
                <p className="mt-1 text-xs text-destructive">{errors.date.message}</p>
              )}
            </div>
            <div>
              <Label htmlFor="invoice-seller">فروشنده</Label>
              <Input
                id="invoice-seller"
                data-testid="invoice-seller"
                placeholder="نام فروشنده"
                {...register("seller")}
              />
              {errors.seller && (
                <p className="mt-1 text-xs text-destructive">{errors.seller.message}</p>
              )}
            </div>
            <div>
              <Label htmlFor="invoice-buyer">خریدار</Label>
              <Input
                id="invoice-buyer"
                data-testid="invoice-buyer"
                placeholder="نام خریدار"
                {...register("buyer")}
              />
              {errors.buyer && (
                <p className="mt-1 text-xs text-destructive">{errors.buyer.message}</p>
              )}
            </div>
            <div className="sm:col-span-2">
              <Label htmlFor="entry-description">توضیحات (اختیاری)</Label>
              <Input
                id="entry-description"
                data-testid="entry-description"
                placeholder="مثلاً تحویل حضوری"
                {...register("note")}
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
            <CardTitle className="text-base">کالاها</CardTitle>
            <Button
              type="button"
              size="sm"
              variant="outline"
              data-testid="invoice-add-line"
              onClick={() => append(emptyLine())}
            >
              <Plus /> افزودن ردیف
            </Button>
          </CardHeader>
          <CardContent className="space-y-3">
            {errors.lines?.message && (
              <p className="text-sm text-destructive" data-testid="invoice-lines-error">
                {errors.lines.message as string}
              </p>
            )}
            {fields.map((field, index) => (
              <div
                key={field.id}
                className="grid grid-cols-2 items-end gap-2 rounded-md border p-3 sm:grid-cols-12"
                data-testid={`invoice-line-${index}`}
              >
                <div className="col-span-2 sm:col-span-5">
                  <Label htmlFor={`invoice-title-${index}`}>نام کالا یا خدمت</Label>
                  <Input
                    id={`invoice-title-${index}`}
                    data-testid={`invoice-title-${index}`}
                    {...register(`lines.${index}.title`)}
                  />
                  {errors.lines?.[index]?.title && (
                    <p className="mt-1 text-xs text-destructive">
                      {errors.lines[index]?.title?.message}
                    </p>
                  )}
                </div>
                <div className="col-span-1 sm:col-span-2">
                  <Label htmlFor={`invoice-quantity-${index}`}>تعداد</Label>
                  <Input
                    id={`invoice-quantity-${index}`}
                    inputMode="decimal"
                    className="num"
                    data-testid={`invoice-quantity-${index}`}
                    {...register(`lines.${index}.quantity`)}
                  />
                  {errors.lines?.[index]?.quantity && (
                    <p className="mt-1 text-xs text-destructive">
                      {errors.lines[index]?.quantity?.message}
                    </p>
                  )}
                </div>
                <div className="col-span-1 sm:col-span-2">
                  <Label htmlFor={`invoice-price-${index}`}>مبلغ واحد (تومان)</Label>
                  <Input
                    id={`invoice-price-${index}`}
                    inputMode="decimal"
                    className="num"
                    data-testid={`invoice-price-${index}`}
                    {...register(`lines.${index}.unit_price`)}
                  />
                  {errors.lines?.[index]?.unit_price && (
                    <p className="mt-1 text-xs text-destructive">
                      {errors.lines[index]?.unit_price?.message}
                    </p>
                  )}
                </div>
                <div className="col-span-1 sm:col-span-2">
                  <Label>مبلغ جزء</Label>
                  <p className="num h-9 leading-9" data-testid={`invoice-line-total-${index}`}>
                    <Money
                      value={lineAmount(lines?.[index] ?? emptyLine()).toFixed(4)}
                      currency="TOMAN"
                    />
                  </p>
                </div>
                <div className="col-span-1">
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    aria-label="حذف ردیف"
                    data-testid={`invoice-remove-${index}`}
                    disabled={fields.length <= 1}
                    onClick={() => remove(index)}
                  >
                    <Trash2 />
                  </Button>
                </div>
              </div>
            ))}
            <p className="text-xs text-muted-foreground" data-testid="invoice-mapping-note">
              ثبت دوطرفه به‌صورت خودکار انجام می‌شود
              {accountsQuery.isSuccess && mappingLabel ? `: ${mappingLabel}` : "."}
            </p>
          </CardContent>
        </Card>

        <div
          className="sticky bottom-0 flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-card/95 p-4 shadow-lg backdrop-blur"
          data-testid="balance-footer"
        >
          <div className="flex flex-wrap items-center gap-3 sm:gap-6">
            <div>
              <div className="text-xs text-muted-foreground">تعداد ردیف</div>
              <div className="num" data-testid="invoice-line-count">
                {faNumber(String(lines?.length ?? 0))}
              </div>
            </div>
            <div>
              <div className="text-xs text-muted-foreground">مبلغ کل</div>
              <div data-testid="invoice-grand-total">
                <Money value={total.toFixed(4)} currency="TOMAN" />
              </div>
            </div>
          </div>
          <Button
            type="submit"
            disabled={isSubmitting || !calendarReady || !validIso(watch("date")) || total.lte(0)}
            data-testid="submit-entry"
          >
            ثبت سند
          </Button>
        </div>
      </form>
    </div>
  );
}
