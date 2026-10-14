/** دفتر اسناد — virtualized grid (50k rows) with pinned summary footer. */
import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { api, parseError } from "@/api/client";
import { VirtualTable } from "@/components/virtual-table";
import { Money } from "@/components/money";
import { Badge } from "@/components/ui/badge";
import { faDate, faDigits } from "@/lib/fa";
import { sumMoney } from "@/lib/money";

interface EntryRow {
  id: string;
  entry_number: number;
  transaction_date: string;
  description: string;
  status: "draft" | "posted" | "voided";
  splits: Array<{ debit: string; credit: string }>;
}

export function JournalListPage(): React.JSX.Element {
  const entriesQuery = useQuery({
    queryKey: ["journal-entries"],
    queryFn: async () => {
      const res = await api.GET("/api/v1/journal-entries");
      if (res.error) throw await parseError(res.response);
      return res.data as unknown as EntryRow[];
    },
  });

  const columns = React.useMemo<Array<ColumnDef<EntryRow, unknown>>>(
    () => [
      {
        accessorKey: "entry_number",
        header: "شماره سند",
        size: 110,
        cell: (info) => faDigits(String(info.getValue())),
      },
      {
        accessorKey: "transaction_date",
        header: "تاریخ",
        size: 110,
        cell: (info) => faDate(String(info.getValue())),
      },
      { accessorKey: "description", header: "شرح", size: 280 },
      {
        id: "total_debit",
        header: "بدهکار",
        size: 150,
        cell: (info) => (
          <Money
            value={sumMoney((info.row.original.splits ?? []).map((s) => s.debit)).toFixed(4)}
            hideCurrency
          />
        ),
      },
      {
        id: "total_credit",
        header: "بستانکار",
        size: 150,
        cell: (info) => (
          <Money
            value={sumMoney((info.row.original.splits ?? []).map((s) => s.credit)).toFixed(4)}
            hideCurrency
          />
        ),
      },
      {
        accessorKey: "status",
        header: "وضعیت",
        size: 100,
        cell: (info) => {
          const v = String(info.getValue());
          return (
            <Badge variant={v === "posted" ? "success" : v === "voided" ? "destructive" : "secondary"}>
              {v === "posted" ? "ثبت‌شده" : v === "voided" ? "ابطال‌شده" : "پیش‌نویس"}
            </Badge>
          );
        },
      },
    ],
    [],
  );

  const rows = entriesQuery.data ?? [];
  const totalDebit = sumMoney(rows.flatMap((r) => (r.splits ?? []).map((s) => s.debit)));
  const totalCredit = sumMoney(rows.flatMap((r) => (r.splits ?? []).map((s) => s.credit)));

  return (
    <div className="space-y-4" dir="rtl">
      <h1 className="text-xl font-bold">دفتر اسناد</h1>
      <VirtualTable<EntryRow>
        columns={columns}
        data={rows}
        footer={
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">جمع کل</span>
            <div className="flex gap-8">
              <Money value={totalDebit.toFixed(4)} />
              <Money value={totalCredit.toFixed(4)} />
            </div>
          </div>
        }
      />
    </div>
  );
}
