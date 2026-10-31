/**
 * حساب‌ها — the chart of accounts, said in the owner's language.
 *
 * The old page printed account codes, an empty «type» badge (it read a field the
 * API does not send), zero numbers, and «در حال بارگذاری…» forever when the list
 * was empty or the request failed. The accounts themselves cannot go away — the
 * statements and the invoice mapping (1040/4010, 1030/2010) are built on them —
 * so this page shows only what the owner needs: what each account is in plain
 * Persian, what it holds today, and the handful of totals that matter.
 *
 * Balances come from the real trial balance (signed debit − credit, shown in the
 * account's own direction). An account with no movement says so instead of
 * pretending to be zero, and a failed request says the state is unknown.
 */
import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { api, parseError } from "@/api/client";
import { Money } from "@/components/money";
import { QueryNotice } from "@/components/query-notice";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { balance, Decimal } from "@/lib/money";
import { tehranToday } from "@/lib/calendar";
import { faDigits } from "@/lib/fa";

type AccountType = "ASSET" | "LIABILITY" | "EQUITY" | "INCOME" | "EXPENSE";

interface Account {
  id: string;
  code: string;
  name: string;
  account_type: AccountType;
  normal_balance: "DEBIT" | "CREDIT";
  currency: string;
  parent_id: string | null;
  path: string;
  is_placeholder: boolean;
  is_active: boolean;
  version_id: number;
}

interface TrialRow {
  account_id: string;
  code: string;
  name: string;
  account_type: AccountType;
  normal_balance: "DEBIT" | "CREDIT";
  is_placeholder: boolean;
  debit: string;
  credit: string;
  balance: string;
}

const SECTIONS: Array<{ type: AccountType; title: string; hint: string }> = [
  { type: "ASSET", title: "دارایی‌ها", hint: "چیزهایی که دارید یا به شما بدهکارند." },
  { type: "LIABILITY", title: "بدهی‌ها", hint: "چیزهایی که باید بپردازید." },
  { type: "EQUITY", title: "سرمایه", hint: "آنچه خودتان در کسب‌وکار گذاشته‌اید." },
  { type: "INCOME", title: "درآمدها", hint: "پولی که از فروش یا خدمات درآمده." },
  { type: "EXPENSE", title: "هزینه‌ها", hint: "پولی که خرج شده است." },
];

/** One plain sentence for the accounts the owner meets every day. */
const PLAIN: Record<string, string> = {
  "1010": "پول نقدی که در صندوق است",
  "1020": "پولی که در حساب بانکی است",
  "1030": "جنس و موادی که در انبار دارید",
  "1040": "پولی که مشتری‌ها به شما بدهکارند",
  "2010": "پولی که به تأمین‌کننده‌ها بدهکارید",
  "3010": "سرمایه‌ای که خودتان آورده‌اید",
};

