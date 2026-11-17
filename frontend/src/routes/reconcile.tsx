/**
 * تطبیق بانکی — matching the bank's statement against the posted books.
 *
 * Every row and number here is the owner's own data: the statement lines that
 * the import screen stored, the posted movements of the chosen bank/cash
 * account, and the reconciliation session that ties the two together. The
 * previous version printed invented rows («شرکت آریا», «پایه موبایل») and its
 * buttons only changed what was on screen; nothing here is invented and every
 * button writes to the server:
 *
 *   «شروع تطبیق»          creates a real session (account + date + balances)
 *   «تأیید پیشنهاد»       links the suggested split, marks the line matched
 *   «تطبیق»               links the book movement chosen for the selected line
 *   «نادیده گرفتن»        persists IGNORED on the statement line
 *   «بازگردانی»           puts an ignored line back into the work list
 *   «تأیید همه پیشنهادها» links every high-confidence suggestion
 *   «تکمیل تطبیق»         completes the session (idempotent on the server)
 *   «بازگشایی»            sudo-guarded reopen of a completed session
 *   «انصراف از جلسه»      abandons an open session
 *
 * A failed request says the state is unknown and offers a retry; an empty
 * result says there is nothing yet and points at the screen that creates it.
 */
import * as React from "react";
import { Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Link2, RotateCcw, Undo2, X } from "lucide-react";
import { api, parseError } from "@/api/client";
import { trackEvent } from "@/lib/analytics";
import { useCalendar } from "@/lib/calendar-settings";
import { tehranToday } from "@/lib/calendar";
import { faDate, faDigits, faNumber } from "@/lib/fa";
import { toDecimal } from "@/lib/money";
import {
  CONFIDENCE_LABELS,
  confidenceOf,
  scoreMatch,
  type Confidence,
  type MatchCandidate,
} from "@/lib/similarity";
import { Money } from "@/components/money";
import { QueryNotice } from "@/components/query-notice";
import { CalendarInput } from "@/components/calendar-input";
import { useOptionalRequestSudo } from "@/components/sudo-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

// ---------------------------------------------------------------- types ---
interface Account {
  id: string;
  code: string;
  name: string;
  account_type: string;
  is_placeholder: boolean;
  is_active: boolean;
}

interface StatementLine {
  id: string;
  account_id: string | null;
  value_date: string;
  payee_raw: string | null;
  description_raw: string | null;
  amount_scaled: number;
  currency: string;
  status: "UNMATCHED" | "SUGGESTED" | "MATCHED" | "IGNORED";
}

interface LedgerRow {
  entry_id: string;
  split_id: string;
  entry_number: number;
  transaction_date: string;
  description: string;
  payee: string | null;
  debit: string;
  credit: string;
  reconciliation_status: "UNRECONCILED" | "CLEARED" | "RECONCILED";
}

interface LedgerRead {
  rows: LedgerRow[];
  opening_balance: string;
  closing_balance: string;
}

interface Session {
  id: string;
  account_id: string;
  statement_date: string;
  beginning_balance: string;
  ending_balance: string;
  status: "OPEN" | "COMPLETED" | "ABANDONED";
  completed_at: string | null;
  created_at: string;
}

interface Progress {
  linked_total: string;
  expected_delta: string;
  balanced: boolean;
}

/** A statement line credits a book movement when amount and date agree closely. */
const CONFIDENT_DAYS = 7;

interface RankedMatch {
  row: LedgerRow;
  score: number;
  confidence: Confidence;
  amountMatch: boolean;
  dateDeltaDays: number | null;
}

interface Suggestion {
  ranked: RankedMatch[];
  best: RankedMatch | null;
}

const STATUS_LABEL: Record<StatementLine["status"], string> = {
  UNMATCHED: "تطبیق‌نشده",
  SUGGESTED: "پیشنهاد",
  MATCHED: "تطبیق‌شده",
  IGNORED: "نادیده‌گرفته",
};

const CONFIDENCE_BADGE: Record<Confidence, "success" | "warning" | "outline"> = {
  auto: "success",
  suggested: "warning",
  manual: "outline",
};

