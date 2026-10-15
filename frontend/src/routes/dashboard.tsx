/**
 * داشبورد — management cockpit.
 *
 * KPI strip (assets / liabilities / equity / net income / stock value / net cash),
 * four ECharts panels (financial structure, profit & loss, daily sales trend,
 * warehouse composition), a prominent alert strip (unbalanced trial balance,
 * stock-out alarms with supplier suggestion, jobs in progress, orders awaiting
 * production, available update) and the recent-orders / production queues.
 */
import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import {
  AlertTriangle,
  ArrowUpCircle,
  CheckCircle2,
  Factory,
  PackageX,
  ShoppingCart,
  TriangleAlert,
} from "lucide-react";

import { api, throwIfError } from "@/api/client";
import { sumMoney } from "@/lib/money";
import { faDate, faNumber } from "@/lib/fa";
import { currentFiscalYear } from "@/lib/fiscal";
import { useUpdateCheck } from "@/lib/update";
import { EChart, type ChartTheme } from "@/components/echart";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Money } from "@/components/money";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/cn";

type TrialRow = {
  name: string;
  debit: string;
  credit: string;
  balance: string;
  account_type: string;
};
type ReportNode = { name: string; amount: string; children?: ReportNode[] };
type BalanceSheet = {
  total_assets: string;
  total_liabilities: string;
  total_equity: string;
  retained_earnings: string;
  assets: ReportNode[];
};
type IncomeStatement = {
  total_income: string;
  total_expenses: string;
  net_income: string;
};
type CashFlow = {
  opening_balance: string;
  closing_balance: string;
  inflows: string;
  outflows: string;
  net_change: string;
};
type InventorySummary = {
  filament_count: number;
  product_count: number;
  total_value: string;
  low_stock_count: number;
  items: Array<{
    id: string;
    name: string;
    kind: "FILAMENT" | "PRODUCT";
    quantity: string;
    unit: "G" | "PCS";
  }>;
};
type Alarm = {
  item_id: string;
  name: string;
  kind: "FILAMENT" | "PRODUCT";
  quantity: string;
  min_quantity: string;
  unit: "G" | "PCS";
  suggested_supplier: string | null;
};
type ProductionSummary = {
  planned: number;
  in_progress: number;
  done: number;
  filament_grams_planned: string;
  jobs: Array<{
    id: string;
    job_number: number;
    product_name: string;
    quantity: string;
    status: string;
    filament_grams: string;
  }>;
};
type Order = {
  id: string;
  order_number: number;
  order_date: string;
  customer_name: string;
  status: string;
  channel: string;
  total?: string;
};
type SalesReport = {
  revenue: string;
  cost: string;
  profit: string;
  orders: number;
  quantity: string;
  rows: Array<{ period: string; revenue: string; cost: string; profit: string; orders: number }>;
};

const ORDER_STATUS_FA: Record<string, string> = {
  NEW: "جدید",
  CONFIRMED: "تأییدشده",
  IN_PRODUCTION: "در تولید",
  READY: "آماده",
  SHIPPED: "ارسال‌شده",
  DELIVERED: "تحویل‌شده",
  CANCELLED: "لغوشده",
};

function num(value: string | number | undefined): number {
  const n = Number(String(value ?? 0).replace(/[^\d.-]/g, ""));
  return Number.isFinite(n) ? n : 0;
}

/** Millions label used by chart axis/label formatters (ECharts callback-safe). */
function fmtMillions(p: { value: unknown }): string {
  return faNumber(String(Math.round(num(p.value as string | number) / 1_000_000))) + " م";
}

