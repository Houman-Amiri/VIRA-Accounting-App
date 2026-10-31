/**
 * One سند opened from دفتر اسناد: read it, correct it, change its status.
 *
 * The owner's rule (item 11) still holds — no بدهکار/بستانکار on this screen.
 * An invoice-shaped entry is edited as the invoice it is (date, seller/buyer,
 * items, prices); the server re-derives the balanced lines. A hand-written
 * entry only exposes its date, description and counterparty.
 *
 * Status is a real state change, not a label:
 *   پیش‌نویس → «ثبت در دفاتر» (post) → ثبت‌شده → «برگشت به پیش‌نویس» (unpost)
 *   ثبت‌شده → «ابطال» (void, with a reason)
 * A posted entry is corrected by the server as unpost → edit → post inside one
 * transaction; the previous content stays in the audit history.
 */
import * as React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, parseError } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { CalendarInput } from "@/components/calendar-input";
import { Money } from "@/components/money";
import { faDate, faNumber } from "@/lib/fa";
import { useCalendar } from "@/lib/calendar-settings";
import { parseAmount, invoiceFormSchema, moneyString, type InvoiceKind } from "@/lib/invoice";
import { rialToToman, tomanToRial, toMoneyString } from "@/lib/money";

export type EntryStatus = "DRAFT" | "POSTED" | "VOIDED";

export interface JournalEntryRow {
  id: string;
  entry_number: number;
  transaction_date: string;
  posted_at: string;
  payee: string | null;
  description: string;
  status: EntryStatus;
  reversed_entry_id: string | null;
  metadata: Record<string, unknown>;
  version_id: number;
  splits: Array<{
    id: string;
    account_id: string;
    memo: string | null;
    debit: string;
    credit: string;
    currency: string;
    exchange_rate: string;
    reconciliation_status: string;
  }>;
}

interface InvoiceMeta {
  kind: InvoiceKind;
  seller: string | null;
  buyer: string | null;
  note: string | null;
  lines: Array<{ title: string; quantity: string; unit_price: string; line_total: string }>;
}

interface EditLine {
  title: string;
  quantity: string;
  unit_price: string;
}

const KIND_LABEL: Record<InvoiceKind, string> = {
  sale: "فاکتور فروش",
  purchase: "فاکتور خرید",
};

function invoiceMeta(entry: JournalEntryRow): InvoiceMeta | null {
  const meta = entry.metadata?.invoice;
  if (!meta || typeof meta !== "object") return null;
  const invoice = meta as InvoiceMeta;
  if (!Array.isArray(invoice.lines)) return null;
  return invoice;
}

/** Persian digits and separators are tolerated in the amount inputs. */
function toman(value: string): string {
  try {
    return rialToToman(value)
      .toFixed(4)
      .replace(/\.?0+$/, "");
  } catch {
    return value;
  }
}

function linesFrom(invoice: InvoiceMeta): EditLine[] {
  return invoice.lines.map((line) => ({
    title: line.title,
    quantity: String(Number(line.quantity) || 1),
    unit_price: toman(line.unit_price),
  }));
}

function lineTotal(line: EditLine): string {
  return moneyString(parseAmount(line.quantity).times(parseAmount(line.unit_price)));
}

function EntryStatusBadge({ status }: { status: EntryStatus }): React.JSX.Element {
  const label = status === "POSTED" ? "ثبت‌شده" : status === "VOIDED" ? "ابطال‌شده" : "پیش‌نویس";
  return (
    <Badge
      data-testid="entry-status"
      variant={status === "POSTED" ? "success" : status === "VOIDED" ? "destructive" : "secondary"}
    >
      {label}
    </Badge>
  );
}