/** Bank amounts are stored scaled ×10 000, signed (negative = money out). */
function bankAmountScaled(line: StatementLine): string {
  return toDecimal(line.amount_scaled).dividedBy(10_000).toFixed(4);
}

/** What the bank account actually moved: debit − credit. */
function bookAmount(row: LedgerRow): string {
  return toDecimal(row.debit).minus(toDecimal(row.credit)).toFixed(4);
}

function lineText(line: StatementLine): string {
  return line.description_raw ?? line.payee_raw ?? "—";
}

function asCandidate(line: StatementLine): MatchCandidate {
  return {
    amount: bankAmountScaled(line),
    dateIso: line.value_date,
    description: [line.payee_raw, line.description_raw].filter(Boolean).join(" "),
    refNo: null,
  };
}

function asCandidateBook(row: LedgerRow): MatchCandidate {
  return {
    amount: bookAmount(row),
    dateIso: row.transaction_date,
    description: [row.description, row.payee].filter(Boolean).join(" "),
    refNo: null,
  };
}

/** Cash and bank accounts are the ones that carry a statement: 101x / 102x. */
function isStatementAccount(account: Account): boolean {
  return (
    account.is_active &&
    !account.is_placeholder &&
    account.account_type === "ASSET" &&
    (account.code.startsWith("101") || account.code.startsWith("102"))
  );
}

