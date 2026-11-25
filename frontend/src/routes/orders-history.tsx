/**
 * تاریخچهٔ سفارشات — shipped, delivered and cancelled orders (item 7).
 *
 * The live orders page keeps only active work; this page is the workshop's
 * archive. Only cancelled orders may be restored to the live order flow.
 */
import * as React from "react";
import { Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, parseError } from "@/api/client";
import { QueryNotice } from "@/components/query-notice";
import { OperationPagination, OPERATION_PAGE_SIZE } from "@/components/operation-pagination";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Money } from "@/components/money";
import { CalendarInput } from "@/components/calendar-input";
import { useCalendar } from "@/lib/calendar-settings";
import { faDate, faNumber } from "@/lib/fa";
import { cn } from "@/lib/cn";

type HistoryOrder = {
  id: string;
  order_number: number;
  order_date: string;
  customer_name: string;
  customer_phone: string | null;
  customer_address: string | null;
  status: string;
  channel: "direct" | "marketplace";
  notes: string | null;
  version_id: number;
  items: Array<{
    id: string;
    product_name: string;
    variant: "plain" | "chain";
    quantity: string;
    unit_price: string;
    unit_cost: string;
    inventory_item_id: string | null;
  }>;
  warnings?: string[];
  total: string;
  total_cost: string;
  profit: string;
};

const HISTORY_STATUSES = ["SHIPPED", "DELIVERED", "CANCELLED"] as const;

const STATUS_LABEL: Record<string, string> = {
  NEW: "جدید",
  CONFIRMED: "تأییدشده",
  IN_PRODUCTION: "در حال تولید",
  READY: "آمادهٔ ارسال",
  SHIPPED: "ارسال‌شده",
  DELIVERED: "تحویل‌شده",
  CANCELLED: "لغو‌شده",
};

const STATUS_VARIANT: Record<string, "secondary" | "warning" | "success" | "destructive"> = {
  SHIPPED: "success",
  DELIVERED: "success",
  CANCELLED: "destructive",
};

