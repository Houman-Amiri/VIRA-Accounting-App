/**
 * سند جدید — multi-split journal form (RHF + Zod + useFieldArray).
 * Live zero-balance validation (superRefine), auto-balance button,
 * hierarchical account picker, pinned balance footer.
 */
import * as React from "react";
import { useForm, useFieldArray, type SubmitHandler } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { journalEntrySchema, splitTotals, autoBalance, type JournalEntryForm, type SplitForm } from "@/lib/journal";
import { Money } from "@/components/money";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useQuery } from "@tanstack/react-query";
import { api, newIdempotencyKey, parseError, ApiError } from "@/api/client";
import { clearDraft, loadDraft, registerDraft } from "@/lib/drafts";
import { faDate } from "@/lib/fa";
import { toMoneyString, tomanToRial } from "@/lib/money";
import { Badge } from "@/components/ui/badge";
import { CheckCircle2, Plus, Trash2, Wand2 } from "lucide-react";

interface AccountOption {
  id: string;
  code: string;
  name: string;
  parent_id: string | null;
}

export function JournalNewPage(): React.JSX.Element {
  const {
    register,
    control,
    handleSubmit,
    watch,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<JournalEntryForm>({
    resolver: zodResolver(journalEntrySchema),
    defaultValues: {
      date: new Date().toISOString().slice(0, 10),
      description: "",
      reference: "",
      currency_code: "IRR",
      splits: [
        { account_id: "", debit: "0", credit: "0", description: "", cost_center_id: "" },
        { account_id: "", debit: "0", credit: "0", description: "", cost_center_id: "" },
      ],
    },
    mode: "onChange",
  });
  const { fields, append, remove } = useFieldArray({ control, name: "splits" });
  const splits = watch("splits");
  const totals = splitTotals(splits as SplitForm[]);

  // Phase 5 §4 — stable Idempotency-Key for this logical submission (reused on
  // retry so the backend replays the cached response instead of duplicating).
  const idemKeyRef = React.useRef(newIdempotencyKey());

  // Phase 5 §4 — draft snapshot: restored after a 401→login round-trip.
  React.useEffect(() => {
    const saved = loadDraft<Partial<JournalEntryForm>>("journal-new");
    if (saved) {
      if (saved.description) setValue("description", saved.description);
      if (saved.reference) setValue("reference", saved.reference);
      if (Array.isArray(saved.splits) && saved.splits.length >= 1) {
        setValue("splits", saved.splits as SplitForm[]);
      }
    }
    return registerDraft("journal-new", () => ({
      description: watch("description"),
      reference: watch("reference"),
      splits: watch("splits"),
    }));
  }, [setValue, watch]);

  // Chart of accounts (hierarchical labels)
  const accountsQuery = useQuery({
    queryKey: ["accounts"],
    queryFn: async () => {
      const res = await api.GET("/api/v1/accounts");
      if (res.error) throw await parseError(res.response);
      return res.data as unknown as AccountOption[];
    },
  });
  const accountById = React.useMemo(
    () => new Map((accountsQuery.data ?? []).map((a) => [a.id, a])),
    [accountsQuery.data],
  );

  const onSubmit: SubmitHandler<JournalEntryForm> = async (data) => {
    try {
      const payload = {
        transaction_date: data.date,
        description: data.description,
        payee: data.reference || null,
        metadata: {},
        splits: data.splits.map((s) => ({
          account_id: s.account_id,
          // Form amounts are Tomans (user entry); API stores Rials — ×10 exactly once.
          debit: toMoneyString(tomanToRial(s.debit)),
          credit: toMoneyString(tomanToRial(s.credit)),
          memo: s.description || null,
          currency: data.currency_code,
          exchange_rate: "1.00000000",
        })),
      };
      const res = await api.POST("/api/v1/journal-entries", {
        body: payload as never,
        headers: { "Idempotency-Key": idemKeyRef.current },
      } as never);
      if (res.error) throw await parseError(res.response);
      idemKeyRef.current = newIdempotencyKey(); // next entry is a new operation
      clearDraft("journal-new");
      window.alert("سند با موفقیت ثبت شد.");
    } catch (e) {
      if (e instanceof ApiError && e.isStale) {
        // Phase 2 §9: compare/refresh before overwriting — never silent overwrite.
        const reload = window.confirm(
          "این رکورد هم‌زمان توسط کاربر دیگری تغییر کرده است. برای دریافت نسخه جدید بارگذاری مجدد می‌شود؟",
        );
        if (reload) window.location.reload();
        return;
      }
      window.alert(e instanceof Error ? e.message : "خطا در ثبت سند");
    }
  };

  return (
    <div className="mx-auto max-w-5xl space-y-4" dir="rtl">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">سند حسابداری جدید</h1>
        <Badge variant={totals.balanced ? "success" : "destructive"}>
          {totals.balanced ? "متوازن" : "نامتوازن"}
        </Badge>
      </div>

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle>مشخصات سند</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-3 gap-4">
            <div>
              <Label htmlFor="date">تاریخ</Label>
              <Input id="date" data-testid="entry-date" {...register("date")} />
              <p className="mt-1 text-xs text-muted-foreground">{faDate(watch("date"))}</p>
              {errors.date && <p className="mt-1 text-xs text-destructive">{errors.date.message}</p>}
            </div>
            <div>
              <Label htmlFor="description">شرح</Label>
              <Input id="description" data-testid="entry-description" {...register("description")} />
              {errors.description && <p className="mt-1 text-xs text-destructive">{errors.description.message}</p>}
            </div>
            <div>
              <Label htmlFor="reference">مرجع</Label>
              <Input id="reference" {...register("reference")} />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>ردیف‌های سند</CardTitle>
            <div className="flex gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                data-testid="auto-balance"
                onClick={() => {
                  const balanced = autoBalance(splits as SplitForm[], splits.length - 1);
                  balanced.forEach((s, i) => {
                    setValue(`splits.${i}.debit`, s.debit, { shouldValidate: true });
                    setValue(`splits.${i}.credit`, s.credit, { shouldValidate: true });
                  });
                }}
              >
                <Wand2 /> ترازنامه خودکار
              </Button>
              <Button
                type="button"
                size="sm"
                onClick={() =>
                  append({ account_id: "", debit: "0", credit: "0", description: "", cost_center_id: "" })
                }
              >
                <Plus /> افزودن ردیف
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {errors.splits?.message && (
              <p className="rounded-md bg-destructive/10 p-2 text-sm text-destructive" data-testid="balance-error">
                {errors.splits.message}
              </p>
            )}
            {fields.map((field, index) => (
              <div
                key={field.id}
                className="grid grid-cols-12 items-end gap-2 rounded-md border p-3"
                data-testid={`split-row-${index}`}
              >
                <div className="col-span-5">
                  <Label>حساب</Label>
                  <select
                    className="flex h-9 w-full rounded-md border border-input bg-transparent px-2 text-sm"
                    data-testid={`split-account-${index}`}
                    {...register(`splits.${index}.account_id`)}
                  >
                    <option value="">انتخاب حساب…</option>
                    {(accountsQuery.data ?? []).map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.code} — {a.name}
                      </option>
                    ))}
                  </select>
                  {errors.splits?.[index]?.account_id && (
                    <p className="mt-1 text-xs text-destructive">{errors.splits[index]?.account_id?.message}</p>
                  )}
                </div>
                <div className="col-span-2">
                  <Label>بدهکار</Label>
                  <Input
                    inputMode="decimal"
                    className="num"
                    data-testid={`split-debit-${index}`}
                    {...register(`splits.${index}.debit`)}
                  />
                </div>
                <div className="col-span-2">
                  <Label>بستانکار</Label>
                  <Input
                    inputMode="decimal"
                    className="num"
                    data-testid={`split-credit-${index}`}
                    {...register(`splits.${index}.credit`)}
                  />
                </div>
                <div className="col-span-2">
                  <Label>شرح</Label>
                  <Input {...register(`splits.${index}.description`)} />
                </div>
                <div className="col-span-1">
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    aria-label="حذف ردیف"
                    disabled={fields.length <= 2}
                    onClick={() => remove(index)}
                  >
                    <Trash2 />
                  </Button>
                </div>
                {accountById.size > 0 && watch(`splits.${index}.account_id`) && (
                  <p className="col-span-12 text-xs text-muted-foreground">
                    {accountById.get(watch(`splits.${index}.account_id`))?.name}
                  </p>
                )}
              </div>
            ))}
          </CardContent>
        </Card>

        {/* Pinned balance footer */}
        <div
          className="sticky bottom-0 flex items-center justify-between rounded-lg border bg-card/95 p-4 shadow-lg backdrop-blur"
          data-testid="balance-footer"
        >
          <div className="flex items-center gap-6">
            <div>
              <div className="text-xs text-muted-foreground">جمع بدهکار</div>
              <Money value={totals.totalDebit.toFixed(4)} currency="TOMAN" />
            </div>
            <div>
              <div className="text-xs text-muted-foreground">جمع بستانکار</div>
              <Money value={totals.totalCredit.toFixed(4)} currency="TOMAN" />
            </div>
            <div>
              <div className="text-xs text-muted-foreground">اختلاف</div>
              <Money value={totals.difference.toFixed(4)} currency="TOMAN" signedColors accounting={false} />
            </div>
            {totals.balanced && (
              <Badge variant="success" data-testid="balanced-badge">
                <CheckCircle2 className="h-3 w-3" /> متوازن
              </Badge>
            )}
          </div>
          <Button type="submit" disabled={isSubmitting || !totals.balanced} data-testid="submit-entry">
            ثبت سند
          </Button>
        </div>
      </form>
    </div>
  );
}
