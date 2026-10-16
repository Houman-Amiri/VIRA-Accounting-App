/** Real-data management cockpit. Unknown/error is never presented as a healthy zero. */
import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import type { EChartsOption } from "echarts";
import { api, throwIfError } from "@/api/client";
import { sumMoney, toDecimal, type MoneyLike } from "@/lib/money";
import { faNumber } from "@/lib/fa";
import { fiscalYearFor } from "@/lib/fiscal";
import {
  chartToman,
  dashboardDate,
  daysBefore,
  inventoryValue,
  tehranDay,
  trialDifference,
} from "@/lib/dashboard";
import { useUpdateCheck } from "@/lib/update";
import { EChart, type ChartTheme } from "@/components/echart";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Money } from "@/components/money";

interface QueryState {
  isPending: boolean;
  isError: boolean;
  isFetching: boolean;
  refetch: () => unknown;
}

/** Hide stale data after a failed refresh; offer retry instead of false reassurance. */
function DataState({
  query,
  children,
}: {
  query: QueryState;
  children: React.ReactNode;
}): React.JSX.Element {
  if (query.isError)
    return (
      <div role="alert" className="space-y-2 py-3 text-sm text-destructive">
        <p>دریافت داده ناموفق بود؛ وضعیت نامشخص است.</p>
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
      <p role="status" className="py-3 text-sm text-muted-foreground">
        در حال دریافت داده…
      </p>
    );
  return <>{children}</>;
}

function Kpi({
  title,
  value,
  query,
  hint,
  unit = "IRR",
  id,
}: {
  title: string;
  value: MoneyLike;
  query: QueryState;
  hint: string;
  unit?: "IRR" | "TOMAN";
  id: string;
}): React.JSX.Element {
  return (
    <Card data-testid={id}>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm text-muted-foreground">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <DataState query={query}>
          <Money
            value={value}
            currency={unit}
            className="text-xl font-bold"
            signedColors={id === "kpi-profit" || toDecimal(value).isNegative()}
          />
          <p className="mt-2 text-xs text-muted-foreground">{hint}</p>
        </DataState>
      </CardContent>
    </Card>
  );
}

type ChartRow = { key?: string; label: string; value: MoneyLike };
/** Monetary plots have one comparable unit, with exact accessible source values. */
function MoneyChart({
  title,
  rows,
  query,
  id,
  unit = "IRR",
  line = false,
  horizontal = false,
}: {
  title: string;
  rows: ChartRow[];
  query: QueryState;
  id: string;
  unit?: "IRR" | "TOMAN";
  line?: boolean;
  horizontal?: boolean;
}): React.JSX.Element {
  const buildOption = React.useCallback(
    (theme: ChartTheme): EChartsOption => {
      const categories = {
        type: "category" as const,
        data: rows.map((r) => r.label),
        axisLabel: {
          color: theme.muted,
          interval: line ? 4 : 0,
          width: horizontal ? 120 : 90,
          overflow: horizontal ? ("truncate" as const) : ("break" as const),
          lineHeight: 18,
          formatter: (value: string) =>
            line
              ? value.slice(5)
              : horizontal && value.length > 22
                ? `${value.slice(0, 22)}…`
                : value,
        },
        axisLine: { lineStyle: { color: theme.border } },
      };
      const amounts = {
        type: "value" as const,
        name: "تومان",
        nameLocation: "end" as const,
        nameTextStyle: { color: theme.muted },
        axisLabel: { color: theme.muted, formatter: (value: number) => faNumber(String(value)) },
        splitLine: { lineStyle: { color: theme.border } },
      };
      return {
        aria: {
          enabled: true,
          label: { description: `${title}؛ داده‌های دقیق در جدول زیر نمودار موجود است.` },
        },
        tooltip: { trigger: "axis", valueFormatter: (value) => `${faNumber(String(value))} تومان` },
        grid: { left: 12, right: horizontal ? 48 : 18, top: 32, bottom: 18, containLabel: true },
        xAxis: horizontal ? amounts : categories,
        yAxis: horizontal ? { ...categories, inverse: true } : amounts,
        series: [
          {
            name: title,
            type: line ? "line" : "bar",
            data: rows.map((r) => chartToman(r.value, unit)),
            itemStyle: { color: theme.primary },
            barMaxWidth: 56,
            ...(line ? { showSymbol: false, lineStyle: { width: 3 } } : {}),
          },
        ],
      };
    },
    [rows, title, unit, line, horizontal],
  );
  const hasValues = rows.some((r) => !toDecimal(r.value).isZero());
  return (
    <Card data-testid={`${id}-panel`} className="min-w-0">
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <DataState query={query}>
          {hasValues ? (
            <EChart buildOption={buildOption} data-testid={id} />
          ) : (
            <p className="flex h-[280px] items-center justify-center text-sm text-muted-foreground">
              برای این بازه مبلغ غیرصفر ثبت نشده است.
            </p>
          )}
          <details className="mt-2 text-xs">
            <summary className="cursor-pointer text-primary">داده‌های نمودار (مبالغ دقیق)</summary>
            <table className="mt-2 w-full text-sm">
              <caption className="sr-only">{title} — تومان</caption>
              <thead>
                <tr>
                  <th className="text-start">عنوان</th>
                  <th className="text-end">مبلغ (تومان)</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.key ?? r.label}>
                    <td>{r.label}</td>
                    <td className="text-end">
                      <Money value={r.value} currency={unit} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        </DataState>
      </CardContent>
    </Card>
  );
}