export function ReconcilePage(): React.JSX.Element {
  const { calendar } = useCalendar();
  const queryClient = useQueryClient();
  const requestSudo = useOptionalRequestSudo();
  const today = tehranToday();

  const [accountId, setAccountId] = React.useState("");
  const [statementDate, setStatementDate] = React.useState(today);
  const [beginning, setBeginning] = React.useState("0");
  const [ending, setEnding] = React.useState("0");
  const [selectedLine, setSelectedLine] = React.useState<string | null>(null);
  const [showIgnored, setShowIgnored] = React.useState(false);
  const [confirmingComplete, setConfirmingComplete] = React.useState(false);
  const [notice, setNotice] = React.useState<{ ok: boolean; text: string } | null>(null);

  const fail = (error: unknown, fallback: string): void => {
    const text = error instanceof Error && error.message ? error.message : fallback;
    setNotice({ ok: false, text });
  };

  // ------------------------------------------------------------ queries ---
  const accountsQuery = useQuery({
    queryKey: ["reconcile", "accounts"],
    queryFn: async () => {
      const res = await api.GET("/api/v1/accounts");
      if (res.error) throw await parseError(res.response);
      return (res.data as unknown as Account[]).filter(isStatementAccount);
    },
  });

  // Pick the first statement account once the list arrives.
  React.useEffect(() => {
    if (!accountId && accountsQuery.data?.length) {
      setAccountId(accountsQuery.data[0].id);
    }
  }, [accountId, accountsQuery.data]);

  const sessionsQuery = useQuery({
    queryKey: ["reconcile", "sessions", accountId],
    enabled: Boolean(accountId),
    queryFn: async () => {
      const res = await api.GET("/api/v1/reconciliation/sessions", {
        params: { query: { account_id: accountId } },
      });
      if (res.error) throw await parseError(res.response);
      return res.data as unknown as Session[];
    },
  });

  const linesQuery = useQuery({
    queryKey: ["reconcile", "lines", accountId],
    enabled: Boolean(accountId),
    queryFn: async () => {
      const res = await api.GET("/api/v1/imports/lines", {
        params: { query: { account_id: accountId } },
      });
      if (res.error) throw await parseError(res.response);
      return res.data as unknown as StatementLine[];
    },
  });

  const session = React.useMemo(
    () => (sessionsQuery.data ?? []).find((s) => s.status === "OPEN") ?? null,
    [sessionsQuery.data],
  );
  const lastClosed = React.useMemo(
    () =>
      (sessionsQuery.data ?? []).find(
        (s) => s.status === "COMPLETED" || s.status === "ABANDONED",
      ) ?? null,
    [sessionsQuery.data],
  );

  const allLines = React.useMemo(() => linesQuery.data ?? [], [linesQuery.data]);

  /** The period the statement covers — taken from the lines themselves. */
  const period = React.useMemo(() => {
    const dates = allLines
      .map((line) => line.value_date)
      .filter(Boolean)
      .sort((a, b) => a.localeCompare(b, "en"));
    if (dates.length) return { start: dates[0], end: dates[dates.length - 1] };
    return { start: `${today.slice(0, 7)}-01`, end: today };
  }, [allLines, today]);

  const ledgerQuery = useQuery({
    queryKey: ["reconcile", "ledger", accountId, period.start, period.end],
    enabled: Boolean(accountId),
    queryFn: async () => {
      const res = await api.GET("/api/v1/accounts/{account_id}/ledger", {
        params: {
          path: { account_id: accountId },
          query: { start: period.start, end: period.end },
        },
      });
      if (res.error) throw await parseError(res.response);
      return res.data as unknown as LedgerRead;
    },
  });

  const progressQuery = useQuery({
    queryKey: ["reconcile", "progress", session?.id],
    enabled: Boolean(session?.id),
    queryFn: async () => {
      const res = await api.GET("/api/v1/reconciliation/sessions/{session_id}/progress", {
        params: { path: { session_id: session!.id } },
      });
      if (res.error) throw await parseError(res.response);
      return res.data as unknown as Progress;
    },
  });

  const invalidate = (): void => {
    void queryClient.invalidateQueries({ queryKey: ["reconcile"] });
  };

  // ---------------------------------------------------------- mutations ---
  const startSession = useMutation({
    mutationFn: async () => {
      if (!accountId) throw new Error("حساب بانکی را انتخاب کنید.");
      const res = await api.POST("/api/v1/reconciliation/sessions", {
        body: {
          account_id: accountId,
          statement_date: statementDate,
          beginning_balance: beginning.trim() || "0",
          ending_balance: ending.trim() || "0",
        },
      });
      if (res.error) throw await parseError(res.response);
      return res.data as unknown as Session;
    },
    onSuccess: (created) => {
      setNotice({ ok: true, text: "جلسه تطبیق ساخته شد؛ حالا ردیف‌ها را تطبیق دهید." });
      trackEvent("reconciliation_started", {
        route: "/reconcile",
        status: created.status,
      });
      invalidate();
    },
    onError: (error) => fail(error, "ساخت جلسه تطبیق ناموفق بود."),
  });

  const linkMatch = useMutation({
    mutationFn: async (payload: { line: StatementLine; row: LedgerRow }) => {
      if (!session) throw new Error("ابتدا جلسه تطبیق را شروع کنید.");
      const linked = await api.POST(
        "/api/v1/reconciliation/sessions/{session_id}/splits/{split_id}/link",
        {
          params: {
            path: { session_id: session.id, split_id: payload.row.split_id },
          },
        },
      );
      if (linked.error) throw await parseError(linked.response);
      const marked = await api.POST("/api/v1/imports/lines/{line_id}/status", {
        params: { path: { line_id: payload.line.id } },
        body: { status: "MATCHED" },
      });
      if (marked.error) throw await parseError(marked.response);
      return payload.row;
    },
    onSuccess: (row) => {
      setNotice({ ok: true, text: `ردیف بانکی با سند ${faDigits(row.entry_number)} تطبیق شد ✓` });
      setSelectedLine(null);
      trackEvent("reconciliation_linked", { route: "/reconcile", entity: "split" });
      invalidate();
    },
    onError: (error) => fail(error, "تطبیق ردیف ناموفق بود."),
  });

  const ignoreLine = useMutation({
    mutationFn: async (line: StatementLine) => {
      const res = await api.POST("/api/v1/imports/lines/{line_id}/status", {
        params: { path: { line_id: line.id } },
        body: { status: "IGNORED" },
      });
      if (res.error) throw await parseError(res.response);
      return line;
    },
    onSuccess: () => {
      setNotice({ ok: true, text: "ردیف نادیده گرفته شد؛ در فهرست نادیده‌شده‌ها می‌ماند." });
      setSelectedLine(null);
      invalidate();
    },
    onError: (error) => fail(error, "نادیده گرفتن ردیف ناموفق بود."),
  });

  const restoreLine = useMutation({
    mutationFn: async (line: StatementLine) => {
      const res = await api.POST("/api/v1/imports/lines/{line_id}/status", {
        params: { path: { line_id: line.id } },
        body: { status: "UNMATCHED" },
      });
      if (res.error) throw await parseError(res.response);
      return line;
    },
    onSuccess: () => {
      setNotice({ ok: true, text: "ردیف به فهرست کار برگشت." });
      invalidate();
    },
    onError: (error) => fail(error, "بازگردانی ردیف ناموفق بود."),
  });

  const completeSession = useMutation({
    mutationFn: async () => {
      if (!session) throw new Error("جلسه‌ای برای تکمیل وجود ندارد.");
      const res = await api.POST("/api/v1/reconciliation/sessions/{session_id}/complete", {
        params: { path: { session_id: session.id } },
        headers: { "Idempotency-Key": crypto.randomUUID() },
      });
      if (res.error) throw await parseError(res.response);
      return res.data as unknown as Session;
    },
    onSuccess: () => {
      setConfirmingComplete(false);
      setNotice({ ok: true, text: "تطبیق تکمیل شد ✓" });
      trackEvent("reconciliation_completed", { route: "/reconcile", status: "ok" });
      invalidate();
    },
    onError: (error) => {
      setConfirmingComplete(false);
      fail(error, "تکمیل تطبیق ناموفق بود.");
    },
  });

  const reopenSession = useMutation({
    mutationFn: async () => {
      if (!lastClosed) throw new Error("جلسه بسته‌ای وجود ندارد.");
      if (requestSudo) await requestSudo();
      const res = await api.POST("/api/v1/reconciliation/sessions/{session_id}/reopen", {
        params: { path: { session_id: lastClosed.id } },
      });
      if (res.error) throw await parseError(res.response);
      return res.data as unknown as Session;
    },
    onSuccess: () => {
      setNotice({ ok: true, text: "جلسه بازگشایی شد؛ می‌توانید دوباره تطبیق دهید." });
      invalidate();
    },
    onError: (error) => fail(error, "بازگشایی جلسه ناموفق بود."),
  });

  const abandonSession = useMutation({
    mutationFn: async () => {
      if (!session) throw new Error("جلسه‌ای برای انصراف وجود ندارد.");
      const res = await api.POST("/api/v1/reconciliation/sessions/{session_id}/abandon", {
        params: { path: { session_id: session.id } },
      });
      if (res.error) throw await parseError(res.response);
      return res.data as unknown as Session;
    },
    onSuccess: () => {
      setNotice({ ok: true, text: "از جلسه صرف‌نظر شد." });
      invalidate();
    },
    onError: (error) => fail(error, "انصراف از جلسه ناموفق بود."),
  });

  // ------------------------------------------------------------ matching ---
  const openRows = React.useMemo(
    () =>
      (ledgerQuery.data?.rows ?? []).filter((row) => row.reconciliation_status === "UNRECONCILED"),
    [ledgerQuery.data],
  );
  const alreadyReconciled = (ledgerQuery.data?.rows ?? []).length - openRows.length;

  const workLines = React.useMemo(
    () => allLines.filter((line) => line.status === "UNMATCHED" || line.status === "SUGGESTED"),
    [allLines],
  );
  const ignoredLines = React.useMemo(
    () => allLines.filter((line) => line.status === "IGNORED"),
    [allLines],
  );
  const matchedLines = React.useMemo(
    () => allLines.filter((line) => line.status === "MATCHED"),
    [allLines],
  );

  /** Best book movement for every open statement line, plus the full ranking. */
  const suggestions = React.useMemo(() => {
    const rows = openRows.map((row) => ({ row, candidate: asCandidateBook(row) }));
    const map = new Map<string, Suggestion>();
    for (const line of workLines) {
      const candidate = asCandidate(line);
      const ranked: RankedMatch[] = rows
        .map(({ row, candidate: bookCandidate }) => {
          const match = scoreMatch(candidate, bookCandidate);
          return {
            row,
            score: match.score,
            confidence: confidenceOf(match),
            amountMatch: match.amountMatch,
            dateDeltaDays: match.dateDeltaDays,
          };
        })
        .sort((a, b) => b.score - a.score);
      const top = ranked[0];
      map.set(line.id, {
        ranked,
        best: top && top.confidence !== "manual" ? top : null,
      });
    }
    return map;
  }, [openRows, workLines]);

  /**
   * What the owner can approve in one go: the same amount and a date within a
   * week. Confidence alone is not enough — a description alone should never
   * clear a line, money is what must line up.
   */
  const confidentMatches = React.useMemo(
    () =>
      workLines.flatMap((line) => {
        const best = suggestions.get(line.id)?.best;
        const closeInTime = (best?.dateDeltaDays ?? Infinity) <= CONFIDENT_DAYS;
        return best && best.amountMatch && closeInTime ? [{ line, row: best.row }] : [];
      }),
    [workLines, suggestions],
  );

  const selected = selectedLine ? workLines.find((line) => line.id === selectedLine) : undefined;

  const linkedTotal = progressQuery.data?.linked_total ?? "0";
  const expectedDelta = progressQuery.data?.expected_delta ?? "0";
  const difference = toDecimal(expectedDelta).minus(linkedTotal);
  const balanced = progressQuery.data?.balanced ?? false;

  const busy =
    linkMatch.isPending ||
    ignoreLine.isPending ||
    restoreLine.isPending ||
    completeSession.isPending ||
    abandonSession.isPending ||
    reopenSession.isPending ||
    startSession.isPending;

  const retryAll = (): void => {
    for (const query of [accountsQuery, sessionsQuery, linesQuery, ledgerQuery, progressQuery]) {
      void query.refetch();
    }
  };

  // --------------------------------------------------------------- render ---
  const accounts = accountsQuery.data ?? [];

  return (
    <div className="space-y-4" dir="rtl" data-testid="reconcile-page">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold">تطبیق بانکی</h1>
          <p className="text-xs text-muted-foreground">
            ردیف‌های صورت‌حساب بانک را با اسناد ثبت‌شده در دفتر تطبیق دهید؛ هر تغییر روی همین نصب
            ذخیره می‌شود.
          </p>
        </div>
        <div className="flex items-center gap-4 rounded-lg border bg-card px-4 py-2">
          <div>
            <div className="text-xs text-muted-foreground">مغایرت زنده</div>
            <span data-testid="live-difference">
              <Money value={difference.toFixed(4)} signedColors accounting={false} />
            </span>
          </div>
          <div>
            <div className="text-xs text-muted-foreground">تطبیق‌یافته</div>
            <span className="num" data-testid="matched-count">
              {faNumber(matchedLines.length)} / {faNumber(allLines.length)}
            </span>
          </div>
        </div>
      </div>

      {notice && (
        <p
          role={notice.ok ? "status" : "alert"}
          data-testid="reconcile-notice"
          className={`rounded-md px-3 py-2 text-sm ${
            notice.ok ? "bg-positive/10 text-positive" : "bg-destructive/10 text-destructive"
          }`}
        >
          {notice.text}
        </p>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">حساب و دوره صورت‌حساب</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <QueryNotice query={accountsQuery} />
          {accountsQuery.isSuccess && accounts.length === 0 && (
            <p className="text-sm text-muted-foreground" data-testid="reconcile-empty-accounts">
              حسابی برای تطبیق نیست. یک حساب بانکی (کد ۱۰۲۰) در{" "}
              <Link to="/accounts" className="text-primary underline">
                حساب‌ها
              </Link>{" "}
              بسازید.
            </p>
          )}
          {accounts.length > 0 && (
            <div className="grid gap-3 md:grid-cols-4">
              <div className="space-y-1">
                <Label htmlFor="reconcile-account">حساب</Label>
                <select
                  id="reconcile-account"
                  data-testid="reconcile-account"
                  className="flex h-9 w-full rounded-md border border-input bg-background px-2 text-sm text-foreground"
                  value={accountId}
                  onChange={(event) => {
                    setAccountId(event.target.value);
                    setSelectedLine(null);
                    setNotice(null);
                  }}
                >
                  {accounts.map((account) => (
                    <option key={account.id} value={account.id}>
                      {faDigits(account.code)} — {account.name}
                    </option>
                  ))}
                </select>
              </div>
              <CalendarInput
                id="reconcile-date"
                value={statementDate}
                onChange={setStatementDate}
                label="تاریخ صورت‌حساب"
              />
              <div className="space-y-1">
                <Label htmlFor="reconcile-opening">مانده آغاز دوره</Label>
                <Input
                  id="reconcile-opening"
                  data-testid="reconcile-opening"
                  inputMode="decimal"
                  value={beginning}
                  onChange={(event) => setBeginning(event.target.value)}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="reconcile-closing">مانده پایان دوره</Label>
                <Input
                  id="reconcile-closing"
                  data-testid="reconcile-closing"
                  inputMode="decimal"
                  value={ending}
                  onChange={(event) => setEnding(event.target.value)}
                />
              </div>
            </div>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <Button
              data-testid="start-session"
              disabled={!accountId || Boolean(session) || busy}
              onClick={() => startSession.mutate()}
            >
              شروع تطبیق
            </Button>
            {session && (
              <span className="num text-xs text-muted-foreground" data-testid="active-session">
                جلسه باز برای تاریخ {faDate(session.statement_date, calendar)} — مانده پایان{" "}
                <Money value={session.ending_balance} hideCurrency />
              </span>
            )}
            {!session && (
              <span className="text-xs text-muted-foreground">
                برای شروع، مانده آغاز و پایان دوره را از صورت‌حساب بانک وارد کنید.
              </span>
            )}
          </div>
        </CardContent>
      </Card>

      <QueryNotice query={linesQuery} />
      <QueryNotice query={ledgerQuery} />

      {allLines.length === 0 && linesQuery.isSuccess && (
        <p
          className="rounded-md border p-4 text-sm text-muted-foreground"
          data-testid="reconcile-empty-lines"
        >
          هنوز صورت‌حسابی برای این حساب وارد نشده است. در{" "}
          <Link to="/bank-import" className="text-primary underline">
            ورود صورت‌حساب بانکی
          </Link>{" "}
          فایل CSV یا OFX بانک را ثبت کنید.
        </p>
      )}

      {allLines.length > 0 && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-base">ردیف‌های بانک</CardTitle>
              <span className="text-xs text-muted-foreground">
                <span className="num">{faNumber(workLines.length)}</span> ردیف در انتظار
              </span>
            </CardHeader>
            <CardContent className="space-y-2">
              {workLines.length === 0 && (
                <p className="p-2 text-sm text-muted-foreground">
                  ردیف بازی نمانده است؛ همه تطبیق یا نادیده گرفته شده‌اند.
                </p>
              )}
              {workLines.map((line, index) => {
                const suggestion = suggestions.get(line.id);
                const best = suggestion?.best ?? null;
                const ranked = (suggestion?.ranked ?? []).slice(0, 5);
                const active = selectedLine === line.id;
                return (
                  <div
                    key={line.id}
                    data-testid={`bank-line-${index}`}
                    className={`rounded-lg border p-3 transition-colors ${
                      active ? "border-primary bg-primary/5" : "hover:bg-muted/40"
                    }`}
                  >
                    <button
                      type="button"
                      className="flex w-full items-center justify-between text-start"
                      onClick={() => setSelectedLine(active ? null : line.id)}
                      aria-pressed={active}
                      data-testid={`select-line-${index}`}
                    >
                      <span className="text-sm">{lineText(line)}</span>
                      <Money value={bankAmountScaled(line)} hideCurrency />
                    </button>
                    <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                      <span className="num">{faDate(line.value_date, calendar)}</span>
                      <Badge variant={best ? CONFIDENCE_BADGE[best.confidence] : "outline"}>
                        {best ? (
                          <>
                            {CONFIDENCE_LABELS[best.confidence]} —{" "}
                            <span className="num">{faNumber(best.score)}٪</span>
                          </>
                        ) : (
                          "بدون پیشنهاد"
                        )}
                      </Badge>
                      <Badge variant="secondary">{STATUS_LABEL[line.status]}</Badge>
                    </div>
                    {best && (
                      <p className="mt-2 text-xs" data-testid={`suggestion-${index}`}>
                        پیشنهاد: سند <span className="num">{faDigits(best.row.entry_number)}</span>{" "}
                        — {best.row.description}
                      </p>
                    )}
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <Button
                        size="sm"
                        data-testid={`accept-${index}`}
                        disabled={busy || !best || !session}
                        title={!session ? "ابتدا جلسه تطبیق را شروع کنید" : undefined}
                        onClick={() => {
                          if (!best) return;
                          linkMatch.mutate({ line, row: best.row });
                        }}
                      >
                        <Check /> تأیید پیشنهاد
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        data-testid={`ignore-${index}`}
                        disabled={busy}
                        onClick={() => ignoreLine.mutate(line)}
                      >
                        <X /> نادیده گرفتن
                      </Button>
                      {ranked.length > 1 && (
                        <select
                          aria-label="انتخاب سند دیگر برای تطبیق"
                          data-testid={`candidate-${index}`}
                          className="h-8 rounded-md border border-input bg-background px-2 text-xs"
                          defaultValue=""
                          disabled={busy || !session}
                          onChange={(event) => {
                            const row = ranked.find((r) => r.row.split_id === event.target.value);
                            if (row) linkMatch.mutate({ line, row: row.row });
                            event.target.value = "";
                          }}
                        >
                          <option value="">سند دیگر…</option>
                          {ranked.map((candidate) => (
                            <option key={candidate.row.split_id} value={candidate.row.split_id}>
                              {faDigits(candidate.row.entry_number)} — {candidate.row.description} (
                              {faNumber(candidate.score)}٪)
                            </option>
                          ))}
                        </select>
                      )}
                    </div>
                  </div>
                );
              })}

              {ignoredLines.length > 0 && (
                <div className="pt-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    data-testid="toggle-ignored"
                    onClick={() => setShowIgnored((v) => !v)}
                  >
                    {showIgnored ? "پنهان کردن" : "نمایش"} ردیف‌های نادیده‌گرفته‌شده (
                    <span className="num">{faNumber(ignoredLines.length)}</span>)
                  </Button>
                  {showIgnored &&
                    ignoredLines.map((line) => (
                      <div
                        key={line.id}
                        className="mt-2 flex items-center justify-between rounded-lg border p-2 text-sm"
                        data-testid={`ignored-line-${line.id}`}
                      >
                        <span>{lineText(line)}</span>
                        <div className="flex items-center gap-2">
                          <Money value={bankAmountScaled(line)} hideCurrency />
                          <Button
                            size="sm"
                            variant="outline"
                            data-testid={`restore-${line.id}`}
                            disabled={busy}
                            onClick={() => restoreLine.mutate(line)}
                          >
                            <Undo2 /> بازگردانی
                          </Button>
                        </div>
                      </div>
                    ))}
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-base">تراکنش‌های باز دفتر</CardTitle>
              <span className="num text-xs text-muted-foreground">
                {faDate(period.start, calendar)} تا {faDate(period.end, calendar)}
              </span>
            </CardHeader>
            <CardContent className="space-y-2">
              {openRows.length === 0 && (
                <p className="p-2 text-sm text-muted-foreground" data-testid="no-open-rows">
                  در این دوره گردشی روی این حساب ثبت نشده است.
                </p>
              )}
              {openRows.map((row, index) => (
                <div
                  key={row.split_id}
                  data-testid={`book-row-${index}`}
                  className="flex items-center justify-between rounded-lg border p-3"
                >
                  <div>
                    <div className="text-sm">{row.description}</div>
                    <div className="num text-xs text-muted-foreground">
                      {faDate(row.transaction_date, calendar)} — سند {faDigits(row.entry_number)}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Money value={bookAmount(row)} hideCurrency />
                    <Button
                      size="icon"
                      variant="ghost"
                      aria-label={`تطبیق سند ${row.entry_number}`}
                      title={
                        selected
                          ? `تطبیق با «${lineText(selected)}»`
                          : "ابتدا یک ردیف بانکی را از ستون کنار انتخاب کنید"
                      }
                      data-testid={`link-${index}`}
                      disabled={busy || !selected || !session}
                      onClick={() => {
                        if (!selected) return;
                        linkMatch.mutate({ line: selected, row });
                      }}
                    >
                      <Link2 />
                    </Button>
                  </div>
                </div>
              ))}
              {alreadyReconciled > 0 && (
                <p className="text-xs text-muted-foreground" data-testid="already-reconciled">
                  <span className="num">{faNumber(alreadyReconciled)}</span> گردش دیگر قبلاً تطبیق
                  شده است و در این فهرست نیست.
                </p>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {session && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">وضعیت جلسه</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid gap-3 text-sm sm:grid-cols-3">
              <div>
                <div className="text-xs text-muted-foreground">جمع تطبیق‌شده</div>
                <span data-testid="linked-total">
                  <Money value={linkedTotal} hideCurrency />
                </span>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">تغییر مورد انتظار صورت‌حساب</div>
                <span data-testid="expected-delta">
                  <Money value={expectedDelta} hideCurrency />
                </span>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">وضعیت</div>
                <span data-testid="balance-state">{balanced ? "تراز است" : "تراز نیست"}</span>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <Button
                data-testid="complete-session"
                disabled={busy}
                onClick={() => {
                  if (balanced) completeSession.mutate();
                  else setConfirmingComplete(true);
                }}
              >
                <Check /> تکمیل تطبیق
              </Button>
              <Button
                variant="outline"
                data-testid="abandon-session"
                disabled={busy}
                onClick={() => abandonSession.mutate()}
              >
                انصراف از جلسه
              </Button>
              {confirmingComplete && (
                <span
                  className="flex flex-wrap items-center gap-2 rounded-md bg-amber-500/15 px-3 py-2 text-xs text-amber-800 dark:text-amber-400"
                  data-testid="confirm-complete"
                >
                  جمع تطبیق‌شده با تغییر صورت‌حساب برابر نیست؛ باز هم تکمیل شود؟
                  <Button
                    size="sm"
                    variant="destructive"
                    data-testid="confirm-complete-yes"
                    disabled={busy}
                    onClick={() => completeSession.mutate()}
                  >
                    بله، تکمیل کن
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    data-testid="confirm-complete-no"
                    onClick={() => setConfirmingComplete(false)}
                  >
                    نه
                  </Button>
                </span>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {!session && lastClosed && (
        <Card>
          <CardContent className="flex flex-wrap items-center justify-between gap-2 pt-4 text-sm">
            <span data-testid="closed-session">
              آخرین جلسه: {lastClosed.status === "COMPLETED" ? "تکمیل‌شده" : "رهاشده"} —{" "}
              {faDate(lastClosed.statement_date, calendar)}
            </span>
            {lastClosed.status === "COMPLETED" && (
              <Button
                variant="outline"
                size="sm"
                data-testid="reopen-session"
                disabled={busy || !requestSudo}
                onClick={() => reopenSession.mutate()}
              >
                <RotateCcw /> بازگشایی جلسه
              </Button>
            )}
          </CardContent>
        </Card>
      )}

      {session && confidentMatches.length > 0 && (
        <div className="space-y-1">
          <Button
            className="w-full"
            data-testid="confirm-all"
            disabled={busy || !session}
            onClick={async () => {
              for (const match of confidentMatches) {
                await linkMatch.mutateAsync({ line: match.line, row: match.row });
              }
              setNotice({
                ok: true,
                text: `${faNumber(confidentMatches.length)} پیشنهاد مطمئن تطبیق شد.`,
              });
            }}
          >
            <Check /> تأیید پیشنهادهای مطمئن (
            <span className="num">{faNumber(confidentMatches.length)}</span>)
          </Button>
          <p className="text-center text-xs text-muted-foreground">
            فقط ردیف‌هایی که مبلغشان دقیقاً یکی است و تاریخشان حداکثر {faNumber(CONFIDENT_DAYS)} روز
            فاصله دارد.
          </p>
        </div>
      )}

      <Button variant="ghost" size="sm" data-testid="retry-all" onClick={retryAll}>
        به‌روزرسانی داده‌ها
      </Button>
    </div>
  );
}
