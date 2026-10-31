import { tehranToday } from "@/lib/calendar";
import { useCalendar } from "@/lib/calendar-settings";
/**
 * صورت‌های مالی — the three real statements plus the trial balance.
 *
 * Every tab reads the same reports the dashboard trusts:
 *   /reports/balance-sheet, /reports/income-statement, /reports/cash-flow,
 *   /reports/trial-balance
 * Nothing is invented or zero-filled: a failed request says the state is
 * unknown and offers a retry, an empty result says there is no data yet.
 */
import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import type { EChartsOption } from "echarts";
import { api, parseError } from "@/api/client";
import { faDate, faNumber } from "@/lib/fa";
import { currentFiscalYear } from "@/lib/fiscal";
import { sumMoney, toDecimal, type MoneyLike } from "@/lib/money";
import { trackEvent } from "@/lib/analytics";
import { EChart } from "@/components/echart";
import { CalendarInput } from "@/components/calendar-input";
import { Money } from "@/components/money";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

interface Node {
  account_id: string;
  code: string;
  name: string;
  account_type: "ASSET" | "LIABILITY" | "EQUITY" | "INCOME" | "EXPENSE";
  is_placeholder: boolean;
  amount: string;
  children?: Node[];
}

interface QueryState {
  isPending: boolean;
  isError: boolean;
  isFetching: boolean;
  refetch: () => unknown;
}

/** Unknown is never shown as a healthy zero; a failure offers a retry. */
function ReportState({
  query,
  children,
  testId,
}: {
  query: QueryState;
  children: React.ReactNode;
  testId: string;
}): React.JSX.Element {
  if (query.isError)
    return (
      <div role="alert" className="space-y-2 p-4 text-sm text-destructive" data-testid={testId}>
        <p>دریافت گزارش ناموفق بود؛ وضعیت نامشخص است.</p>
        <button
          type="button"
          className="rounded border px-3 py-1"
          disabled={query.isFetching}
          onClick={() => void query.refetch()}
        >
          تلاش دوباره
        </button>
      </div>
    );
  if (query.isPending)
    return (
      <p role="status" className="p-4 text-sm text-muted-foreground">
        در حال دریافت گزارش…
      </p>
    );
  return <div data-testid={`${testId}-ready`}>{children}</div>;
}

/**
 * One statement line. A group header (placeholder account) carries no balance of
 * its own — the server keeps that 0 — so it shows a dash instead of a fake zero,
 * and a placeholder with nothing under it is dropped entirely.
 *
 * A real account is clickable: it opens the posted movements behind that number.
 */
function TreeRows({
  nodes,
  depth = 0,
  onOpen,
}: {
  nodes: Node[];
  depth?: number;
  onOpen: (node: Node) => void;
}): React.JSX.Element {
  return (
    <>
      {nodes.map((node) => {
        const children = node.children ?? [];
        if (node.is_placeholder && children.length === 0) return null;
        return (
          <React.Fragment key={node.account_id}>
            <tr
              className={node.is_placeholder ? "font-semibold" : "hover:bg-accent/40"}
              data-testid={`stmt-node-${node.code}`}
            >
              <td
                className="py-1.5 ps-1"
                style={{ paddingInlineStart: `${0.25 + depth * 1.1}rem` }}
              >
                <span className="num text-xs text-muted-foreground">{faNumber(node.code)}</span>{" "}
                {node.is_placeholder ? (
                  node.name
                ) : (
                  <button
                    type="button"
                    className="underline decoration-dotted underline-offset-2"
                    onClick={() => onOpen(node)}
                    data-testid={`stmt-open-${node.code}`}
                    aria-label={`نمایش گردش حساب ${node.name}`}
                  >
                    {node.name}
                  </button>
                )}
              </td>
              <td className="py-1.5 pe-1 text-end">
                {node.is_placeholder ? (
                  <span className="text-muted-foreground">—</span>
                ) : (
                  <Money value={node.amount} hideCurrency />
                )}
              </td>
            </tr>
            {children.length > 0 && <TreeRows nodes={children} depth={depth + 1} onOpen={onOpen} />}
          </React.Fragment>
        );
      })}
    </>
  );
}