export function DashboardPage(): React.JSX.Element {
  const navigate = useNavigate();
  // Refresh the civil day across midnight without requiring a page reload.
  const [today, setToday] = React.useState(() => tehranDay());
  React.useEffect(() => {
    const timer = window.setInterval(() => setToday(tehranDay()), 60_000);
    return () => window.clearInterval(timer);
  }, []);
  const fiscal = fiscalYearFor(today);
  const salesStart = daysBefore(today, 29);
  const trial = useQuery({
    queryKey: ["dashboard", "trial", today],
    queryFn: async () => {
      const res = await api.GET("/api/v1/reports/trial-balance", {
        params: { query: { as_of: today } },
      });
      await throwIfError(res);
      return res.data!;
    },
  });
  const balance = useQuery({
    queryKey: ["dashboard", "balance", today],
    queryFn: async () => {
      const res = await api.GET("/api/v1/reports/balance-sheet", {
        params: { query: { as_of: today } },
      });
      await throwIfError(res);
      return res.data!;
    },
  });
  const income = useQuery({
    queryKey: ["dashboard", "income", fiscal.startIso, today],
    queryFn: async () => {
      const res = await api.GET("/api/v1/reports/income-statement", {
        params: { query: { start: fiscal.startIso, end: today } },
      });
      await throwIfError(res);
      return res.data!;
    },
  });
  const cash = useQuery({
    queryKey: ["dashboard", "cash", fiscal.startIso, today],
    queryFn: async () => {
      // Do not include receivables / inventory (103/104) in cash by using prefix "10".
      const reports = await Promise.all(
        ["101", "102"].map(async (cash_prefix) => {
          const res = await api.GET("/api/v1/reports/cash-flow", {
            params: { query: { start: fiscal.startIso, end: today, cash_prefix } },
          });
          await throwIfError(res);
          return res.data!;
        }),
      );
      return sumMoney(reports.map((r) => r.closing_balance)).toFixed(4);
    },
  });
  const inventory = useQuery({
    queryKey: ["dashboard", "inventory"],
    queryFn: async () => {
      const res = await api.GET("/api/v1/warehouse/summary");
      await throwIfError(res);
      return res.data!;
    },
  });
  const alarms = useQuery({
    queryKey: ["dashboard", "alarms"],
    queryFn: async () => {
      const res = await api.GET("/api/v1/warehouse/alarms");
      await throwIfError(res);
      return res.data!;
    },
  });
  const production = useQuery({
    queryKey: ["dashboard", "production"],
    queryFn: async () => {
      const res = await api.GET("/api/v1/production/summary");
      await throwIfError(res);
      return res.data!;
    },
  });
  const orders = useQuery({
    queryKey: ["dashboard", "orders"],
    queryFn: async () => {
      const res = await api.GET("/api/v1/orders");
      await throwIfError(res);
      return res.data!;
    },
  });
  const orderCounts = useQuery({
    queryKey: ["dashboard", "order-counts"],
    queryFn: async () => {
      const res = await api.GET("/api/v1/orders/summary");
      await throwIfError(res);
      return res.data!;
    },
  });
  const sales = useQuery({
    queryKey: ["dashboard", "sales", salesStart, today],
    queryFn: async () => {
      const res = await api.GET("/api/v1/orders/reports/sales", {
        params: { query: { period: "daily", date_from: salesStart, date_to: today } },
      });
      await throwIfError(res);
      return res.data!;
    },
  });
  const health = useQuery({
    queryKey: ["dashboard", "health"],
    queryFn: async () => {
      const res = await api.GET("/api/v1/health/live");
      await throwIfError(res);
      return res.data!;
    },
    refetchInterval: 60_000,
  });
  // Cached badge only. System update checks require explicit user action / sudo.
  const update = useUpdateCheck(false);
  const queries = [
    trial,
    balance,
    income,
    cash,
    inventory,
    alarms,
    production,
    orders,
    orderCounts,
    sales,
    health,
  ];
  const fetching = queries.some((q) => q.isFetching);
  const equity = sumMoney([balance.data?.total_equity, balance.data?.retained_earnings]);
  const difference = trialDifference(trial.data ?? []);
  const pendingOrders = (orderCounts.data?.new ?? 0) + (orderCounts.data?.confirmed ?? 0);
  const activeJobs = (production.data?.jobs ?? [])
    .filter((j) => j.status === "PLANNED" || j.status === "IN_PROGRESS")
    .slice(0, 6);
  const structure: ChartRow[] = [
    { label: "دارایی", value: balance.data?.total_assets ?? "0" },
    { label: "بدهی", value: balance.data?.total_liabilities ?? "0" },
    { label: "حقوق صاحبان سهام", value: equity },
  ];
  const profit: ChartRow[] = [
    { label: "درآمد", value: income.data?.total_income ?? "0" },
    { label: "هزینه", value: income.data?.total_expenses ?? "0" },
    { label: "سود / زیان خالص", value: income.data?.net_income ?? "0" },
  ];
  // Sort by exact value, not Number; grams and pieces must not share a quantity axis.
  const stock = [...(inventory.data?.items ?? [])]
    .sort((a, b) => toDecimal(inventoryValue(b)).comparedTo(inventoryValue(a)))
    .slice(0, 8)
    .map((i) => ({
      key: i.id,
      label: `${i.name} (${i.unit === "G" ? "گرم" : "عدد"})`,
      value: inventoryValue(i),
    }));
  // Include zero-sales days for a continuous 30-day time axis.
  const daily = Array.from({ length: 30 }, (_, i) => {
    const day = daysBefore(today, 29 - i);
    return {
      label: dashboardDate(day),
      value: sales.data?.rows.find((r) => r.period === day)?.revenue ?? "0",
    };
  });
  const periodHint = `سال مالی ${fiscal.label} تا ${dashboardDate(today)}`;
  const action = (
    to: "/journal" | "/warehouse" | "/orders" | "/production" | "/system",
    text: string,
  ) => (
    <button
      type="button"
      className="mt-2 rounded border px-3 py-1 text-xs text-primary hover:bg-accent"
      onClick={() => void navigate({ to })}
    >
      {text}
    </button>
  );

  return (
    <div className="space-y-5" dir="rtl" data-testid="dashboard">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold">داشبورد مدیریت</h1>
          <p className="text-xs text-muted-foreground">{periodHint} — تاریخ تهران</p>
        </div>
        <div className="flex flex-wrap items-center gap-3 text-xs">
          <span role="status" data-testid="dashboard-health">
            {health.isError
              ? "ارتباط با سرویس ناموفق"
              : health.isPending
                ? "در حال بررسی سرویس…"
                : "سرویس در دسترس"}
          </span>
          {action(
            "/system",
            update.data?.checked && update.data.update_available
              ? `نسخهٔ ${update.data.latest} در آخرین بررسی موجود بود`
              : "بررسی به‌روزرسانی",
          )}
          <button
            type="button"
            className="rounded border px-3 py-2"
            disabled={fetching}
            onClick={() => void Promise.all(queries.map((q) => q.refetch()))}
          >
            تازه‌سازی داده‌ها
          </button>
        </div>
      </header>
      <p className="text-xs text-muted-foreground">
        همهٔ مبالغ به تومان؛ صورت‌های مالی فقط از اسناد قطعی حسابداری هستند. سفارش‌ها و انبار گزارش
        عملیاتی مستقل‌اند و خودکار سند حسابداری نمی‌سازند.
      </p>
      <section aria-label="شاخص‌های کلیدی" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <Kpi
          id="kpi-assets"
          title="دارایی‌ها"
          value={balance.data?.total_assets ?? "0"}
          query={balance}
          hint={`مانده تا ${dashboardDate(today)}`}
        />
        <Kpi
          id="kpi-liabilities"
          title="بدهی‌ها"
          value={balance.data?.total_liabilities ?? "0"}
          query={balance}
          hint={`مانده تا ${dashboardDate(today)}`}
        />
        <Kpi
          id="kpi-equity"
          title="حقوق صاحبان سهام"
          value={equity}
          query={balance}
          hint="شامل سود / زیان انباشته"
        />
        <Kpi
          id="kpi-profit"
          title="سود / زیان خالص"
          value={income.data?.net_income ?? "0"}
          query={income}
          hint={periodHint}
        />
        <Kpi
          id="kpi-stock"
          title="ارزش موجودی انبار"
          value={inventory.data?.total_value ?? "0"}
          unit="TOMAN"
          query={inventory}
          hint="موجودی فعلی × قیمت ثبت‌شدهٔ هر واحد"
        />
        <Kpi
          id="kpi-cash"
          title="موجودی نقد و بانک"
          value={cash.data ?? "0"}
          query={cash}
          hint="ماندهٔ حساب‌های با پیش‌شمارهٔ ۱۰۱ و ۱۰۲ تا امروز"
        />
      </section>
      <section
        aria-label="هشدارها و اقدام‌ها"
        data-testid="dashboard-alerts"
        className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"
      >
        <Card data-testid="alert-trial">
          <CardHeader>
            <CardTitle className="text-sm">تراز حسابداری</CardTitle>
          </CardHeader>
          <CardContent>
            <DataState query={trial}>
              <p className={toDecimal(difference).isZero() ? "text-positive" : "text-destructive"}>
                {toDecimal(difference).isZero()
                  ? "تراز بدهکار و بستانکار برابر است."
                  : "اختلاف در تراز حسابداری"}
              </p>
              {!toDecimal(difference).isZero() && <Money value={difference} signedColors />}
              {action("/journal", "بررسی اسناد حسابداری")}
            </DataState>
          </CardContent>
        </Card>
        <Card data-testid="alert-stock">
          <CardHeader>
            <CardTitle className="text-sm">کمبود موجودی</CardTitle>
          </CardHeader>
          <CardContent>
            <DataState query={alarms}>
              <p>
                {alarms.data?.length
                  ? `${faNumber(String(alarms.data.length))} قلم در حداقل موجودی یا کمتر`
                  : "هیچ قلمی در حداقل موجودی یا کمتر نیست."}
              </p>
              <ul className="mt-2 space-y-2 text-xs">
                {alarms.data?.slice(0, 3).map((a) => (
                  <li key={a.item_id}>
                    {a.name}: {faNumber(a.quantity)} / حداقل {faNumber(a.min_quantity)}{" "}
                    {a.unit === "G" ? "گرم" : "عدد"}
                    <br />
                    تأمین‌کنندهٔ پیشنهادی: {a.suggested_supplier ?? "ثبت نشده"}
                  </li>
                ))}
              </ul>
              {action("/warehouse", "رسیدگی به موجودی")}
            </DataState>
          </CardContent>
        </Card>
        <Card data-testid="alert-production">
          <CardHeader>
            <CardTitle className="text-sm">صف تولید</CardTitle>
          </CardHeader>
          <CardContent>
            <DataState query={production}>
              <p>
                {faNumber(String(production.data?.planned ?? 0))} برنامه‌ریزی‌شده؛{" "}
                {faNumber(String(production.data?.in_progress ?? 0))} در حال تولید
              </p>
              <p className="mt-2 text-xs">
                فیلامنت مورد نیاز: {faNumber(production.data?.filament_grams_planned ?? "0")} گرم
              </p>
              {action("/production", "پیگیری تولید")}
            </DataState>
          </CardContent>
        </Card>
        <Card data-testid="alert-orders">
          <CardHeader>
            <CardTitle className="text-sm">سفارش‌های در انتظار تولید</CardTitle>
          </CardHeader>
          <CardContent>
            <DataState query={orderCounts}>
              <p>{faNumber(String(pendingOrders))} سفارش جدید یا تأییدشده</p>
              <p className="mt-2 text-xs">
                از مجموع {faNumber(String(orderCounts.data?.total ?? 0))} سفارش؛ مستقل از محدودیت
                فهرست اخیر
              </p>
              {action("/orders", "پیگیری سفارش‌ها")}
            </DataState>
          </CardContent>
        </Card>
      </section>
      <section aria-label="نمودارهای مدیریتی" className="grid gap-4 lg:grid-cols-2">
        <MoneyChart
          id="chart-structure"
          title="ساختار مالی تا امروز"
          rows={structure}
          query={balance}
        />
        <MoneyChart
          id="chart-pnl"
          title={`درآمد و هزینه — ${periodHint}`}
          rows={profit}
          query={income}
        />
        <MoneyChart
          id="chart-sales"
          title="فروش سفارش‌ها — ۳۰ روز تا امروز"
          rows={daily}
          unit="TOMAN"
          query={sales}
          line
        />
        <MoneyChart
          id="chart-stock"
          title="ارزش ۸ قلم اول انبار — قیمت ثبت‌شده"
          rows={stock}
          horizontal
          unit="TOMAN"
          query={inventory}
        />
      </section>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">سفارش‌های اخیر</CardTitle>
          </CardHeader>
          <CardContent>
            <DataState query={orders}>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr>
                      <th className="text-start">شماره / تاریخ</th>
                      <th className="text-start">مشتری</th>
                      <th className="text-start">وضعیت</th>
                      <th className="text-end">مبلغ (تومان)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {orders.data?.slice(0, 6).map((o) => (
                      <tr key={o.id} data-testid={`dash-order-${o.id}`} className="border-b">
                        <td className="py-2">
                          {faNumber(String(o.order_number))}
                          <br />
                          {dashboardDate(o.order_date)}
                        </td>
                        <td>{o.customer_name}</td>
                        <td>
                          {
                            {
                              NEW: "جدید",
                              IN_PRODUCTION: "در حال تولید",
                              READY: "آماده",
                              DELIVERED: "تحویل‌شده",
                              CONFIRMED: "تأییدشده",
                              SHIPPED: "ارسال‌شده",
                              CANCELLED: "لغوشده",
                            }[o.status]
                          }
                        </td>
                        <td className="text-end">
                          <Money value={o.total} currency="TOMAN" />
                        </td>
                      </tr>
                    ))}
                    {orders.data?.length === 0 && (
                      <tr>
                        <td colSpan={4} className="py-6 text-center text-muted-foreground">
                          هنوز سفارشی ثبت نشده است.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              {action("/orders", "همهٔ سفارش‌ها")}
            </DataState>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">کارهای تولید در جریان</CardTitle>
          </CardHeader>
          <CardContent>
            <DataState query={production}>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr>
                      <th className="text-start">شماره</th>
                      <th className="text-start">محصول</th>
                      <th className="text-start">تعداد</th>
                      <th className="text-end">فیلامنت (گرم)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {activeJobs.map((j) => (
                      <tr key={j.id} data-testid={`dash-job-${j.id}`} className="border-b">
                        <td className="py-2">{faNumber(String(j.job_number))}</td>
                        <td>{j.product_name}</td>
                        <td>{faNumber(j.quantity)}</td>
                        <td className="text-end">
                          {faNumber(toDecimal(j.filament_grams).times(j.quantity).toString())}
                        </td>
                      </tr>
                    ))}
                    {activeJobs.length === 0 && (
                      <tr>
                        <td colSpan={4} className="py-6 text-center text-muted-foreground">
                          کار تولیدی در جریان نیست.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              {action("/production", "همهٔ کارهای تولید")}
            </DataState>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
