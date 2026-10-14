/**
 * Virtualized ledger grid — TanStack Table v8 + TanStack Virtual.
 * 50 000 rows at 60 FPS: only visible rows render, sticky header + pinned
 * summary footer (Cleared Balance / Unreconciled Delta / Working Balance).
 */
import * as React from "react";
import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import { cn } from "@/lib/cn";

export interface VirtualTableProps<T> {
  columns: Array<ColumnDef<T, unknown>>;
  data: T[];
  /** Pinned summary footer cells (left→right in DOM; RTL-aware). */
  footer?: React.ReactNode;
  estimateRowHeight?: number;
  className?: string;
  onRowClick?: (row: T) => void;
  emptyText?: string;
}

export function VirtualTable<T>({
  columns,
  data,
  footer,
  estimateRowHeight = 40,
  className,
  onRowClick,
  emptyText = "داده‌ای موجود نیست",
}: VirtualTableProps<T>): React.JSX.Element {
  const [sorting, setSorting] = React.useState<SortingState>([]);
  const parentRef = React.useRef<HTMLDivElement>(null);

  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  const { rows } = table.getRowModel();
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => estimateRowHeight,
    overscan: 24,
  });

  return (
    <div className={cn("flex flex-col rounded-lg border bg-card", className)}>
      <div ref={parentRef} className="scrollbar-thin max-h-[60vh] overflow-auto" role="grid" aria-rowcount={rows.length}>
        <table className="w-full text-sm" style={{ width: table.getCenterTotalSize() }}>
          <thead className="sticky top-0 z-10 bg-card shadow-[0_1px_0_hsl(var(--border))]">
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <th
                    key={header.id}
                    className="h-10 whitespace-nowrap px-2 text-end font-medium text-muted-foreground select-none"
                    style={{ width: header.getSize() }}
                    onClick={header.column.getToggleSortingHandler()}
                    aria-sort={
                      header.column.getIsSorted() === "asc"
                        ? "ascending"
                        : header.column.getIsSorted() === "desc"
                          ? "descending"
                          : undefined
                    }
                  >
                    <div className="flex items-center gap-1 cursor-pointer">
                      {flexRender(header.column.columnDef.header, header.getContext())}
                      {header.column.getIsSorted() === "asc" ? " ▲" : header.column.getIsSorted() === "desc" ? " ▼" : ""}
                    </div>
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody
            style={{ height: `${virtualizer.getTotalSize()}px`, position: "relative" }}
          >
            {virtualizer.getVirtualItems().map((virtualRow) => {
              const row = rows[virtualRow.index];
              return (
                <tr
                  key={row.id}
                  data-index={virtualRow.index}
                  ref={virtualizer.measureElement}
                  className={cn(
                    "absolute w-full border-b border-border/40 hover:bg-muted/50",
                    onRowClick && "cursor-pointer",
                  )}
                  style={{ transform: `translateY(${virtualRow.start}px)` }}
                  onClick={() => onRowClick?.(row.original)}
                >
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="px-2 py-2 whitespace-nowrap" style={{ width: cell.column.getSize() }}>
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              );
            })}
            {rows.length === 0 && (
              <tr>
                <td colSpan={columns.length} className="p-8 text-center text-muted-foreground">
                  {emptyText}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {footer && (
        <div className="sticky bottom-0 border-t bg-muted/60 backdrop-blur px-2 py-2 text-sm font-medium">{footer}</div>
      )}
    </div>
  );
}