export function JournalEntryDrawer({
  entry,
  accounts,
  onClose,
}: {
  entry: JournalEntryRow;
  /** account_id → «code — name» for the read-only line list. */
  accounts: Map<string, string>;
  onClose: () => void;
}): React.JSX.Element {
  const { calendar } = useCalendar();
  const queryClient = useQueryClient();
  const invoice = invoiceMeta(entry);

  const [editing, setEditing] = React.useState(false);
  const [date, setDate] = React.useState(entry.transaction_date);
  const [description, setDescription] = React.useState(entry.description);
  const [payee, setPayee] = React.useState(entry.payee ?? "");
  const [seller, setSeller] = React.useState(invoice?.seller ?? "");
  const [buyer, setBuyer] = React.useState(invoice?.buyer ?? "");
  const [note, setNote] = React.useState(invoice?.note ?? "");
  const [lines, setLines] = React.useState<EditLine[]>(
    invoice ? linesFrom(invoice) : [{ title: "", quantity: "1", unit_price: "" }],
  );
  // A hand-written two-line entry (one debit, one credit) can have its amount
  // corrected without ever showing the user debit/credit: both sides move
  // together, so the entry stays balanced by construction.
  const simple =
    !invoice &&
    entry.splits.length === 2 &&
    entry.splits.every((split) => split.currency === "IRR" && Number(split.exchange_rate) === 1);
  const [amount, setAmount] = React.useState("");
  const [voiding, setVoiding] = React.useState(false);
  const [voidReason, setVoidReason] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const closeRef = React.useRef<HTMLButtonElement>(null);

  React.useEffect(() => {
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // A different entry in the same drawer must not keep the previous text.
  React.useEffect(() => {
    setEditing(false);
    setVoiding(false);
    setError(null);
  }, [entry.id]);

  // After a save/unpost the server sends a new version; refresh the fields but
  // stay in the editor the user is already in.
  React.useEffect(() => {
    setDate(entry.transaction_date);
    setDescription(entry.description);
    setPayee(entry.payee ?? "");
    setSeller(invoice?.seller ?? "");
    setBuyer(invoice?.buyer ?? "");
    setNote(invoice?.note ?? "");
    setLines(invoice ? linesFrom(invoice) : [{ title: "", quantity: "1", unit_price: "" }]);
    const debit = entry.splits.find((row) => Number(row.debit) > 0);
    setAmount(debit ? toman(debit.debit) : "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entry.id, entry.version_id]);

  function refresh(): void {
    void queryClient.invalidateQueries({ queryKey: ["journal-entries"] });
    void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    void queryClient.invalidateQueries({ queryKey: ["reports"] });
    void queryClient.invalidateQueries({ queryKey: ["accounts"] });
  }

  function fail(e: unknown): void {
    if (e instanceof ApiError && e.isStale) {
      setError("این سند هم‌زمان تغییر کرده است؛ فهرست تازه شد. یک‌بار دیگر تلاش کنید.");
      refresh();
      return;
    }
    setError(e instanceof Error ? e.message : "عملیات انجام نشد.");
  }

  const post = useMutation({
    mutationFn: async () => {
      const res = await api.POST("/api/v1/journal-entries/{entry_id}/post", {
        params: { path: { entry_id: entry.id } },
      });
      if (res.error) throw await parseError(res.response);
      return res.data;
    },
    onSuccess: refresh,
    onError: fail,
  });

  const unpost = useMutation({
    mutationFn: async () => {
      const res = await api.POST("/api/v1/journal-entries/{entry_id}/unpost", {
        params: { path: { entry_id: entry.id } },
      });
      if (res.error) throw await parseError(res.response);
      return res.data;
    },
    onSuccess: () => {
      refresh();
      setEditing(true);
    },
    onError: fail,
  });

  const voidEntry = useMutation({
    mutationFn: async (reason: string) => {
      const res = await api.POST("/api/v1/journal-entries/{entry_id}/void", {
        params: { path: { entry_id: entry.id }, query: { reason } },
      });
      if (res.error) throw await parseError(res.response);
      return res.data;
    },
    onSuccess: () => {
      setVoiding(false);
      setEditing(false);
      refresh();
    },
    onError: fail,
  });

  const save = useMutation({
    mutationFn: async () => {
      setError(null);
      if (!invoice) {
        // Hand-written entry: header fields, plus the amount when the entry is
        // a plain two-line one (both sides move together, so it stays balanced).
        const corrected = parseAmount(amount);
        if (simple && corrected.lte(0)) throw new Error("مبلغ سند باید بزرگ‌تر از صفر باشد.");
        const amountRial = moneyString(tomanToRial(corrected));
        const res = await api.PUT("/api/v1/journal-entries/{entry_id}", {
          params: { path: { entry_id: entry.id } },
          body: {
            transaction_date: date,
            description: description.trim(),
            payee: payee.trim() || null,
            version_id: entry.version_id,
            ...(simple
              ? {
                  splits: entry.splits.map((split) => ({
                    account_id: split.account_id,
                    memo: split.memo ?? undefined,
                    debit: Number(split.debit) > 0 ? amountRial : "0.0000",
                    credit: Number(split.credit) > 0 ? amountRial : "0.0000",
                    currency: split.currency,
                    exchange_rate: split.exchange_rate,
                  })),
                }
              : {}),
          },
        });
        if (res.error) throw await parseError(res.response);
        return res.data;
      }
      const parsed = invoiceFormSchema.safeParse({
        kind: invoice.kind,
        date,
        seller,
        buyer,
        note,
        lines,
      });
      if (!parsed.success) {
        throw new Error(parsed.error.issues[0]?.message ?? "اطلاعات سند کامل نیست.");
      }
      const res = await api.PUT("/api/v1/journal-entries/{entry_id}/invoice", {
        params: { path: { entry_id: entry.id } },
        body: {
          kind: invoice.kind,
          transaction_date: date,
          seller: parsed.data.seller?.trim() || null,
          buyer: parsed.data.buyer?.trim() || null,
          note: parsed.data.note?.trim() || null,
          lines: parsed.data.lines.map((line) => ({
            title: line.title.trim(),
            quantity: moneyString(parseAmount(line.quantity)),
            unit_price: toMoneyString(tomanToRial(parseAmount(line.unit_price))),
          })),
          version_id: entry.version_id,
        },
      });
      if (res.error) throw await parseError(res.response);
      return res.data;
    },
    onSuccess: () => {
      setEditing(false);
      refresh();
    },
    onError: fail,
  });

  const busy = post.isPending || unpost.isPending || voidEntry.isPending || save.isPending;
  const total = lines.reduce(
    (sum, line) => sum.plus(parseAmount(lineTotal(line))),
    parseAmount("0"),
  );

  function updateLine(index: number, patch: Partial<EditLine>): void {
    setLines((current) => current.map((line, i) => (i === index ? { ...line, ...patch } : line)));
  }

  return (
    <div className="fixed inset-0 z-50 flex print:hidden" data-testid="entry-drawer">
      <button
        type="button"
        className="flex-1 bg-black/30"
        aria-label="بستن سند"
        onClick={onClose}
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={`سند شماره ${entry.entry_number}`}
        className="h-full w-full max-w-2xl overflow-y-auto bg-background p-4 shadow-xl"
      >
        <div className="mb-3 flex items-start justify-between gap-2">
          <div className="space-y-1">
            <h2 className="text-lg font-bold">
              سند شمارهٔ <span className="num">{faNumber(entry.entry_number)}</span>
            </h2>
            <p className="num text-xs text-muted-foreground">
              {faDate(entry.transaction_date, calendar)}
              {invoice ? ` — ${KIND_LABEL[invoice.kind]}` : ""}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <EntryStatusBadge status={entry.status} />
            <button
              ref={closeRef}
              type="button"
              className="rounded border px-3 py-1 text-sm"
              onClick={onClose}
              data-testid="entry-drawer-close"
            >
              بستن
            </button>
          </div>
        </div>

        {error && (
          <p
            role="alert"
            className="mb-3 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive"
            data-testid="entry-error"
          >
            {error}
          </p>
        )}

        {!editing && (
          <>
            <dl className="mb-3 grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-muted-foreground">شرح</dt>
                <dd data-testid="entry-description">{entry.description}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">طرف حساب</dt>
                <dd data-testid="entry-payee">{entry.payee || "—"}</dd>
              </div>
              {invoice && (
                <>
                  <div>
                    <dt className="text-muted-foreground">فروشنده</dt>
                    <dd>{invoice.seller || "—"}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">خریدار</dt>
                    <dd>{invoice.buyer || "—"}</dd>
                  </div>
                </>
              )}
            </dl>

            {invoice ? (
              <table className="mb-3 w-full text-sm" aria-label="ردیف‌های سند">
                <thead>
                  <tr className="border-b text-muted-foreground">
                    <th scope="col" className="py-1 text-start font-medium">
                      کالا یا خدمت
                    </th>
                    <th scope="col" className="py-1 text-end font-medium">
                      تعداد
                    </th>
                    <th scope="col" className="py-1 text-end font-medium">
                      مبلغ واحد
                    </th>
                    <th scope="col" className="py-1 text-end font-medium">
                      مبلغ
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {invoice.lines.map((line, index) => (
                    <tr key={`${line.title}-${index}`} data-testid="entry-line">
                      <td className="py-1">{line.title}</td>
                      <td className="num py-1 text-end">
                        {faNumber(String(Number(line.quantity)))}
                      </td>
                      <td className="py-1 text-end">
                        <Money value={line.unit_price} />
                      </td>
                      <td className="py-1 text-end">
                        <Money value={line.line_total} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <ul className="mb-3 space-y-1 text-sm" aria-label="ردیف‌های سند">
                {entry.splits.map((split) => (
                  <li key={split.id} className="flex justify-between gap-4">
                    <span>{accounts.get(split.account_id) ?? split.account_id}</span>
                    <span>
                      <Money
                        value={Number(split.debit) > 0 ? split.debit : split.credit}
                        signedColors
                        direction={Number(split.debit) > 0 ? "inflow" : "outflow"}
                      />
                    </span>
                  </li>
                ))}
              </ul>
            )}

            {voiding && (
              <div className="mb-3 space-y-2 rounded-md border p-3" data-testid="entry-void-form">
                <Label htmlFor="void-reason">دلیل ابطال</Label>
                <Input
                  id="void-reason"
                  data-testid="entry-void-reason"
                  value={voidReason}
                  onChange={(event) => setVoidReason(event.target.value)}
                  placeholder="مثلاً اشتباه در مبلغ یا تاریخ"
                />
                <div className="flex gap-2">
                  <Button
                    type="button"
                    variant="destructive"
                    data-testid="entry-void-confirm"
                    disabled={busy || !voidReason.trim()}
                    onClick={() => voidEntry.mutate(voidReason.trim())}
                  >
                    ابطال سند
                  </Button>
                  <Button type="button" variant="ghost" onClick={() => setVoiding(false)}>
                    انصراف
                  </Button>
                </div>
              </div>
            )}

            <div className="flex flex-wrap gap-2 border-t pt-3">
              {entry.status === "DRAFT" && (
                <Button
                  type="button"
                  data-testid="entry-post"
                  disabled={busy}
                  onClick={() => post.mutate()}
                >
                  ثبت در دفاتر
                </Button>
              )}
              {entry.status === "POSTED" && (
                <Button
                  type="button"
                  variant="outline"
                  data-testid="entry-unpost"
                  disabled={busy}
                  onClick={() => unpost.mutate()}
                >
                  برگشت به پیش‌نویس
                </Button>
              )}
              {invoice && (
                <a
                  className="inline-flex h-9 items-center rounded-md border border-input px-4 text-sm hover:bg-accent"
                  href={`/api/v1/journal-entries/${entry.id}/invoice.pdf`}
                  target="_blank"
                  rel="noreferrer"
                  data-testid="entry-print-invoice"
                >
                  چاپ فاکتور
                </a>
              )}
              {entry.status !== "VOIDED" && (
                <Button
                  type="button"
                  variant="outline"
                  data-testid="entry-edit"
                  disabled={busy}
                  onClick={() => setEditing(true)}
                >
                  ویرایش سند
                </Button>
              )}
              {entry.status === "POSTED" && (
                <Button
                  type="button"
                  variant="destructive"
                  data-testid="entry-void"
                  disabled={busy}
                  onClick={() => setVoiding(true)}
                >
                  ابطال سند
                </Button>
              )}
              {entry.status === "VOIDED" && (
                <p className="text-sm text-muted-foreground" data-testid="entry-voided-note">
                  این سند ابطال شده است و دیگر در دفاتر و صورت‌های مالی نمی‌آید.
                </p>
              )}
            </div>
          </>
        )}

        {editing && (
          <form
            className="space-y-3"
            data-testid="entry-editor"
            onSubmit={(event) => {
              event.preventDefault();
              save.mutate();
            }}
          >
            {entry.status === "POSTED" && (
              <p className="rounded-md bg-secondary px-3 py-2 text-xs text-muted-foreground">
                این سند در دفاتر ثبت شده است. با ذخیره، سند از ثبت خارج و با مقادیر تازه دوباره ثبت
                می‌شود؛ نسخهٔ قبلی در تاریخچهٔ تغییرات می‌ماند.
              </p>
            )}
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <CalendarInput
                  id="entry-date"
                  label="تاریخ"
                  value={date}
                  onChange={(iso) => setDate(iso)}
                />
              </div>
              {!invoice && (
                <>
                  <div className="space-y-1">
                    <Label htmlFor="entry-payee-input">طرف حساب</Label>
                    <Input
                      id="entry-payee-input"
                      data-testid="entry-payee-input"
                      value={payee}
                      onChange={(event) => setPayee(event.target.value)}
                    />
                  </div>
                  {simple && (
                    <div className="space-y-1">
                      <Label htmlFor="entry-amount-input">مبلغ سند (تومان)</Label>
                      <Input
                        id="entry-amount-input"
                        data-testid="entry-amount-input"
                        value={amount}
                        onChange={(event) => setAmount(event.target.value)}
                      />
                    </div>
                  )}
                  <div className="space-y-1 sm:col-span-2">
                    <Label htmlFor="entry-description-input">شرح</Label>
                    <Input
                      id="entry-description-input"
                      data-testid="entry-description-input"
                      value={description}
                      onChange={(event) => setDescription(event.target.value)}
                    />
                  </div>
                </>
              )}
              {invoice && (
                <>
                  <div className="space-y-1">
                    <Label htmlFor="entry-seller">
                      {invoice.kind === "sale" ? "فروشنده" : "فروشنده (الزامی)"}
                    </Label>
                    <Input
                      id="entry-seller"
                      data-testid="entry-seller"
                      value={seller}
                      onChange={(event) => setSeller(event.target.value)}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="entry-buyer">
                      {invoice.kind === "sale" ? "خریدار (الزامی)" : "خریدار"}
                    </Label>
                    <Input
                      id="entry-buyer"
                      data-testid="entry-buyer"
                      value={buyer}
                      onChange={(event) => setBuyer(event.target.value)}
                    />
                  </div>
                  <div className="space-y-1 sm:col-span-2">
                    <Label htmlFor="entry-note">یادداشت</Label>
                    <Input
                      id="entry-note"
                      value={note}
                      onChange={(event) => setNote(event.target.value)}
                    />
                  </div>
                </>
              )}
            </div>

            {invoice && (
              <div className="space-y-2">
                <p className="text-sm font-medium">ردیف‌های سند</p>
                {lines.map((line, index) => (
                  <div
                    key={index}
                    className="grid grid-cols-12 items-end gap-2"
                    data-testid="entry-line-form"
                  >
                    <div className="col-span-5 space-y-1">
                      <Label htmlFor={`entry-line-title-${index}`}>کالا یا خدمت</Label>
                      <Input
                        id={`entry-line-title-${index}`}
                        value={line.title}
                        onChange={(event) => updateLine(index, { title: event.target.value })}
                      />
                    </div>
                    <div className="col-span-2 space-y-1">
                      <Label htmlFor={`entry-line-qty-${index}`}>تعداد</Label>
                      <Input
                        id={`entry-line-qty-${index}`}
                        value={line.quantity}
                        onChange={(event) => updateLine(index, { quantity: event.target.value })}
                      />
                    </div>
                    <div className="col-span-3 space-y-1">
                      <Label htmlFor={`entry-line-price-${index}`}>مبلغ واحد (تومان)</Label>
                      <Input
                        id={`entry-line-price-${index}`}
                        value={line.unit_price}
                        onChange={(event) => updateLine(index, { unit_price: event.target.value })}
                      />
                    </div>
                    <div className="col-span-2 flex items-center justify-between gap-1 pb-2 text-xs">
                      <Money value={lineTotal(line)} currency="TOMAN" hideCurrency />
                      {lines.length > 1 && (
                        <button
                          type="button"
                          className="text-destructive"
                          aria-label="حذف ردیف"
                          onClick={() =>
                            setLines((current) => current.filter((_, i) => i !== index))
                          }
                        >
                          ✕
                        </button>
                      )}
                    </div>
                  </div>
                ))}
                <div className="flex items-center justify-between">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      setLines((current) => [
                        ...current,
                        { title: "", quantity: "1", unit_price: "" },
                      ])
                    }
                  >
                    افزودن ردیف
                  </Button>
                  <p className="text-sm">
                    مبلغ کل: <Money value={total.toFixed(4)} currency="TOMAN" />
                  </p>
                </div>
              </div>
            )}

            {!invoice && !simple && (
              <p className="text-xs text-muted-foreground">
                این سند بیش از دو ردیف دارد؛ تاریخ، شرح و طرف حساب آن قابل ویرایش است. برای تغییر
                حساب‌ها و مبلغ‌ها، آن را ابطال کنید و سند تازه بسازید.
              </p>
            )}

            <div className="flex gap-2 border-t pt-3">
              <Button type="submit" data-testid="entry-save" disabled={busy}>
                {save.isPending ? "در حال ذخیره…" : "ذخیرهٔ اصلاح"}
              </Button>
              <Button type="button" variant="ghost" onClick={() => setEditing(false)}>
                انصراف
              </Button>
            </div>
          </form>
        )}
      </aside>
    </div>
  );
}
