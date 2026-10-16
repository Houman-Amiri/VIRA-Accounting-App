/**
 * سفارش‌ها — customer orders (MASTER_PROMPT §3.2).
 *
 * Order list with status/channel/search/date filters, a line-item form whose
 * unit price can be filled straight from the pricing engine (قیمت نهایی.xlsx),
 * status transitions, proforma PDF download and the daily/weekly/monthly/annual
 * sales report.
 */
import * as React from "react";
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
import { computePrice, parseNum, type PriceInputs } from "@/lib/priceCalc";
import { pricingConstants, usePricingSettings } from "@/lib/pricing-settings";
import { CalendarInput } from "@/components/calendar-input";
import { useCalendar } from "@/lib/calendar-settings";
import { tehranToday, validIso } from "@/lib/calendar";
import { faDate, faNumber } from "@/lib/fa";

type OrderLine = {
  product_name: string;
  variant: "plain" | "chain";
  quantity: string;
  unit_price: string;
  unit_cost: string;
  weight_g: string;
  print_hours: string;
};

type Order = {
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
  items: Array<{ id: string } & OrderLine>;
  total: string;
  total_cost: string;
  profit: string;
};

type SalesReport = {
  period: string;
  start: string;
  end: string;
  orders: number;
  quantity: string;
  revenue: string;
  cost: string;
  profit: string;
  rows: Array<{
    period: string;
    orders: number;
    quantity: string;
    revenue: string;
    cost: string;
    profit: string;
  }>;
};

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
  NEW: "secondary",
  CONFIRMED: "secondary",
  IN_PRODUCTION: "warning",
  READY: "success",
  SHIPPED: "success",
  DELIVERED: "success",
  CANCELLED: "destructive",
};

const NEXT_STATUSES: Record<string, string[]> = {
  NEW: ["CONFIRMED", "CANCELLED"],
  CONFIRMED: ["IN_PRODUCTION", "CANCELLED"],
  IN_PRODUCTION: ["READY", "CANCELLED"],
  READY: ["SHIPPED", "CANCELLED"],
  SHIPPED: ["DELIVERED"],
  DELIVERED: [],
  CANCELLED: [],
};

const emptyLine = (): OrderLine => ({
  product_name: "",
  variant: "plain",
  quantity: "1",
  unit_price: "0",
  unit_cost: "0",
  weight_g: "",
  print_hours: "",
});

function errText(error: unknown): string {
  return error instanceof Error ? error.message : "خطای نامشخص";
}