function TotalRow({
  label,
  value,
  testId,
  strong = false,
}: {
  label: string;
  value: MoneyLike;
  testId: string;
  strong?: boolean;
}): React.JSX.Element {
  return (
    <tr className={strong ? "border-t-2 font-bold" : "border-t font-semibold"} data-testid={testId}>
      <td className="py-2 ps-1">{label}</td>
      <td className="py-2 pe-1 text-end">
        <Money value={value} hideCurrency />
      </td>
    </tr>
  );
}

function Empty({ text }: { text: string }): React.JSX.Element {
  return <p className="p-6 text-center text-sm text-muted-foreground">{text}</p>;
}

/**
 * Exact difference between the two sides of the balance sheet.
 * assets − (liabilities + equity + retained earnings); "0.0000" when it balances.
 */
export function balanceSheetDifference(
  totalAssets: MoneyLike,
  totalLiabilities: MoneyLike,
  totalEquity: MoneyLike,
  retained: MoneyLike,
): string {
  return toDecimal(totalAssets)
    .minus(sumMoney([totalLiabilities, totalEquity, retained]))
    .toFixed(4);
}

/** A drill-down drawer: the posted movements behind one statement line. */
function AccountDrawer({
  account,
  start,
  end,
  onClose,
}: {
  account: { accountId: string; code: string; name: string };
  start?: string;
  end?: string;
  onClose: () => void;
}): React.JSX.Element {
  const { calendar } = useCalendar();
  const closeRef = React.useRef<HTMLButtonElement>(null);
  React.useEffect(() => {
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const ledger = useQuery({
    queryKey: ["accounts", "ledger", account.accountId, start, end],
    queryFn: async () => {
      const res = await api.GET("/api/v1/accounts/{account_id}/ledger", {
        params: { path: { account_id: account.accountId }, query: { start, end } },
      });
      if (res.error) throw await parseError(res.response);
      return res.data!;
    },
  });

  return (
    <div className="fixed inset-0 z-50 flex print:hidden" data-testid="stmt-drill">
      <button
        type="button"
        className="flex-1 bg-black/30"
        aria-label="بستن گردش حساب"
        onClick={onClose}
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={`گردش حساب ${account.name}`}
        className="h-full w-full max-w-xl overflow-y-auto bg-background p-4 shadow-xl"
      >
        <div className="mb-3 flex items-start justify-between gap-2">
          <div>
            <h2 className="text-lg font-bold">{account.name}</h2>
            <p className="num text-xs text-muted-foreground">کد حساب {faNumber(account.code)}</p>
          </div>
          <button
            ref={closeRef}
            type="button"
            className="rounded border px-3 py-1 text-sm"
            onClick={onClose}
            data-testid="stmt-drill-close"
          >
            بستن
          </button>
        </div>
        <ReportState query={ledger} testId="stmt-drill-state">
          {ledger.data && (
            <>
              <div className="mb-2 flex items-center justify-between text-sm">
                <span>ماندهٔ ابتدای دوره</span>
                <span data-testid="stmt-drill-opening">
                  <Money value={ledger.data.opening_balance} hideCurrency /> تومان
                </span>
              </div>
              {ledger.data.rows.length === 0 ? (
                <Empty text="در این دوره گردشی روی این حساب ثبت نشده است." />
              ) : (
                <table className="w-full text-xs" aria-label={`گردش حساب ${account.name}`}>
                  <thead>
                    <tr className="border-b text-muted-foreground">
                      <th scope="col" className="py-1 text-start font-medium">
                        تاریخ
                      </th>
                      <th scope="col" className="py-1 text-start font-medium">
                        شماره سند
                      </th>
                      <th scope="col" className="py-1 text-start font-medium">
                        شرح
                      </th>
                      <th scope="col" className="py-1 text-end font-medium">
                        بدهکار
                      </th>
                      <th scope="col" className="py-1 text-end font-medium">
                        بستانکار
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {ledger.data.rows.map((row) => (
                      <tr key={`${row.entry_id}-${row.entry_number}`} data-testid="stmt-drill-row">
                        <td className="py-1">{faDate(row.transaction_date, calendar)}</td>
                        <td className="num py-1">{faNumber(row.entry_number)}</td>
                        <td className="py-1">
                          {row.description}
                          {row.payee ? ` — ${row.payee}` : ""}
                        </td>
                        <td className="py-1 text-end">
                          <Money value={row.debit} hideCurrency />
                        </td>
                        <td className="py-1 text-end">
                          <Money value={row.credit} hideCurrency />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              <div className="mt-3 flex items-center justify-between border-t pt-2 text-sm font-semibold">
                <span>ماندهٔ پایان دوره</span>
                <span data-testid="stmt-drill-closing">
                  <Money value={ledger.data.closing_balance} hideCurrency /> تومان
                </span>
              </div>
              <p className="mt-3 text-xs text-muted-foreground">
                فقط اسناد ثبت‌شده نمایش داده می‌شوند؛ پیش‌نویس‌ها در دفاتر نیستند. برای دیدن اصل
                سند، به «دفتر روزنامه» بروید.
              </p>
            </>
          )}
        </ReportState>
      </aside>
    </div>
  );
}

export function StatementsPage(): React.JSX.Element {
  const { calendar } = useCalendar();
  const { t } = useTranslation("reports");
  const today = tehranToday();
  const fiscal = currentFiscalYear(today);

  const [asOf, setAsOf] = React.useState(today);
  const [from, setFrom] = React.useState(fiscal.startIso);
  const [to, setTo] = React.useState(today);
  // Drill-down drawer: which account, and which period the statement used.
  const [drill, setDrill] = React.useState<{
    accountId: string;
    code: string;
    name: string;
    start?: string;
    end?: string;
  } | null>(null);

  const balance = useQuery({
    queryKey: ["reports", "balance-sheet", asOf],
    queryFn: async () => {
      const res = await api.GET("/api/v1/reports/balance-sheet", {
        params: { query: { as_of: asOf } },
      });
      trackEvent("report_viewed", { route: "/statements", entity: "balance-sheet" });
      if (res.error) throw await parseError(res.response);
      return res.data!;
    },
  });

  const income = useQuery({
    queryKey: ["reports", "income-statement", from, to],
    queryFn: async () => {
      const res = await api.GET("/api/v1/reports/income-statement", {
        params: { query: { start: from, end: to } },
      });
      trackEvent("report_viewed", { route: "/statements", entity: "income-statement" });
      if (res.error) throw await parseError(res.response);
      return res.data!;
    },
  });

  // Cash and bank are separate accounts (1010 «صندوق», 1020 «بانک»). Querying
  // the «10» prefix would also sweep in receivables and inventory, which are
  // assets but not cash, so each group is read on its own.
  const cashAccounts = [
    { prefix: "101", key: "cash", label: "صندوق" },
    { prefix: "102", key: "bank", label: "بانک" },
  ] as const;
  const cash = useQuery({
    queryKey: ["reports", "cash-flow", from, to],
    queryFn: async () => {
      const rows = await Promise.all(
        cashAccounts.map(async (row) => {
          const res = await api.GET("/api/v1/reports/cash-flow", {
            params: { query: { start: from, end: to, cash_prefix: row.prefix } },
          });
          if (res.error) throw await parseError(res.response);
          return { ...row, report: res.data! };
        }),
      );
      trackEvent("report_viewed", { route: "/statements", entity: "cash-flow" });
      const total = (
        key: "opening_balance" | "closing_balance" | "inflows" | "outflows" | "net_change",
      ) => sumMoney(rows.map((r) => r.report[key]));
      return {
        rows,
        opening: total("opening_balance"),
        closing: total("closing_balance"),
        inflows: total("inflows"),
        outflows: total("outflows"),
        net: total("net_change"),
      };
    },
  });

  const trial = useQuery({
    queryKey: ["reports", "trial-balance", to],
    queryFn: async () => {
      const res = await api.GET("/api/v1/reports/trial-balance", {
        params: { query: { as_of: to } },
      });
      if (res.error) throw await parseError(res.response);
      return res.data!;
    },
  });

  const buildTrialOption = React.useCallback((): EChartsOption => {
    const rows = (trial.data ?? []).slice(0, 8);
    return {
      tooltip: { trigger: "axis" },
      grid: { left: 80, right: 20, top: 30, bottom: 40 },
      xAxis: { type: "category", data: rows.map((r) => r.name), axisLabel: { rotate: 30 } },
      yAxis: { type: "value" },
      series: [{ type: "bar", data: rows.map((r) => r.balance), itemStyle: { color: "#3b82f6" } }],
    };
  }, [trial.data]);

  const hasNodes = (nodes: Node[] | undefined): boolean =>
    (nodes ?? []).some((node) => !node.is_placeholder || (node.children ?? []).length > 0);

  const difference = balance.data
    ? balanceSheetDifference(
        balance.data.total_assets,
        balance.data.total_liabilities,
        balance.data.total_equity,
        balance.data.retained_earnings,
      )
    : null;
  const balanced = difference !== null && toDecimal(difference).isZero();

  return (
    <div className="space-y-4" dir="rtl">
      {/* Print/PDF header — Jalali fiscal-year dating (Phase 7 §3). */}
      <div className="print-only hidden rounded-md border p-3 text-sm">
        <div className="font-bold">
          {t("statements.title")} — {t("statements.fiscalYear")}{" "}
          {currentFiscalYear(tehranToday()).label}
        </div>
        <div>
          {t("statements.from")} {faDate(currentFiscalYear(tehranToday()).startIso, calendar)} —{" "}
          {t("statements.to")} {faDate(currentFiscalYear(tehranToday()).endIso, calendar)}
        </div>
      </div>
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">{t("statements.title")}</h1>
        <button
          type="button"
          className="rounded-md border px-3 py-1.5 text-sm print:hidden"
          onClick={() => window.print()}
        >
          {t("statements.print")}
        </button>
      </div>
      <Tabs defaultValue="balance-sheet">
        <TabsList>
          <TabsTrigger value="balance-sheet">{t("statements.balanceSheet")}</TabsTrigger>
          <TabsTrigger value="income">{t("statements.incomeStatement")}</TabsTrigger>
          <TabsTrigger value="cash-flow">{t("statements.cashFlow")}</TabsTrigger>
          <TabsTrigger value="trial">{t("statements.trialBalance")}</TabsTrigger>
        </TabsList>

        <TabsContent value="balance-sheet">
          <Card>
            <CardHeader className="flex flex-row flex-wrap items-end justify-between gap-2">
              <CardTitle className="text-base">{t("statements.balanceSheet")}</CardTitle>
              <div className="w-56 print:hidden">
                <CalendarInput
                  id="statements-as-of"
                  value={asOf}
                  onChange={setAsOf}
                  label={t("statements.asOfShort")}
                />
              </div>
            </CardHeader>
            <CardContent>
              <ReportState query={balance} testId="balance-sheet-state">
                {balance.data && (
                  <>
                    <table className="w-full text-sm" aria-label="ترازنامه">
                      <thead>
                        <tr className="border-b text-muted-foreground">
                          <th scope="col" className="py-2 text-start font-medium">
                            {t("statements.accountName")}
                          </th>
                          <th scope="col" className="py-2 pe-1 text-end font-medium">
                            {t("statements.balance")} (تومان)
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr className="bg-muted/40">
                          <td colSpan={2} className="py-1.5 ps-1 font-semibold">
                            {t("statements.assets")}
                          </td>
                        </tr>
                        {hasNodes(balance.data.assets) ? (
                          <TreeRows
                            nodes={balance.data.assets}
                            onOpen={(n) =>
                              setDrill({
                                accountId: n.account_id,
                                code: n.code,
                                name: n.name,
                                end: asOf,
                              })
                            }
                          />
                        ) : (
                          <tr>
                            <td colSpan={2}>
                              <Empty text={t("statements.empty")} />
                            </td>
                          </tr>
                        )}
                        <TotalRow
                          label={`${t("statements.total")} ${t("statements.assets")}`}
                          value={balance.data.total_assets}
                          testId="bs-total-assets"
                        />
                        <tr className="bg-muted/40">
                          <td colSpan={2} className="py-1.5 ps-1 font-semibold">
                            {t("statements.liabilities")}
                          </td>
                        </tr>
                        {hasNodes(balance.data.liabilities) ? (
                          <TreeRows
                            nodes={balance.data.liabilities}
                            onOpen={(n) =>
                              setDrill({
                                accountId: n.account_id,
                                code: n.code,
                                name: n.name,
                                end: asOf,
                              })
                            }
                          />
                        ) : (
                          <tr>
                            <td colSpan={2}>
                              <Empty text={t("statements.empty")} />
                            </td>
                          </tr>
                        )}
                        <TotalRow
                          label={`${t("statements.total")} ${t("statements.liabilities")}`}
                          value={balance.data.total_liabilities}
                          testId="bs-total-liabilities"
                        />
                        <tr className="bg-muted/40">
                          <td colSpan={2} className="py-1.5 ps-1 font-semibold">
                            {t("statements.equity")}
                          </td>
                        </tr>
                        {hasNodes(balance.data.equity) ? (
                          <TreeRows
                            nodes={balance.data.equity}
                            onOpen={(n) =>
                              setDrill({
                                accountId: n.account_id,
                                code: n.code,
                                name: n.name,
                                end: asOf,
                              })
                            }
                          />
                        ) : (
                          <tr>
                            <td colSpan={2}>
                              <Empty text={t("statements.empty")} />
                            </td>
                          </tr>
                        )}
                        <TotalRow
                          label={t("statements.retainedEarnings")}
                          value={balance.data.retained_earnings}
                          testId="bs-retained-earnings"
                        />
                        <TotalRow
                          label={`${t("statements.total")} ${t("statements.liabilities")} + ${t("statements.equity")}`}
                          value={sumMoney([
                            balance.data.total_liabilities,
                            balance.data.total_equity,
                            balance.data.retained_earnings,
                          ])}
                          testId="bs-total-liabilities-equity"
                          strong
                        />
                      </tbody>
                    </table>
                    {balanced ? (
                      <p
                        className="mt-3 rounded-md bg-green-100 px-3 py-2 text-sm text-green-900 dark:bg-green-900/40 dark:text-green-100"
                        data-testid="bs-balanced"
                      >
                        ترازنامه تراز است: دارایی‌ها با بدهی‌ها و سرمایه برابرند.
                      </p>
                    ) : (
                      <p
                        role="alert"
                        className="mt-3 rounded-md bg-red-100 px-3 py-2 text-sm text-red-900 dark:bg-red-900/40 dark:text-red-100"
                        data-testid="bs-imbalance"
                      >
                        ترازنامه تراز نیست؛ اختلاف: <Money value={difference ?? "0"} hideCurrency />{" "}
                        تومان. پیش از تصمیم‌گیری مالی، اسناد را بررسی کنید.
                      </p>
                    )}
                  </>
                )}
              </ReportState>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="income">
          <Card>
            <CardHeader className="flex flex-row flex-wrap items-end justify-between gap-2">
              <CardTitle className="text-base">{t("statements.incomeStatement")}</CardTitle>
              <div className="flex flex-wrap gap-2 print:hidden">
                <div className="w-48">
                  <CalendarInput
                    id="statements-from"
                    value={from}
                    onChange={setFrom}
                    label={t("statements.from")}
                  />
                </div>
                <div className="w-48">
                  <CalendarInput
                    id="statements-to"
                    value={to}
                    onChange={setTo}
                    label={t("statements.to")}
                  />
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <ReportState query={income} testId="income-state">
                {income.data && (
                  <table className="w-full text-sm" aria-label="صورت سود و زیان">
                    <thead>
                      <tr className="border-b text-muted-foreground">
                        <th scope="col" className="py-2 text-start font-medium">
                          {t("statements.accountName")}
                        </th>
                        <th scope="col" className="py-2 pe-1 text-end font-medium">
                          {t("statements.balance")} (تومان)
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr className="bg-muted/40">
                        <td colSpan={2} className="py-1.5 ps-1 font-semibold">
                          {t("statements.revenue")}
                        </td>
                      </tr>
                      {hasNodes(income.data.income) ? (
                        <TreeRows
                          nodes={income.data.income}
                          onOpen={(n) =>
                            setDrill({
                              accountId: n.account_id,
                              code: n.code,
                              name: n.name,
                              start: from,
                              end: to,
                            })
                          }
                        />
                      ) : (
                        <tr>
                          <td colSpan={2}>
                            <Empty text={t("statements.empty")} />
                          </td>
                        </tr>
                      )}
                      <TotalRow
                        label={`${t("statements.total")} ${t("statements.revenue")}`}
                        value={income.data.total_income}
                        testId="is-total-income"
                      />
                      <tr className="bg-muted/40">
                        <td colSpan={2} className="py-1.5 ps-1 font-semibold">
                          {t("statements.expenses")}
                        </td>
                      </tr>
                      {hasNodes(income.data.expenses) ? (
                        <TreeRows
                          nodes={income.data.expenses}
                          onOpen={(n) =>
                            setDrill({
                              accountId: n.account_id,
                              code: n.code,
                              name: n.name,
                              start: from,
                              end: to,
                            })
                          }
                        />
                      ) : (
                        <tr>
                          <td colSpan={2}>
                            <Empty text={t("statements.empty")} />
                          </td>
                        </tr>
                      )}
                      <TotalRow
                        label={`${t("statements.total")} ${t("statements.expenses")}`}
                        value={income.data.total_expenses}
                        testId="is-total-expenses"
                      />
                      <TotalRow
                        label={t("statements.netIncome")}
                        value={income.data.net_income}
                        testId="is-net-income"
                        strong
                      />
                    </tbody>
                  </table>
                )}
              </ReportState>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="cash-flow">
          <Card>
            <CardHeader className="flex flex-row flex-wrap items-end justify-between gap-2">
              <CardTitle className="text-base">{t("statements.cashFlow")}</CardTitle>
              <div className="flex flex-wrap gap-2 print:hidden">
                <div className="w-48">
                  <CalendarInput
                    id="statements-cash-from"
                    value={from}
                    onChange={setFrom}
                    label={t("statements.from")}
                  />
                </div>
                <div className="w-48">
                  <CalendarInput
                    id="statements-cash-to"
                    value={to}
                    onChange={setTo}
                    label={t("statements.to")}
                  />
                </div>
              </div>
              <p className="w-full text-xs text-muted-foreground">{t("statements.cashNote")}</p>
            </CardHeader>
            <CardContent>
              <ReportState query={cash} testId="cash-flow-state">
                {cash.data && (
                  <table className="w-full text-sm" aria-label="جریان وجوه نقد">
                    <thead>
                      <tr className="border-b text-muted-foreground">
                        <th scope="col" className="py-2 text-start font-medium">
                          شرح
                        </th>
                        <th scope="col" className="py-2 pe-1 text-end font-medium">
                          مبلغ (تومان)
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      <TotalRow
                        label="ماندهٔ ابتدای دوره"
                        value={cash.data.opening}
                        testId="cf-opening"
                      />
                      <TotalRow
                        label="وجه نقد دریافتی در دوره"
                        value={cash.data.inflows}
                        testId="cf-inflows"
                      />
                      <TotalRow
                        label="وجه نقد پرداختی در دوره"
                        value={cash.data.outflows}
                        testId="cf-outflows"
                      />
                      <TotalRow
                        label="تغییر خالص دوره"
                        value={cash.data.net}
                        testId="cf-net"
                        strong
                      />
                      <TotalRow
                        label="ماندهٔ پایان دوره"
                        value={cash.data.closing}
                        testId="cf-closing"
                        strong
                      />
                      {cash.data.rows.map((row) => (
                        <tr key={row.key} data-testid={`cf-${row.key}`}>
                          <td className="py-1.5 ps-1 text-muted-foreground">
                            {row.label} (ماندهٔ پایان دوره)
                          </td>
                          <td className="py-1.5 pe-1 text-end text-muted-foreground">
                            <Money value={row.report.closing_balance} hideCurrency />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </ReportState>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="trial">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("statements.trialBalance")}</CardTitle>
            </CardHeader>
            <CardContent>
              <ReportState query={trial} testId="trial-state">
                {trial.data && trial.data.length === 0 ? (
                  <Empty text={t("statements.empty")} />
                ) : (
                  <>
                    <div className="divide-y">
                      {(trial.data ?? []).map((r) => (
                        <div
                          key={r.account_id}
                          className="flex items-center justify-between py-2 text-sm"
                          data-testid={`tb-row-${r.code}`}
                        >
                          <span>
                            <span className="num text-muted-foreground">{faNumber(r.code)}</span>{" "}
                            {r.name}
                          </span>
                          <div className="flex gap-6">
                            <Money value={r.debit} hideCurrency />
                            <Money value={r.credit} hideCurrency />
                            <Money value={r.balance} hideCurrency signedColors />
                          </div>
                        </div>
                      ))}
                    </div>
                    <EChart
                      buildOption={buildTrialOption}
                      height={288}
                      className="mt-4"
                      data-testid="trial-chart"
                    />
                  </>
                )}
              </ReportState>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
      {drill && (
        <AccountDrawer
          account={drill}
          start={drill.start}
          end={drill.end}
          onClose={() => setDrill(null)}
        />
      )}
    </div>
  );
}