export function OrdersHistoryPage(): React.JSX.Element {
  const { calendar, ready: calendarReady } = useCalendar();
  const [page, setPage] = React.useState(0);
  const [statusFilter, setStatusFilter] = React.useState("");
  const [search, setSearch] = React.useState("");
  const [dateFrom, setDateFrom] = React.useState("");
  const [dateTo, setDateTo] = React.useState("");
  const [fromInvalid, setFromInvalid] = React.useState(false);
  const [toInvalid, setToInvalid] = React.useState(false);
  const [openItems, setOpenItems] = React.useState<string | null>(null);
  const [message, setMessage] = React.useState("");
  const queryClient = useQueryClient();

  const filtersReady =
    calendarReady && !fromInvalid && !toInvalid && !(dateFrom && dateTo && dateFrom > dateTo);

  const historyQuery = useQuery({
    enabled: filtersReady,
    queryKey: ["orders", "history", statusFilter, search, dateFrom, dateTo, page],
    queryFn: async () => {
      const res = await api.GET("/api/v1/orders", {
        params: {
          query: {
            status_group: "history",
            limit: OPERATION_PAGE_SIZE + 1,
            offset: page * OPERATION_PAGE_SIZE,
            ...(statusFilter ? { status: statusFilter } : {}),
            ...(search ? { search } : {}),
            ...(dateFrom ? { date_from: dateFrom } : {}),
            ...(dateTo ? { date_to: dateTo } : {}),
          },
        },
      });
      if (res.error) throw await parseError(res.response);
      return res.data as unknown as HistoryOrder[];
    },
  });

  const restore = useMutation({
    mutationFn: async (order: HistoryOrder) => {
      const res = await api.POST("/api/v1/orders/{order_id}/restore", {
        params: { path: { order_id: order.id } },
        body: { version_id: order.version_id },
      });
      if (res.error) throw await parseError(res.response);
      return res.data;
    },
    onSuccess: (order) => {
      setMessage(
        `سفارش #${faNumber(String(order.order_number))} بازیابی شد و با وضعیت «${STATUS_LABEL[order.status]}» به سفارش‌های فعال بازگشت.`,
      );
      void queryClient.invalidateQueries({ queryKey: ["orders"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (error) => {
      setMessage(error instanceof Error ? error.message : "بازیابی سفارش ناموفق بود.");
      void queryClient.invalidateQueries({ queryKey: ["orders"] });
    },
  });

  return (
    <div className="space-y-6" dir="rtl">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-xl font-bold">تاریخچهٔ سفارشات</h1>
          <p className="text-xs text-muted-foreground">
            سفارش‌های ارسال‌شده، تحویل‌شده و لغوشده؛ سفارش لغوشده قابل بازیابی است. برای سفارش‌های
            لغوشدهٔ قدیمی که وضعیت پیشین ثبت نشده، وضعیت بر اساس کارهای تولید تعیین می‌شود و در نبود
            تولید، «جدید» خواهد بود.
          </p>
        </div>
        <Link
          to="/orders"
          data-testid="orders-history-back"
          className="inline-flex h-9 items-center rounded-md border border-input px-3 text-sm hover:bg-accent"
        >
          بازگشت به سفارش‌های فعال
        </Link>
      </div>

      {message && (
        <p
          role="status"
          data-testid="history-message"
          className="rounded-md bg-muted px-3 py-2 text-sm"
        >
          {message}
        </p>
      )}
      <Card className="min-w-0">
        <CardHeader>
          <CardTitle className="text-base">سفارش‌های بسته‌شده</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap items-end gap-2">
            <div className="w-40">
              <Label className="text-xs">جستجو</Label>
              <Input
                data-testid="history-search"
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setPage(0);
                }}
                placeholder="نام/تلفن/آدرس مشتری"
              />
            </div>
            <div className="w-32">
              <Label className="text-xs">وضعیت</Label>
              <select
                className="flex h-9 w-full rounded-md border border-input bg-background px-2 text-sm text-foreground"
                value={statusFilter}
                data-testid="history-status"
                onChange={(e) => {
                  setStatusFilter(e.target.value);
                  setPage(0);
                }}
              >
                <option value="">همه</option>
                {HISTORY_STATUSES.map((value) => (
                  <option key={value} value={value}>
                    {STATUS_LABEL[value]}
                  </option>
                ))}
              </select>
            </div>
            <div className="w-36">
              <CalendarInput
                id="history-from"
                label="از تاریخ"
                value={dateFrom}
                onInvalidChange={setFromInvalid}
                onChange={(iso) => {
                  setDateFrom(iso);
                  setPage(0);
                }}
              />
            </div>
            <div className="w-36">
              <CalendarInput
                id="history-to"
                label="تا تاریخ"
                value={dateTo}
                onInvalidChange={setToInvalid}
                onChange={(iso) => {
                  setDateTo(iso);
                  setPage(0);
                }}
              />
            </div>
          </div>
          {dateFrom && dateTo && dateFrom > dateTo && (
            <p role="alert" className="text-destructive">
              ابتدای بازه نباید پس از انتهای آن باشد.
            </p>
          )}

          <QueryNotice query={historyQuery} />
          <div className="overflow-x-auto">
            <table className="w-full min-w-[44rem] text-sm">
              <thead>
                <tr className="border-b text-muted-foreground">
                  <th className="py-2 text-start font-medium">#</th>
                  <th className="py-2 text-start font-medium">تاریخ</th>
                  <th className="py-2 text-start font-medium">مشتری</th>
                  <th className="py-2 text-start font-medium">اقلام</th>
                  <th className="py-2 text-start font-medium">مبلغ</th>
                  <th className="py-2 text-start font-medium">سود</th>
                  <th className="py-2 text-start font-medium">وضعیت</th>
                  <th className="py-2 text-start font-medium">اقدام</th>
                </tr>
              </thead>
              <tbody>
                {(filtersReady && historyQuery.isSuccess
                  ? historyQuery.data.slice(0, OPERATION_PAGE_SIZE)
                  : []
                ).map((order) => (
                  <React.Fragment key={order.id}>
                    <tr className="border-b" data-testid={`history-order-${order.id}`}>
                      <td className="num py-2">{faNumber(String(order.order_number))}</td>
                      <td className="py-2">{faDate(order.order_date, calendar)}</td>
                      <td className="py-2">
                        {order.customer_name}
                        {order.customer_phone && (
                          <div className="num text-xs text-muted-foreground">
                            {faNumber(order.customer_phone)}
                          </div>
                        )}
                      </td>
                      <td className="py-2">
                        <button
                          type="button"
                          aria-expanded={openItems === order.id}
                          aria-controls={`history-items-${order.id}`}
                          data-testid={`history-order-${order.id}-items-toggle`}
                          className={cn(
                            "inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs hover:bg-accent",
                            openItems === order.id && "bg-accent",
                          )}
                          onClick={() =>
                            setOpenItems((current) => (current === order.id ? null : order.id))
                          }
                        >
                          <span className="num">{faNumber(String(order.items.length))}</span>
                          قلم
                        </button>
                      </td>
                      <td className="py-2">
                        <Money value={order.total} currency="TOMAN" />
                      </td>
                      <td className="py-2">
                        <Money value={order.profit} currency="TOMAN" />
                      </td>
                      <td className="py-2">
                        <Badge variant={STATUS_VARIANT[order.status] ?? "secondary"}>
                          {STATUS_LABEL[order.status] ?? order.status}
                        </Badge>
                      </td>
                      <td className="py-2">
                        <a
                          className="inline-flex h-8 items-center rounded-md border border-input px-3 text-xs hover:bg-accent"
                          href={`/api/v1/orders/${order.id}/proforma.pdf`}
                          target="_blank"
                          rel="noreferrer"
                        >
                          پیش‌فاکتور
                        </a>
                        {order.status === "CANCELLED" && (
                          <Button
                            size="sm"
                            variant="outline"
                            className="ms-1"
                            data-testid={`history-order-${order.id}-restore`}
                            disabled={restore.isPending}
                            onClick={() => restore.mutate(order)}
                          >
                            بازیابی سفارش
                          </Button>
                        )}
                      </td>
                    </tr>
                    {openItems === order.id && (
                      <tr
                        id={`history-items-${order.id}`}
                        data-testid={`history-order-${order.id}-items`}
                        className="border-b bg-muted/40"
                      >
                        <td colSpan={8} className="px-2 py-2">
                          <ul className="space-y-1 text-xs" aria-label="اقلام سفارش">
                            {order.items.map((line, index) => (
                              <li
                                key={index}
                                className="flex items-center justify-between gap-2 rounded border bg-background px-2 py-1"
                              >
                                <span>
                                  {line.product_name}
                                  {line.variant === "chain" ? " (زنجیر)" : ""}
                                </span>
                                <span className="num text-muted-foreground">
                                  ×{faNumber(line.quantity)}
                                  {line.unit_price && (
                                    <>
                                      {" — "}
                                      <Money
                                        value={line.unit_price}
                                        currency="TOMAN"
                                        hideCurrency
                                      />
                                    </>
                                  )}
                                </span>
                              </li>
                            ))}
                          </ul>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))}
                {filtersReady && historyQuery.isSuccess && historyQuery.data.length === 0 && (
                  <tr>
                    <td colSpan={8} className="py-6 text-center text-muted-foreground">
                      سفارش بسته‌شده‌ای ثبت نشده است.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <OperationPagination
            page={page}
            next={
              filtersReady &&
              historyQuery.isSuccess &&
              historyQuery.data.length > OPERATION_PAGE_SIZE
            }
            busy={historyQuery.isFetching}
            onChange={setPage}
          />
        </CardContent>
      </Card>
    </div>
  );
}