export function OrdersPage(): React.JSX.Element {
  const { calendar, ready: calendarReady } = useCalendar();
  const [fromInvalid, setFromInvalid] = React.useState(false);
  const [toInvalid, setToInvalid] = React.useState(false);
  const pricingQuery = usePricingSettings();
  const queryClient = useQueryClient();
  const [page, setPage] = React.useState(0);
  const [statusFilter, setStatusFilter] = React.useState("");
  const [channelFilter, setChannelFilter] = React.useState("");
  const [search, setSearch] = React.useState("");
  const [dateFrom, setDateFrom] = React.useState("");
  const [dateTo, setDateTo] = React.useState("");
  const [period, setPeriod] = React.useState<"daily" | "weekly" | "monthly" | "annual">("monthly");
  const [message, setMessage] = React.useState<string | null>(null);
  const [form, setForm] = React.useState({
    order_date: tehranToday(),
    customer_name: "",
    customer_phone: "",
    customer_address: "",
    channel: "marketplace" as "direct" | "marketplace",
    notes: "",
    items: [emptyLine()],
  });

  const filtersReady =
    calendarReady && !fromInvalid && !toInvalid && !(dateFrom && dateTo && dateFrom > dateTo);
  const ordersQuery = useQuery({
    enabled: filtersReady,
    queryKey: ["orders", statusFilter, channelFilter, search, dateFrom, dateTo, page],
    queryFn: async () => {
      const res = await api.GET("/api/v1/orders", {
        params: {
          query: {
            limit: OPERATION_PAGE_SIZE + 1,
            offset: page * OPERATION_PAGE_SIZE,
            ...(statusFilter ? { status: statusFilter } : {}),
            ...(channelFilter ? { channel: channelFilter } : {}),
            ...(search ? { search } : {}),
            ...(dateFrom ? { date_from: dateFrom } : {}),
            ...(dateTo ? { date_to: dateTo } : {}),
          },
        },
      });
      if (res.error) throw await parseError(res.response);
      return res.data as unknown as Order[];
    },
  });

  const reportQuery = useQuery({
    queryKey: ["orders", "report", period],
    queryFn: async () => {
      const res = await api.GET("/api/v1/orders/reports/sales", {
        params: { query: { period } },
      });
      if (res.error) throw await parseError(res.response);
      return res.data as unknown as SalesReport;
    },
  });

  const invalidate = (): void => {
    void queryClient.invalidateQueries({ queryKey: ["orders"] });
    void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
  };

  const createOrder = useMutation({
    mutationFn: async () => {
      if (!calendarReady || !validIso(form.order_date))
        throw new Error("تاریخ معتبر و تنظیم تقویم باید دریافت شوند.");
      const res = await api.POST("/api/v1/orders", {
        body: {
          order_date: form.order_date,
          status: "NEW" as const,
          customer_name: form.customer_name,
          customer_phone: form.customer_phone || null,
          customer_address: form.customer_address || null,
          channel: form.channel,
          notes: form.notes || null,
          items: form.items.map((line) => ({
            product_name: line.product_name,
            variant: line.variant,
            quantity: parseNum(line.quantity || "1").toString(),
            unit_price: parseNum(line.unit_price || "0").toString(),
            unit_cost: parseNum(line.unit_cost || "0").toString(),
            weight_g: parseNum(line.weight_g || "0").toString(),
            print_hours: parseNum(line.print_hours || "0").toString(),
          })),
        },
      });
      if (res.error) throw await parseError(res.response);
      return res.data;
    },
    onSuccess: () => {
      setPage(0);
      setForm((f) => ({
        ...f,
        customer_name: "",
        customer_phone: "",
        customer_address: "",
        items: [emptyLine()],
      }));
      setMessage("سفارش ثبت شد ✓");
      invalidate();
    },
    onError: (e) => setMessage(errText(e)),
  });

  const setStatus = useMutation({
    mutationFn: async (payload: { order: Order; status: string }) => {
      const res = await api.PATCH("/api/v1/orders/{order_id}", {
        params: { path: { order_id: payload.order.id } },
        body: {
          version_id: payload.order.version_id,
          status: payload.status as
            "NEW" | "CONFIRMED" | "IN_PRODUCTION" | "READY" | "SHIPPED" | "DELIVERED" | "CANCELLED",
        },
      });
      if (res.error) throw await parseError(res.response);
      return res.data;
    },
    onSuccess: () => {
      setMessage("وضعیت سفارش به‌روز شد ✓");
      invalidate();
    },
    onError: (e) => setMessage(errText(e)),
  });

  const updateLine = (index: number, patch: Partial<OrderLine>): void =>
    setForm((f) => ({
      ...f,
      items: f.items.map((line, i) => (i === index ? { ...line, ...patch } : line)),
    }));

  /** Fill unit price/cost from the sheet-exact pricing engine. */
  const priceLine = (index: number): void => {
    if (!pricingQuery.data || pricingQuery.isError || pricingQuery.isPending) {
      setMessage("ثابت‌های قیمت‌گذاری در دسترس نیستند؛ دوباره تلاش کنید.");
      void pricingQuery.refetch();
      return;
    }
    const line = form.items[index];
    try {
      const inputs: PriceInputs = {
        weightG: line.weight_g || "0",
        printHours: line.print_hours || "0",
        quantity: parseNum(line.quantity || "1").toString(),
        variant: line.variant,
        channel: form.channel,
      };
      const result = computePrice(inputs, pricingConstants(pricingQuery.data));
      updateLine(index, {
        unit_price: result.unitFinalPrice.toFixed(4),
        unit_cost: result.unitProductionCost.toFixed(4),
      });
      setMessage("قیمت از ماشین‌حساب قیمت‌گذاری محاسبه شد ✓");
    } catch (error) {
      setMessage(errText(error));
    }
  };

  const formTotal = React.useMemo(() => {
    try {
      return form.items.reduce(
        (sum, line) => sum.plus(parseNum(line.quantity).times(parseNum(line.unit_price))),
        parseNum("0"),
      );
    } catch {
      return parseNum("0");
    }
  }, [form.items]);

  return (
    <div className="space-y-6" dir="rtl">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-bold">سفارش‌ها</h1>
        <Badge variant="outline">
          فروش دوره:{" "}
          {reportQuery.isSuccess ? (
            <Money value={reportQuery.data.revenue} currency="TOMAN" />
          ) : (
            "نامشخص"
          )}
        </Badge>
      </div>

      {message && (
        <p className="rounded-md bg-muted px-3 py-2 text-sm" data-testid="orders-message">
          {message}
        </p>
      )}

      <div className="grid gap-4 xl:grid-cols-5">
        <Card className="xl:col-span-3">
          <CardHeader>
            <CardTitle className="text-base">فهرست سفارش‌ها</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex flex-wrap items-end gap-2">
              <div className="w-40">
                <Label className="text-xs">جستجو</Label>
                <Input
                  data-testid="orders-search"
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
                  onChange={(e) => {
                    setStatusFilter(e.target.value);
                    setPage(0);
                  }}
                >
                  <option value="">همه</option>
                  {Object.entries(STATUS_LABEL).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="w-28">
                <Label className="text-xs">کانال</Label>
                <select
                  className="flex h-9 w-full rounded-md border border-input bg-background px-2 text-sm text-foreground"
                  value={channelFilter}
                  onChange={(e) => {
                    setChannelFilter(e.target.value);
                    setPage(0);
                  }}
                >
                  <option value="">همه</option>
                  <option value="direct">مستقیم</option>
                  <option value="marketplace">بازارگاه</option>
                </select>
              </div>
              <div className="w-36">
                <CalendarInput
                  id="orders-from"
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
                  id="orders-to"
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

            <QueryNotice query={ordersQuery} />
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
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
                  {(filtersReady && ordersQuery.isSuccess
                    ? ordersQuery.data.slice(0, OPERATION_PAGE_SIZE)
                    : []
                  ).map((order) => (
                    <tr key={order.id} className="border-b" data-testid={`order-${order.id}`}>
                      <td className="num py-2">{faNumber(String(order.order_number))}</td>
                      <td className="py-2">
                        {faDate(order.order_date, calendar)}
                        <div className="text-xs text-muted-foreground">
                          {order.channel === "marketplace" ? "بازارگاه" : "مستقیم"}
                        </div>
                      </td>
                      <td className="py-2">
                        {order.customer_name}
                        {order.customer_phone && (
                          <div className="num text-xs text-muted-foreground">
                            {faNumber(order.customer_phone)}
                          </div>
                        )}
                      </td>
                      <td className="py-2">
                        {order.items.map((line, i) => (
                          <div key={i} className="text-xs">
                            {line.product_name}
                            {line.variant === "chain" ? " (زنجیر)" : ""} ×{" "}
                            <span className="num">{faNumber(line.quantity)}</span>
                          </div>
                        ))}
                      </td>
                      <td className="py-2">
                        <Money value={order.total} currency="TOMAN" />
                      </td>
                      <td className="py-2">
                        <Money value={order.profit} currency="TOMAN" />
                      </td>
                      <td className="py-2">
                        <Badge variant={STATUS_VARIANT[order.status]}>
                          {STATUS_LABEL[order.status]}
                        </Badge>
                      </td>
                      <td className="py-2">
                        <div className="flex flex-wrap gap-1">
                          {(NEXT_STATUSES[order.status] ?? []).map((next) => (
                            <Button
                              key={next}
                              size="sm"
                              variant={next === "CANCELLED" ? "ghost" : "outline"}
                              data-testid={`order-${order.id}-${next}`}
                              disabled={setStatus.isPending}
                              onClick={() => setStatus.mutate({ order, status: next })}
                            >
                              {STATUS_LABEL[next]}
                            </Button>
                          ))}
                          <a
                            className="inline-flex h-8 items-center rounded-md border border-input px-3 text-xs hover:bg-accent"
                            href={`/api/v1/orders/${order.id}/proforma.pdf`}
                            target="_blank"
                            rel="noreferrer"
                          >
                            پیش‌فاکتور
                          </a>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {filtersReady && ordersQuery.isSuccess && ordersQuery.data.length === 0 && (
                    <tr>
                      <td colSpan={8} className="py-6 text-center text-muted-foreground">
                        سفارشی یافت نشد.
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
                ordersQuery.isSuccess &&
                ordersQuery.data.length > OPERATION_PAGE_SIZE
              }
              busy={ordersQuery.isFetching}
              onChange={setPage}
            />
          </CardContent>
        </Card>

        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">ثبت سفارش</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-2 gap-2">
              <div>
                <CalendarInput
                  id="order-date"
                  label="تاریخ سفارش"
                  required
                  value={form.order_date}
                  onChange={(iso) => setForm((f) => ({ ...f, order_date: iso }))}
                />
              </div>
              <div>
                <Label className="text-xs">کانال فروش</Label>
                <select
                  className="flex h-9 w-full rounded-md border border-input bg-background px-2 text-sm text-foreground"
                  value={form.channel}
                  data-testid="order-channel"
                  onChange={(e) =>
                    setForm((f) => ({ ...f, channel: e.target.value as "direct" | "marketplace" }))
                  }
                >
                  <option value="marketplace">بازارگاه</option>
                  <option value="direct">مستقیم</option>
                </select>
              </div>
            </div>
            <div>
              <Label className="text-xs">نام مشتری</Label>
              <Input
                data-testid="order-customer"
                value={form.customer_name}
                onChange={(e) => setForm((f) => ({ ...f, customer_name: e.target.value }))}
              />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <Label className="text-xs">تلفن</Label>
                <Input
                  className="num"
                  value={form.customer_phone}
                  onChange={(e) => setForm((f) => ({ ...f, customer_phone: e.target.value }))}
                />
              </div>
              <div>
                <Label className="text-xs">آدرس</Label>
                <Input
                  value={form.customer_address}
                  onChange={(e) => setForm((f) => ({ ...f, customer_address: e.target.value }))}
                />
              </div>
            </div>

            <div className="space-y-2 rounded-md border p-2">
              <p className="text-xs font-medium">اقلام سفارش</p>
              {form.items.map((line, index) => (
                <div
                  key={index}
                  className="space-y-1 border-b pb-2 last:border-0"
                  data-testid={`line-${index}`}
                >
                  <div className="grid grid-cols-2 gap-1">
                    <Input
                      className="h-8 text-xs"
                      placeholder="نام محصول"
                      value={line.product_name}
                      onChange={(e) => updateLine(index, { product_name: e.target.value })}
                    />
                    <select
                      className="flex h-8 w-full rounded-md border border-input bg-background px-2 text-xs text-foreground"
                      value={line.variant}
                      onChange={(e) =>
                        updateLine(index, { variant: e.target.value as "plain" | "chain" })
                      }
                    >
                      <option value="plain">ساده</option>
                      <option value="chain">حلقه‌دار</option>
                    </select>
                  </div>
                  <div className="grid grid-cols-4 gap-1">
                    <Input
                      className="num h-8 text-xs"
                      placeholder="تعداد"
                      value={line.quantity}
                      onChange={(e) => updateLine(index, { quantity: e.target.value })}
                    />
                    <Input
                      className="num h-8 text-xs"
                      placeholder="وزن (گرم)"
                      value={line.weight_g}
                      onChange={(e) => updateLine(index, { weight_g: e.target.value })}
                    />
                    <Input
                      className="num h-8 text-xs"
                      placeholder="زمان (ساعت)"
                      value={line.print_hours}
                      onChange={(e) => updateLine(index, { print_hours: e.target.value })}
                    />
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={pricingQuery.isPending}
                      onClick={() => priceLine(index)}
                    >
                      محاسبهٔ قیمت
                    </Button>
                  </div>
                  <div className="grid grid-cols-2 gap-1">
                    <Input
                      className="num h-8 text-xs"
                      placeholder="قیمت واحد"
                      value={line.unit_price}
                      onChange={(e) => updateLine(index, { unit_price: e.target.value })}
                    />
                    <Input
                      className="num h-8 text-xs"
                      placeholder="بهای تمام‌شده واحد"
                      value={line.unit_cost}
                      onChange={(e) => updateLine(index, { unit_cost: e.target.value })}
                    />
                  </div>
                </div>
              ))}
              <div className="flex items-center justify-between">
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setForm((f) => ({ ...f, items: [...f.items, emptyLine()] }))}
                >
                  + افزودن قلم
                </Button>
                <span className="text-sm">
                  جمع: <Money value={formTotal.toFixed(4)} currency="TOMAN" />
                </span>
              </div>
            </div>

            <Button
              className="w-full"
              data-testid="order-submit"
              disabled={
                createOrder.isPending ||
                !form.customer_name.trim() ||
                !calendarReady ||
                !validIso(form.order_date)
              }
              onClick={() => createOrder.mutate()}
            >
              ثبت سفارش
            </Button>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">گزارش فروش</CardTitle>
          <select
            className="h-8 rounded-md border border-input bg-background px-2 text-sm text-foreground"
            value={period}
            data-testid="report-period"
            onChange={(e) => setPeriod(e.target.value as typeof period)}
          >
            <option value="daily">روزانه</option>
            <option value="weekly">هفتگی</option>
            <option value="monthly">ماهانه</option>
            <option value="annual">سالانه</option>
          </select>
        </CardHeader>
        <CardContent>
          <QueryNotice query={reportQuery} />
          {reportQuery.isSuccess && (
            <div className="pb-3 flex flex-wrap gap-3 text-sm">
              <span>
                تعداد سفارش:{" "}
                <span className="num">{faNumber(String(reportQuery.data?.orders ?? 0))}</span>
              </span>
              <span>
                فروش: <Money value={reportQuery.data?.revenue ?? "0"} currency="TOMAN" />
              </span>
              <span>
                بهای تمام‌شده: <Money value={reportQuery.data?.cost ?? "0"} currency="TOMAN" />
              </span>
              <span>
                سود: <Money value={reportQuery.data?.profit ?? "0"} currency="TOMAN" />
              </span>
            </div>
          )}
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-muted-foreground">
                <th className="py-2 text-start font-medium">دوره</th>
                <th className="py-2 text-start font-medium">سفارش</th>
                <th className="py-2 text-start font-medium">تعداد</th>
                <th className="py-2 text-start font-medium">فروش</th>
                <th className="py-2 text-start font-medium">سود</th>
              </tr>
            </thead>
            <tbody>
              {(reportQuery.isSuccess ? reportQuery.data.rows : []).map((row) => (
                <tr key={row.period} className="border-b" data-testid={`report-${row.period}`}>
                  <td className="num py-2">{row.period}</td>
                  <td className="num py-2">{faNumber(String(row.orders))}</td>
                  <td className="num py-2">{faNumber(row.quantity)}</td>
                  <td className="py-2">
                    <Money value={row.revenue} currency="TOMAN" />
                  </td>
                  <td className="py-2">
                    <Money value={row.profit} currency="TOMAN" />
                  </td>
                </tr>
              ))}
              {reportQuery.isSuccess && reportQuery.data.rows.length === 0 && (
                <tr>
                  <td colSpan={5} className="py-6 text-center text-muted-foreground">
                    در این بازه فروشی ثبت نشده است.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}