/** KPI card — big number, caption and optional signed delta hint. */
function Kpi({
  title,
  children,
  hint,
  testId,
  tone = "neutral",
}: {
  title: string;
  children: React.ReactNode;
  hint?: React.ReactNode;
  testId: string;
  tone?: "neutral" | "positive" | "negative";
}): React.JSX.Element {
  return (
    <Card data-testid={testId} className="overflow-hidden">
      <CardHeader className="pb-2">
        <CardTitle className="text-xs font-medium text-muted-foreground">{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-1">
        <div
          className={cn(
            "text-lg font-bold",
            tone === "positive" && "text-[hsl(var(--positive))]",
            tone === "negative" && "text-[hsl(var(--negative))]",
          )}
        >
          {children}
        </div>
        {hint && <div className="text-xs text-muted-foreground">{hint}</div>}
      </CardContent>
    </Card>
  );
}

function AlertCard({
  tone,
  icon,
  title,
  body,
  onClick,
  testId,
}: {
  tone: "danger" | "warning" | "info" | "success";
  icon: React.ReactNode;
  title: string;
  body: React.ReactNode;
  onClick?: () => void;
  testId: string;
}): React.JSX.Element {
  const tones = {
    danger:
      "border-[hsl(var(--negative))] bg-[hsl(var(--negative)/0.08)] text-[hsl(var(--negative))]",
    warning: "border-amber-500 bg-amber-500/10 text-amber-700 dark:text-amber-400",
    info: "border-sky-500 bg-sky-500/10 text-sky-700 dark:text-sky-400",
    success:
      "border-[hsl(var(--positive))] bg-[hsl(var(--positive)/0.08)] text-[hsl(var(--positive))]",
  } as const;
  return (
    <button
      type="button"
      data-testid={testId}
      onClick={onClick}
      className={cn(
        "flex w-full items-start gap-2 rounded-lg border p-3 text-start text-sm transition-colors",
        tones[tone],
        onClick ? "cursor-pointer hover:opacity-90" : "cursor-default",
      )}
    >
      <span className="mt-0.5 shrink-0">{icon}</span>
      <span className="min-w-0">
        <span className="block font-semibold">{title}</span>
        <span className="block text-xs text-foreground/80">{body}</span>
      </span>
    </button>
  );
}

export function DashboardPage(): React.JSX.Element {
  const navigate = useNavigate();
  const fiscal = currentFiscalYear(new Date().toISOString().slice(0, 10));
  const update = useUpdateCheck();

  const ready = useQuery({
    queryKey: ["health", "ready"],
    queryFn: async () => {
      const res = await api.GET("/api/v1/health/ready");
      await throwIfError(res);
      return res.data as unknown as { status: string; checks: Record<string, unknown> };
    },
  });

  const trial = useQuery({
    queryKey: ["reports", "trial-balance"],
    queryFn: async () => {
      const res = await api.GET("/api/v1/reports/trial-balance");
      await throwIfError(res);
      return (res.data ?? []) as unknown as TrialRow[];
    },
  });

  const balanceSheet = useQuery({
    queryKey: ["reports", "balance-sheet", "dashboard"],
    queryFn: async () => {
      const res = await api.GET("/api/v1/reports/balance-sheet", { params: { query: {} } });
      await throwIfError(res);
      return res.data as unknown as BalanceSheet;
    },
  });

  const income = useQuery({
    queryKey: ["reports", "income-statement", fiscal.startIso, fiscal.endIso],
    queryFn: async () => {
      const res = await api.GET("/api/v1/reports/income-statement", {
        params: { query: { start: fiscal.startIso, end: fiscal.endIso } },
      });
      await throwIfError(res);
      return res.data as unknown as IncomeStatement;
    },
  });

  const cashFlow = useQuery({
    queryKey: ["reports", "cash-flow", fiscal.startIso, fiscal.endIso],
    queryFn: async () => {
      const res = await api.GET("/api/v1/reports/cash-flow", {
        params: { query: { start: fiscal.startIso, end: fiscal.endIso } },
      });
      await throwIfError(res);
      return res.data as unknown as CashFlow;
    },
  });

  const inventory = useQuery({
    queryKey: ["warehouse", "summary", "dashboard"],
    queryFn: async () => {
      const res = await api.GET("/api/v1/warehouse/summary");
      await throwIfError(res);
      return res.data as unknown as InventorySummary;
    },
  });

  const alarms = useQuery({
    queryKey: ["warehouse", "alarms", "dashboard"],
    queryFn: async () => {
      const res = await api.GET("/api/v1/warehouse/alarms");
      await throwIfError(res);
      return (res.data ?? []) as unknown as Alarm[];
    },
  });

  const production = useQuery({
    queryKey: ["production", "summary", "dashboard"],
    queryFn: async () => {
      const res = await api.GET("/api/v1/production/summary");
      await throwIfError(res);
      return res.data as unknown as ProductionSummary;
    },
  });

  const sales = useQuery({
    queryKey: ["orders", "reports", "sales", "daily", "dashboard"],
    queryFn: async () => {
      const res = await api.GET("/api/v1/orders/reports/sales", {
        params: { query: { period: "daily" } },
      });
      await throwIfError(res);
      return res.data as unknown as SalesReport;
    },
  });

  const orders = useQuery({
    queryKey: ["orders", "dashboard"],
    queryFn: async () => {
      const res = await api.GET("/api/v1/orders", { params: { query: {} } });
      await throwIfError(res);
      return (res.data ?? []) as unknown as Order[];
    },
  });

  const trialTotals = React.useMemo(() => {
    const rows = trial.data ?? [];
    const totalDebit = sumMoney(rows.map((r) => r.debit));
    const totalCredit = sumMoney(rows.map((r) => r.credit));
    return { totalDebit, totalCredit, balanced: totalDebit.equals(totalCredit) };
  }, [trial.data]);

  const stockValue = num(inventory.data?.total_value);
  const lowCount = alarms.data?.length ?? 0;
  const openJobs = (production.data?.in_progress ?? 0) + (production.data?.planned ?? 0);
  const pendingOrders = (orders.data ?? []).filter((o) => o.status === "NEW").length;
  const recentOrders = React.useMemo(() => [...(orders.data ?? [])].slice(0, 6), [orders.data]);
  const activeJobs = React.useMemo(
    () =>
      (production.data?.jobs ?? []).filter(
        (j) => j.status === "PLANNED" || j.status === "IN_PROGRESS",
      ),
    [production.data],
  );

  const bs = balanceSheet.data;
  const is = income.data;
  const cf = cashFlow.data;

  const structureOption = React.useCallback(
    (theme: ChartTheme) => ({
      legend: { bottom: 0, textStyle: { color: theme.muted } },
      tooltip: { trigger: "axis" as const, axisPointer: { type: "shadow" as const } },
      grid: { left: 60, right: 20, top: 20, bottom: 50 },
      xAxis: {
        type: "category" as const,
        data: ["دارایی‌ها", "بدهی‌ها", "سرمایه"],
        axisLabel: { color: theme.muted },
        axisLine: { lineStyle: { color: theme.border } },
      },
      yAxis: {
        type: "value" as const,
        axisLabel: {
          color: theme.muted,
          formatter: (v: number) => faNumber(String(Math.round(v / 1_000_000))) + "م",
        },
        splitLine: { lineStyle: { color: theme.border, type: "dashed" as const } },
      },
      series: [
        {
          type: "bar" as const,
          name: "مبلغ (تومان)",
          barWidth: "45%",
          data: [
            { value: num(bs?.total_assets), itemStyle: { color: theme.primary } },
            { value: num(bs?.total_liabilities), itemStyle: { color: theme.negative } },
            { value: num(bs?.total_equity), itemStyle: { color: theme.positive } },
          ],
          label: {
            show: true,
            position: "top" as const,
            color: theme.text,
            formatter: fmtMillions,
          },
        },
      ],
    }),
    [bs],
  );

  const pnlOption = React.useCallback(
    (theme: ChartTheme) => ({
      tooltip: { trigger: "axis" as const },
      grid: { left: 60, right: 20, top: 20, bottom: 40 },
      xAxis: {
        type: "category" as const,
        data: ["درآمد", "هزینه", "سود خالص"],
        axisLabel: { color: theme.muted },
        axisLine: { lineStyle: { color: theme.border } },
      },
      yAxis: {
        type: "value" as const,
        axisLabel: {
          color: theme.muted,
          formatter: (v: number) => faNumber(String(Math.round(v / 1_000_000))) + "م",
        },
        splitLine: { lineStyle: { color: theme.border, type: "dashed" as const } },
      },
      series: [
        {
          type: "bar" as const,
          barWidth: "45%",
          data: [
            { value: num(is?.total_income), itemStyle: { color: theme.positive } },
            { value: num(is?.total_expenses), itemStyle: { color: theme.negative } },
            {
              value: num(is?.net_income),
              itemStyle: { color: num(is?.net_income) >= 0 ? theme.primary : theme.negative },
            },
          ],
          label: { show: true, position: "top" as const, color: theme.text },
        },
      ],
    }),
    [is],
  );

  const salesRows = React.useMemo(() => sales.data?.rows ?? [], [sales.data]);
  const salesOption = React.useCallback(
    (theme: ChartTheme) => ({
      legend: { bottom: 0, textStyle: { color: theme.muted } },
      tooltip: { trigger: "axis" as const },
      grid: { left: 60, right: 20, top: 20, bottom: 50 },
      xAxis: {
        type: "category" as const,
        data: salesRows.map((r) => r.period),
        axisLabel: { color: theme.muted, rotate: salesRows.length > 7 ? 35 : 0 },
        axisLine: { lineStyle: { color: theme.border } },
      },
      yAxis: {
        type: "value" as const,
        axisLabel: {
          color: theme.muted,
          formatter: (v: number) => faNumber(String(Math.round(v / 1_000_000))) + "م",
        },
        splitLine: { lineStyle: { color: theme.border, type: "dashed" as const } },
      },
      series: [
        {
          name: "فروش",
          type: "bar" as const,
          barMaxWidth: 26,
          itemStyle: { color: theme.primary },
          data: salesRows.map((r) => num(r.revenue)),
        },
        {
          name: "بهای تمام‌شده",
          type: "bar" as const,
          barMaxWidth: 26,
          itemStyle: { color: theme.muted },
          data: salesRows.map((r) => num(r.cost)),
        },
        {
          name: "سود",
          type: "line" as const,
          smooth: true,
          lineStyle: { color: theme.positive, width: 3 },
          itemStyle: { color: theme.positive },
          data: salesRows.map((r) => num(r.profit)),
        },
      ],
    }),
    [salesRows],
  );

  const stockRows = React.useMemo(
    () => [...(inventory.data?.items ?? [])].slice(0, 8).reverse(),
    [inventory.data],
  );
  const stockOption = React.useCallback(
    (theme: ChartTheme) => ({
      legend: { bottom: 0, textStyle: { color: theme.muted } },
      tooltip: { trigger: "axis" as const, axisPointer: { type: "shadow" as const } },
      grid: { left: 110, right: 30, top: 20, bottom: 50 },
      xAxis: {
        type: "value" as const,
        axisLabel: { color: theme.muted },
        splitLine: { lineStyle: { color: theme.border, type: "dashed" as const } },
      },
      yAxis: {
        type: "category" as const,
        data: stockRows.map((i) => i.name),
        axisLabel: { color: theme.muted, width: 95, overflow: "truncate" as const },
        axisLine: { lineStyle: { color: theme.border } },
      },
      series: [
        {
          name: "موجودی",
          type: "bar" as const,
          barMaxWidth: 18,
          data: stockRows.map((i) => ({
            value: num(i.quantity),
            itemStyle: { color: i.kind === "FILAMENT" ? theme.primary : theme.positive },
          })),
          label: {
            show: true,
            position: "end" as const,
            color: theme.text,
            formatter: (p: { value: unknown }) => faNumber(String(num(p.value as string | number))),
          },
        },
      ],
    }),
    [stockRows],
  );

  return (
    <div className="space-y-6" dir="rtl">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-xl font-bold">داشبورد</h1>
          <p className="text-xs text-muted-foreground">
            سال مالی {fiscal.label} — {faDate(fiscal.startIso)} تا {faDate(fiscal.endIso)}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {(update.data?.update_available ?? false) && (
            <Badge
              variant="warning"
              className="cursor-pointer"
              data-testid="dashboard-update-badge"
              onClick={() => void navigate({ to: "/system" })}
            >
              نسخهٔ {update.data?.latest} آمادهٔ نصب
            </Badge>
          )}
          <Badge variant={ready.data?.status === "ready" ? "success" : "secondary"}>
            {ready.data?.status === "ready" ? "سیستم آماده" : "در حال بررسی…"}
          </Badge>
        </div>
      </div>

      {/* ——— هشدارها ——— */}
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4" data-testid="dashboard-alerts">
        <AlertCard
          testId="alert-balance"
          tone={trialTotals.balanced ? "success" : "danger"}
          icon={trialTotals.balanced ? <CheckCircle2 size={18} /> : <TriangleAlert size={18} />}
          title={trialTotals.balanced ? "دفاتر متوازن است" : "عدم توازن در دفاتر!"}
          body={
            trialTotals.balanced ? (
              <>
                بدهکار و بستانکار برابر: <Money value={trialTotals.totalDebit.toFixed(4)} />
              </>
            ) : (
              <>
                اختلاف:{" "}
                <Money
                  value={trialTotals.totalDebit.minus(trialTotals.totalCredit).abs().toFixed(4)}
                />
              </>
            )
          }
          onClick={() => void navigate({ to: "/statements" })}
        />
        <AlertCard
          testId="alert-stock"
          tone={lowCount > 0 ? "warning" : "success"}
          icon={lowCount > 0 ? <PackageX size={18} /> : <CheckCircle2 size={18} />}
          title={
            lowCount > 0
              ? `${faNumber(String(lowCount))} هشدار اتمام موجودی`
              : "موجودی انبار کافی است"
          }
          body={
            lowCount > 0
              ? (alarms.data ?? [])
                  .slice(0, 2)
                  .map(
                    (a) =>
                      `${a.name} (${faNumber(a.quantity)} از ${faNumber(a.min_quantity)} ${a.unit === "G" ? "گرم" : "عدد"})`,
                  )
                  .join(" — ")
              : "هیچ کالایی زیر حد بحرانی نیست."
          }
          onClick={() => void navigate({ to: "/warehouse" })}
        />
        <AlertCard
          testId="alert-production"
          tone={openJobs > 0 ? "info" : "success"}
          icon={<Factory size={18} />}
          title={
            openJobs > 0
              ? `${faNumber(String(openJobs))} کار تولید باز`
              : "کار تولیدی در جریان نیست"
          }
          body={
            <>
              فیلامنت موردنیاز: {faNumber(production.data?.filament_grams_planned ?? "0")} گرم —
              تمام‌شده: {faNumber(String(production.data?.done ?? 0))}
            </>
          }
          onClick={() => void navigate({ to: "/production" })}
        />
        <AlertCard
          testId="alert-orders"
          tone={pendingOrders > 0 ? "warning" : "info"}
          icon={pendingOrders > 0 ? <ShoppingCart size={18} /> : <AlertTriangle size={18} />}
          title={
            pendingOrders > 0
              ? `${faNumber(String(pendingOrders))} سفارش جدید`
              : "سفارش جدیدی ثبت نشده"
          }
          body={
            (update.data?.update_available ?? false) ? (
              <span className="flex items-center gap-1">
                <ArrowUpCircle size={14} /> به‌روزرسانی {update.data?.latest} موجود است
              </span>
            ) : (
              `${faNumber(String((orders.data ?? []).length))} سفارش ثبت‌شده`
            )
          }
          onClick={() => void navigate({ to: "/orders" })}
        />
      </div>

      {/* ——— شاخص‌ها ——— */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-6">
        <Kpi title="دارایی‌ها" testId="kpi-assets" hint="مانده دارایی تا امروز">
          <Money value={bs?.total_assets} />
        </Kpi>
        <Kpi title="بدهی‌ها" testId="kpi-liabilities" tone="negative">
          <Money value={bs?.total_liabilities} />
        </Kpi>
        <Kpi title="حقوق صاحبان سهام" testId="kpi-equity" tone="positive">
          <Money value={bs?.total_equity} />
        </Kpi>
        <Kpi
          title="سود خالص دورهٔ جاری"
          testId="kpi-net-income"
          tone={num(is?.net_income) >= 0 ? "positive" : "negative"}
          hint={`درآمد ${faNumber(String(Math.round(num(is?.total_income) / 1_000_000)))} م / هزینه ${faNumber(String(Math.round(num(is?.total_expenses) / 1_000_000)))} م`}
        >
          <Money value={is?.net_income} />
        </Kpi>
        <Kpi
          title="ارزش موجودی انبار"
          testId="kpi-stock-value"
          hint={`${faNumber(String(inventory.data?.filament_count ?? 0))} فیلامنت / ${faNumber(String(inventory.data?.product_count ?? 0))} محصول`}
        >
          <Money value={stockValue > 0 ? String(stockValue) : "0"} currency="TOMAN" />
        </Kpi>
        <Kpi
          title="گردش نقدی خالص"
          testId="kpi-cash"
          tone={num(cf?.net_change) >= 0 ? "positive" : "negative"}
          hint={
            <>
              مانده پایان: <Money value={cf?.closing_balance} />
            </>
          }
        >
          <Money value={cf?.net_change} signedColors />
        </Kpi>
      </div>

      {/* ——— نمودارها ——— */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">ساختار مالی</CardTitle>
          </CardHeader>
          <CardContent>
            <EChart buildOption={structureOption} height={260} data-testid="chart-structure" />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">سود و زیان — سال مالی {fiscal.label}</CardTitle>
          </CardHeader>
          <CardContent>
            <EChart buildOption={pnlOption} height={260} data-testid="chart-pnl" />
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">روند فروش روزانه</CardTitle>
            <span className="text-xs text-muted-foreground">
              جمع فروش: <Money value={sales.data?.revenue} />
            </span>
          </CardHeader>
          <CardContent>
            {salesRows.length > 0 ? (
              <EChart buildOption={salesOption} height={280} data-testid="chart-sales" />
            ) : (
              <p className="py-16 text-center text-sm text-muted-foreground">فروشی ثبت نشده است.</p>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">ترکیب موجودی انبار</CardTitle>
            <span className="text-xs text-muted-foreground">
              ارزش کل: <Money value={stockValue > 0 ? String(stockValue) : "0"} currency="TOMAN" />
            </span>
          </CardHeader>
          <CardContent>
            {stockRows.length > 0 ? (
              <EChart buildOption={stockOption} height={280} data-testid="chart-stock" />
            ) : (
              <p className="py-16 text-center text-sm text-muted-foreground">
                کالایی در انبار ثبت نشده است.
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* ——— صف‌ها ——— */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">آخرین سفارش‌ها</CardTitle>
            <button
              type="button"
              className="text-xs text-primary hover:underline"
              onClick={() => void navigate({ to: "/orders" })}
            >
              همهٔ سفارش‌ها
            </button>
          </CardHeader>
          <CardContent>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-muted-foreground">
                  <th className="py-2 text-start font-medium">#</th>
                  <th className="py-2 text-start font-medium">مشتری</th>
                  <th className="py-2 text-start font-medium">تاریخ</th>
                  <th className="py-2 text-start font-medium">وضعیت</th>
                </tr>
              </thead>
              <tbody>
                {recentOrders.map((o) => (
                  <tr key={o.id} className="border-b" data-testid={`dash-order-${o.id}`}>
                    <td className="num py-2">{faNumber(String(o.order_number))}</td>
                    <td className="py-2">{o.customer_name}</td>
                    <td className="num py-2 text-xs">{faDate(o.order_date)}</td>
                    <td className="py-2 text-xs">{ORDER_STATUS_FA[o.status] ?? o.status}</td>
                  </tr>
                ))}
                {recentOrders.length === 0 && (
                  <tr>
                    <td colSpan={4} className="py-6 text-center text-muted-foreground">
                      سفارشی ثبت نشده است.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">کارهای تولید در جریان</CardTitle>
            <button
              type="button"
              className="text-xs text-primary hover:underline"
              onClick={() => void navigate({ to: "/production" })}
            >
              صفحهٔ تولید
            </button>
          </CardHeader>
          <CardContent>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-muted-foreground">
                  <th className="py-2 text-start font-medium">#</th>
                  <th className="py-2 text-start font-medium">محصول</th>
                  <th className="py-2 text-start font-medium">تعداد</th>
                  <th className="py-2 text-start font-medium">فیلامنت (گرم)</th>
                </tr>
              </thead>
              <tbody>
                {activeJobs.map((j) => (
                  <tr key={j.id} className="border-b" data-testid={`dash-job-${j.id}`}>
                    <td className="num py-2">{faNumber(String(j.job_number))}</td>
                    <td className="py-2">{j.product_name}</td>
                    <td className="num py-2">{faNumber(j.quantity)}</td>
                    <td className="num py-2">
                      {faNumber(String(num(j.filament_grams) * num(j.quantity)))}
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
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
