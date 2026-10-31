import { useCalendar } from "@/lib/calendar-settings";
/**
 * دفتر اسناد — virtualized grid (50k rows) with pinned summary footer.
 *
 * Every row opens the entry itself: read it, correct it, and change its status
 * (پیش‌نویس → ثبت‌شده → ابطال‌شده). Editing is done as the invoice the entry
 * came from, so بدهکار/بستانکار never appears on this screen (item 11).
 */
import * as React from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { api, parseError } from "@/api/client";
import { VirtualTable } from "@/components/virtual-table";
import { QueryNotice } from "@/components/query-notice";
import { SearchFilterBar } from "@/components/search-filter-bar";
import { Money } from "@/components/money";
import { Badge } from "@/components/ui/badge";
import { JournalEntryDrawer, type JournalEntryRow } from "@/components/journal-entry-drawer";
import { faDate, faDigits } from "@/lib/fa";
import { sumMoney } from "@/lib/money";

export function JournalListPage(): React.JSX.Element {
  const { calendar } = useCalendar();
  const { t } = useTranslation("ledger");
  const [selectedId, setSelectedId] = React.useState<string | null>(null);

  const entriesQuery = useQuery({
    queryKey: ["journal-entries"],
    queryFn: async () => {
      const res = await api.GET("/api/v1/journal-entries", {
        params: { query: { limit: 200 } },
      });
      if (res.error) throw await parseError(res.response);
      return res.data as unknown as JournalEntryRow[];
    },
  });

  const accountsQuery = useQuery({
    queryKey: ["accounts"],
    queryFn: async () => {
      const res = await api.GET("/api/v1/accounts");
      if (res.error) throw await parseError(res.response);
      return res.data as unknown as Array<{ id: string; code: string; name: string }>;
    },
  });
  const accountLabels = React.useMemo(
    () => new Map((accountsQuery.data ?? []).map((a) => [a.id, `${a.code} — ${a.name}`])),
    [accountsQuery.data],
  );

  const columns = React.useMemo<Array<ColumnDef<JournalEntryRow, unknown>>>(
    () => [
      {
        accessorKey: "entry_number",
        header: t("journalList.entryNumber"),
        size: 90,
        cell: (info) => faDigits(String(info.getValue())),
      },
      {
        accessorKey: "transaction_date",
        header: t("journalList.date"),
        size: 110,
        cell: (info) => faDate(String(info.getValue()), calendar),
      },
      { accessorKey: "description", header: t("journalList.description"), size: 260 },
      {
        id: "total_debit",
        header: t("journalList.debit"),
        size: 130,
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
        size: 130,
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
          // The API speaks DRAFT/POSTED/VOIDED; the old page compared lowercase
          // and so labelled every entry «پیش‌نویس».
          const v = String(info.getValue()).toUpperCase();
          return (
            <Badge
              data-testid="entry-status"
              variant={v === "POSTED" ? "success" : v === "VOIDED" ? "destructive" : "secondary"}
            >
              {v === "POSTED"
                ? t("journalList.statusPosted")
                : v === "VOIDED"
                  ? t("journalList.statusVoid")
                  : t("journalList.statusDraft")}
            </Badge>
          );
        },
      },
      {
        id: "actions",
        header: t("journalList.actions"),
        size: 120,
        cell: (info) => (
          <button
            type="button"
            className="rounded border px-2 py-1 text-xs hover:bg-accent"
            data-testid={`entry-open-${info.row.original.entry_number}`}
            onClick={(event) => {
              event.stopPropagation();
              setSelectedId(info.row.original.id);
            }}
          >
            {t("journalList.open")}
          </button>
        ),
      },
    ],
    [t, calendar],
  );

  const rows = entriesQuery.data ?? [];
  const selected = rows.find((row) => row.id === selectedId) ?? null;
  const totalDebit = sumMoney(rows.flatMap((r) => (r.splits ?? []).map((s) => s.debit)));
  const totalCredit = sumMoney(rows.flatMap((r) => (r.splits ?? []).map((s) => s.credit)));

  return (
    <div className="space-y-4" dir="rtl">
      <h1 className="text-xl font-bold">{t("journalList.title")}</h1>
      <p className="text-sm text-muted-foreground">{t("journalList.hint")}</p>
      <SearchFilterBar entity="entry" data-testid="journal-search" />
      <QueryNotice query={entriesQuery} />
      {entriesQuery.isSuccess && rows.length === 0 && (
        <p className="text-sm text-muted-foreground" data-testid="journal-empty">
          {t("journalList.empty")}
        </p>
      )}
      <VirtualTable<JournalEntryRow>
        columns={columns}
        data={rows}
        onRowClick={(row) => setSelectedId(row.id)}
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
      {selected && (
        <JournalEntryDrawer
          entry={selected}
          accounts={accountLabels}
          onClose={() => setSelectedId(null)}
        />
      )}
    </div>
  );
}