export function AccountsPage(): React.JSX.Element {
  const asOf = tehranToday();

  const accountsQuery = useQuery({
    queryKey: ["accounts"],
    queryFn: async () => {
      const res = await api.GET("/api/v1/accounts");
      if (res.error) throw await parseError(res.response);
      return res.data as unknown as Account[];
    },
  });

  const trialQuery = useQuery({
    queryKey: ["accounts", "trial", asOf],
    queryFn: async () => {
      const res = await api.GET("/api/v1/reports/trial-balance", {
        params: { query: { as_of: asOf } },
      });
      if (res.error) throw await parseError(res.response);
      return res.data as unknown as TrialRow[];
    },
  });

  const balances = React.useMemo(
    () => new Map((trialQuery.data ?? []).map((row) => [row.account_id, row])),
    [trialQuery.data],
  );

  /** The side a human reads: a credit-normal account is positive when credited. */
  const shown = (row: TrialRow | undefined, account: Account): Decimal => {
    if (!row) return new Decimal(0);
    return account.normal_balance === "CREDIT"
      ? balance(row.credit, row.debit)
      : balance(row.debit, row.credit);
  };

  const allAccounts = React.useMemo(
    () =>
      (accountsQuery.data ?? [])
        // Placeholders are pure structure (no postings) — accountants' scaffolding.
        .filter((account) => !account.is_placeholder && account.is_active)
        .sort((a, b) => a.code.localeCompare(b.code, "en")),
    [accountsQuery.data],
  );

  // A long list of untouched accounts is noise; on a fresh install, where
  // nothing has moved yet, they are still the only thing there is to show.
  const idle = allAccounts.filter((account) => !balances.has(account.id));
  const [showIdle, setShowIdle] = React.useState(false);
  const accounts = React.useMemo(
    () =>
      idle.length === 0 || idle.length === allAccounts.length || showIdle
        ? allAccounts
        : allAccounts.filter((account) => balances.has(account.id)),
    [allAccounts, idle.length, showIdle, balances],
  );

  const totals = new Map<AccountType, Decimal>();
  for (const account of accounts) {
    const row = balances.get(account.id);
    const value = shown(row, account);
    totals.set(
      account.account_type,
      (totals.get(account.account_type) ?? new Decimal(0)).plus(value),
    );
  }
  const assets = totals.get("ASSET") ?? new Decimal(0);
  const liabilities = totals.get("LIABILITY") ?? new Decimal(0);
  const net = assets.minus(liabilities);

  const loading = accountsQuery.isPending || trialQuery.isPending;
  const failed = accountsQuery.isError || trialQuery.isError;

  return (
    <div className="space-y-4" dir="rtl">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-bold">حساب‌ها</h1>
        <Link to="/statements" className="text-sm text-primary underline-offset-4 hover:underline">
          دیدن در صورت‌های مالی
        </Link>
      </div>
      <p className="text-sm text-muted-foreground">
        هر جایی که پول شما می‌نشیند یک حساب است. مانده‌ها همان اعداد دفتر شما هستند.
      </p>

      <QueryNotice query={accountsQuery} />
      <QueryNotice query={trialQuery} />

      {!loading && !failed && (
        <>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3" data-testid="accounts-summary">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-muted-foreground">دارایی‌ها</CardTitle>
              </CardHeader>
              <CardContent className="text-lg font-semibold">
                <Money value={assets.toFixed(4)} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-muted-foreground">بدهی‌ها</CardTitle>
              </CardHeader>
              <CardContent className="text-lg font-semibold">
                <Money value={liabilities.toFixed(4)} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-muted-foreground">
                  خالص دارایی (دارایی منهای بدهی)
                </CardTitle>
              </CardHeader>
              <CardContent className="text-lg font-semibold" data-testid="accounts-net">
                <Money value={net.toFixed(4)} />
              </CardContent>
            </Card>
          </div>

          {accounts.length === 0 && (
            <p className="rounded-lg border bg-card p-8 text-center text-muted-foreground">
              هنوز حسابی ساخته نشده است.
            </p>
          )}

          {SECTIONS.map((section) => {
            const rows = accounts.filter((account) => account.account_type === section.type);
            if (rows.length === 0) return null;
            return (
              <section
                key={section.type}
                className="rounded-lg border bg-card"
                data-testid={`accounts-section-${section.type.toLowerCase()}`}
                aria-label={section.title}
              >
                <header className="flex flex-wrap items-baseline justify-between gap-2 border-b px-4 py-2">
                  <div>
                    <h2 className="text-base font-semibold">{section.title}</h2>
                    <p className="text-xs text-muted-foreground">{section.hint}</p>
                  </div>
                  <p className="text-sm text-muted-foreground">
                    جمع:{" "}
                    <span data-testid={`accounts-total-${section.type.toLowerCase()}`}>
                      <Money value={(totals.get(section.type) ?? new Decimal(0)).toFixed(4)} />
                    </span>
                  </p>
                </header>
                <ul className="divide-y">
                  {rows.map((account) => {
                    const row = balances.get(account.id);
                    const value = shown(row, account);
                    return (
                      <li
                        key={account.id}
                        className="flex flex-wrap items-center justify-between gap-2 px-4 py-2 text-sm"
                        data-testid={`accounts-row-${account.code}`}
                      >
                        <div className="min-w-0">
                          <p className="font-medium">{account.name}</p>
                          <p className="text-xs text-muted-foreground">
                            {PLAIN[account.code] ? `${PLAIN[account.code]} — ` : ""}
                            <span className="num opacity-70">کد {faDigits(account.code)}</span>
                          </p>
                        </div>
                        <div className="text-end">
                          {row ? (
                            <Money value={value.toFixed(4)} signedColors />
                          ) : (
                            <span className="text-xs text-muted-foreground">بدون گردش</span>
                          )}
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </section>
            );
          })}

          {idle.length > 0 && idle.length < allAccounts.length && (
            <button
              type="button"
              className="text-sm text-primary underline-offset-4 hover:underline"
              data-testid="accounts-toggle-idle"
              onClick={() => setShowIdle((value) => !value)}
            >
              {showIdle
                ? "پنهان کردن حساب‌های بدون گردش"
                : `نمایش ${faDigits(String(idle.length))} حساب بدون گردش`}
            </button>
          )}

          {trialQuery.isSuccess && (trialQuery.data ?? []).length === 0 && accounts.length > 0 && (
            <p className="text-xs text-muted-foreground" data-testid="accounts-no-movement">
              هنوز سندی ثبت نشده است؛ برای همین همهٔ حساب‌ها «بدون گردش» هستند.
            </p>
          )}
        </>
      )}
    </div>
  );
}
