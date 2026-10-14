/** داشبورد — readiness strip + net-worth style KPI cards. */
import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { api, throwIfError } from "@/api/client";
import { sumMoney } from "@/lib/money";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Money } from "@/components/money";
import { Badge } from "@/components/ui/badge";

export function DashboardPage(): React.JSX.Element {
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
      return (res.data ?? []) as unknown as Array<{ debit: string; credit: string }>;
    },
  });

  const trialTotals = React.useMemo(() => {
    const rows = trial.data ?? [];
    const totalDebit = sumMoney(rows.map((r) => r.debit));
    const totalCredit = sumMoney(rows.map((r) => r.credit));
    return { totalDebit, totalCredit, balanced: totalDebit.equals(totalCredit) };
  }, [trial.data]);

  return (
    <div className="space-y-6" dir="rtl">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">داشبورد</h1>
        <Badge variant={ready.data?.status === "ready" ? "success" : "secondary"}>
          {ready.data?.status === "ready" ? "سیستم آماده" : "در حال بررسی…"}
        </Badge>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground">جمع بدهکار (ترازنامه آزمایشی)</CardTitle>
          </CardHeader>
          <CardContent>
            <Money value={trialTotals.totalDebit.toFixed(4)} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground">جمع بستانکار</CardTitle>
          </CardHeader>
          <CardContent>
            <Money value={trialTotals.totalCredit.toFixed(4)} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground">توازن</CardTitle>
          </CardHeader>
          <CardContent>
            <Badge variant={trialTotals.balanced ? "success" : "destructive"}>
              {trialTotals.balanced ? "متوازن ✓" : "نامتوازن"}
            </Badge>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
