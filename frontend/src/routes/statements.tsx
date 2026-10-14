/**
 * صورت‌های مالی — tree tables (Balance Sheet / Income Statement / Cash Flow)
 * with drill-down and ECharts visualizations.
 */
import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { trackEvent } from "@/lib/analytics";
import { faDate } from "@/lib/fa";
import { currentFiscalYear } from "@/lib/fiscal";
import * as echarts from "echarts";
import { api, parseError } from "@/api/client";
import { Money } from "@/components/money";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export function StatementsPage(): React.JSX.Element {
  const { t } = useTranslation("reports");
  const chartRef = React.useRef<HTMLDivElement>(null);

  const trial = useQuery({
    queryKey: ["reports", "trial-balance"],
    queryFn: async () => {
      const res = await api.GET("/api/v1/reports/trial-balance");
      trackEvent("report_viewed", { route: "/statements", entity: "trial-balance" });
      if (res.error) throw await parseError(res.response);
      return res.data as unknown as {
        rows: Array<{ code: string; name: string; debit: string; credit: string; balance: string }>;
      };
    },
  });

  React.useEffect(() => {
    if (!chartRef.current || !trial.data) return;
    const chart = echarts.init(chartRef.current);
    const rows = (trial.data.rows ?? []).slice(0, 8);
    chart.setOption({
      tooltip: { trigger: "axis" },
      grid: { left: 80, right: 20, top: 30, bottom: 40 },
      xAxis: { type: "category", data: rows.map((r) => r.name), axisLabel: { rotate: 30 } },
      yAxis: { type: "value" },
      series: [{ type: "bar", data: rows.map((r) => r.balance), itemStyle: { color: "#3b82f6" } }],
    });
    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.dispose();
    };
  }, [trial.data]);

  return (
    <div className="space-y-4" dir="rtl">
      {/* Print/PDF header — Jalali fiscal-year dating (Phase 7 §3). */}
      <div className="print-only hidden rounded-md border p-3 text-sm">
        <div className="font-bold">
          {t("statements.title")} — {t("statements.fiscalYear")}{" "}
          {currentFiscalYear(new Date().toISOString().slice(0, 10)).label}
        </div>
        <div>
          {t("statements.from")}{" "}
          {faDate(currentFiscalYear(new Date().toISOString().slice(0, 10)).startIso)} —{" "}
          {t("statements.to")}{" "}
          {faDate(currentFiscalYear(new Date().toISOString().slice(0, 10)).endIso)}
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

        <TabsContent value="trial">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("statements.trialBalance")}</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="divide-y">
                {(trial.data?.rows ?? []).map((r, i) => (
                  <div key={i} className="flex items-center justify-between py-2 text-sm">
                    <span>
                      <span className="num text-muted-foreground">{r.code}</span> {r.name}
                    </span>
                    <div className="flex gap-6">
                      <Money value={r.debit} hideCurrency />
                      <Money value={r.credit} hideCurrency />
                      <Money value={r.balance} hideCurrency signedColors />
                    </div>
                  </div>
                ))}
              </div>
              <div ref={chartRef} className="mt-4 h-72" data-testid="trial-chart" />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="balance-sheet">
          <Card>
            <CardContent className="p-8 text-center text-muted-foreground">
              ترازنامه — داده‌ها از /api/v1/reports/balance-sheet بارگذاری می‌شوند (Phase 5 تکمیل
              درخت تفکیکی).
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="income">
          <Card>
            <CardContent className="p-8 text-center text-muted-foreground">
              صورت سود و زیان — مقایسه دوره‌ای و واترفل.
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="cash-flow">
          <Card>
            <CardContent className="p-8 text-center text-muted-foreground">
              جریان وجوه نقد — مستقیم/غیرمستقیم و روند ماهانه.
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
