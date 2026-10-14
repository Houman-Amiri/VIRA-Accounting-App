/** دفتر اسناد — virtualized grid (50k rows) with pinned summary footer. */
import * as React from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { api, parseError } from "@/api/client";
import { VirtualTable } from "@/components/virtual-table";
import { SearchFilterBar } from "@/components/search-filter-bar";
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
  const { t } = useTranslation("ledger");
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
        header: t("journalList.entryNumber"),
        size: 110,
        cell: (info) => faDigits(String(info.getValue())),
      },
      {
        accessorKey: "transaction_date",
        header: t("journalList.date"),
        size: 110,
        cell: (info) => faDate(String(info.getValue())),
      },
      { accessorKey: "description", header: t("journalList.description"), size: 280 },
      {
        id: "total_debit",
        header: t("journalList.debit"),
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
        header: t("journalList.credit"),
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
        header: t("journalList.status"),
        size: 100,
        cell: (info) => {
          const v = String(info.getValue());
          return (
            <Badge
              variant={v === "posted" ? "success" : v === "voided" ? "destructive" : "secondary"}
            >
              {v === "posted"
                ? t("journalList.statusPosted")
                : v === "voided"
                  ? t("journalList.statusVoid")
                  : t("journalList.statusDraft")}
            </Badge>
          );
        },
      },
    ],
    [t],
  );

  const rows = entriesQuery.data ?? [];
  const totalDebit = sumMoney(rows.flatMap((r) => (r.splits ?? []).map((s) => s.debit)));
  const totalCredit = sumMoney(rows.flatMap((r) => (r.splits ?? []).map((s) => s.credit)));

  return (
    <div className="space-y-4" dir="rtl">
      <h1 className="text-xl font-bold">{t("journalList.title")}</h1>
      <SearchFilterBar entity="entry" data-testid="journal-search" />
      <VirtualTable<EntryRow>
        columns={columns}
        data={rows}
        footer={
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">{t("journalList.total")}</span>
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
