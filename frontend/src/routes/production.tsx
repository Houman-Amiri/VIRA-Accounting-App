/**
 * تولید — production jobs (MASTER_PROMPT §3.3).
 *
 * A job is planned from an order line (or manually), linked to a filament spool
 * in the warehouse; finishing it consumes the filament and adds the produced
 * models to stock. Unit cost/price come from the sheet-exact pricing engine.
 */
import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, parseError } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Money } from "@/components/money";
import { computePrice, parseNum, type PriceInputs } from "@/lib/priceCalc";
import { pricingConstants, usePricingSettings } from "@/lib/pricing-settings";
import { QueryNotice } from "@/components/query-notice";
import { collectOperationPages } from "@/lib/operation-pages";
import { OperationPagination, OPERATION_PAGE_SIZE } from "@/components/operation-pagination";
import { toDecimal } from "@/lib/money";
import { faNumber } from "@/lib/fa";

type Job = {
  id: string;
  job_number: number;
  order_id: string | null;
  order_item_id: string | null;
  order_number: number | null;
  product_name: string;
  variant: "plain" | "chain";
  channel: "direct" | "marketplace";
  quantity: string;
  status: "PLANNED" | "IN_PROGRESS" | "DONE" | "CANCELLED";
  filament_item_id: string | null;
  filament_item_name: string | null;
  product_item_id: string | null;
  product_item_name: string | null;
  filament_grams: string;
  print_hours: string;
  unit_cost: string;
  unit_price: string;
  note: string | null;
  started_at: string | null;
  finished_at: string | null;
  version_id: number;
};

type Item = {
  id: string;
  name: string;
  kind: string;
  unit: string;
  quantity: string;
};

type OrderOption = {
  id: string;
  order_number: number;
  customer_name: string;
  channel: "direct" | "marketplace";
  status: string;
  items: Array<{
    id: string;
    product_name: string;
    variant: "plain" | "chain";
    quantity: string;
    weight_g: string;
    print_hours: string;
    unit_cost: string;
    unit_price: string;
    inventory_item_id?: string | null;
  }>;
};

const STATUS_LABEL: Record<string, string> = {
  PLANNED: "برنامه‌ریزی‌شده",
  IN_PROGRESS: "در حال چاپ",
  DONE: "تمام‌شده",
  CANCELLED: "لغو‌شده",
};

const STATUS_VARIANT: Record<string, "secondary" | "warning" | "success" | "destructive"> = {
  PLANNED: "secondary",
  IN_PROGRESS: "warning",
  DONE: "success",
  CANCELLED: "destructive",
};

function errText(error: unknown): string {
  return error instanceof Error ? error.message : "خطای نامشخص";
}

export function ProductionPage(): React.JSX.Element {
  const pricingQuery = usePricingSettings();
  const queryClient = useQueryClient();
  const [page, setPage] = React.useState(0);
  const [editingJob, setEditingJob] = React.useState<Job | null>(null);
  const [statusFilter, setStatusFilter] = React.useState("");
  const [message, setMessage] = React.useState<string | null>(null);
  const [form, setForm] = React.useState({
    order_id: "",
    order_item_id: "",
    product_name: "",
    variant: "plain" as "plain" | "chain",
    channel: "marketplace" as "direct" | "marketplace",
    quantity: "1",
    filament_item_id: "",
    product_item_id: "",
    filament_grams: "",
    print_hours: "",
  });

  const jobsQuery = useQuery({
    queryKey: ["production", "jobs", statusFilter, page],
    queryFn: async () => {
      const res = await api.GET("/api/v1/production/jobs", {
        params: {
          query: {
            ...(statusFilter ? { status: statusFilter } : {}),
            limit: OPERATION_PAGE_SIZE + 1,
            offset: page * OPERATION_PAGE_SIZE,
          },
        },
      });
      if (res.error) throw await parseError(res.response);
      return res.data as unknown as Job[];
    },
  });

  const summaryQuery = useQuery({
    queryKey: ["production", "summary"],
    queryFn: async () => {
      const res = await api.GET("/api/v1/production/summary");
      if (res.error) throw await parseError(res.response);
      return res.data as unknown as {
        planned: number;
        in_progress: number;
        done: number;
        filament_grams_planned: string;
      };
    },
  });

  const itemsQuery = useQuery({
    queryKey: ["warehouse", "items", "for-production"],
    queryFn: async () => {
      const res = await api.GET("/api/v1/warehouse/summary");
      if (res.error) throw await parseError(res.response);
      return res.data!.items as Item[];
    },
  });

  const ordersQuery = useQuery({
    queryKey: ["orders", "open"],
    queryFn: async () => {
      const rows = await collectOperationPages(async (offset, limit) => {
        const res = await api.GET("/api/v1/orders", { params: { query: { offset, limit } } });
        if (res.error) throw await parseError(res.response);
        return res.data!;
      });
      return (rows as OrderOption[]).filter(
        (o) => !["CANCELLED", "SHIPPED", "DELIVERED"].includes(o.status),
      );
    },
  });

  const invalidate = (): void => {
    void queryClient.invalidateQueries({ queryKey: ["production"] });
    void queryClient.invalidateQueries({ queryKey: ["warehouse"] });
    void queryClient.invalidateQueries({ queryKey: ["orders"] });
    void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
  };

  const createJob = useMutation({
    mutationFn: async () => {
      const order = ordersQuery.data?.find((o) => o.id === form.order_id);
      const line = order?.items.find((line) => line.id === form.order_item_id);
      if (form.order_id && (!line || ordersQuery.isError))
        throw new Error("ردیف سفارش معتبر در دسترس نیست.");
      const inputs: PriceInputs = {
        weightG: form.filament_grams || "0",
        printHours: form.print_hours || "0",
        quantity: form.quantity || "1",
        variant: form.variant,
        channel: form.channel,
      };
      let unitCost: string;
      let unitPrice: string;
      if (line) {
        unitCost = line.unit_cost;
        unitPrice = line.unit_price;
      } else {
        if (!pricingQuery.data || pricingQuery.isError || pricingQuery.isPending)
          throw new Error("ثابت‌های قیمت‌گذاری در دسترس نیستند؛ دوباره تلاش کنید.");
        const priced = computePrice(inputs, pricingConstants(pricingQuery.data));
        unitCost = priced.unitProductionCost.toFixed(4);
        unitPrice = priced.unitFinalPrice.toFixed(4);
      }
      const res = await api.POST("/api/v1/production/jobs", {
        body: {
          product_name: form.product_name,
          quantity: parseNum(form.quantity || "1").toString(),
          variant: form.variant,
          channel: form.channel,
          order_id: form.order_id || null,
          order_item_id: form.order_item_id || null,
          filament_item_id: form.filament_item_id || null,
          product_item_id: form.product_item_id || null,
          filament_grams: parseNum(form.filament_grams || "0").toString(),
          print_hours: parseNum(form.print_hours || "0").toString(),
          unit_cost: unitCost,
          unit_price: unitPrice,
        },
      });
      if (res.error) throw await parseError(res.response);
      return res.data;
    },
    onSuccess: () => {
      setPage(0);
      setStatusFilter("");
      setMessage("کار تولید ثبت شد ✓");
      setForm((f) => ({
        ...f,
        order_id: "",
        order_item_id: "",
        product_name: "",
        quantity: "1",
        filament_grams: "",
        print_hours: "",
      }));
      invalidate();
    },
    onError: (e) => setMessage(errText(e)),
  });

  const act = useMutation({
    mutationFn: async (payload: { job: Job; action: "start" | "finish" | "cancel" }) => {
      const res = await api.POST(`/api/v1/production/jobs/{job_id}/${payload.action}`, {
        params: { path: { job_id: payload.job.id } },
      });
      if (res.error) throw await parseError(res.response);
      return res.data;
    },
    onSuccess: () => {
      setMessage("وضعیت کار تولید به‌روز شد ✓");
      invalidate();
    },
    onError: (e) => setMessage(errText(e)),
  });

  const saveMapping = useMutation({
    mutationFn: async () => {
      if (!editingJob) throw new Error("کاری انتخاب نشده است");
      const res = await api.PATCH("/api/v1/production/jobs/{job_id}", {
        params: { path: { job_id: editingJob.id } },
        body: {
          version_id: editingJob.version_id,
          order_item_id: editingJob.order_item_id,
          filament_item_id: editingJob.filament_item_id,
          product_item_id: editingJob.product_item_id,
          filament_grams: parseNum(editingJob.filament_grams).toString(),
        },
      });
      if (res.error) throw await parseError(res.response);
    },
    onSuccess: () => {
      setEditingJob(null);
      setMessage("اتصال انبار ذخیره شد ✓");
      invalidate();
    },
    onError: (e) => setMessage(errText(e)),
  });

  const filaments = (itemsQuery.data ?? []).filter((i) => i.kind === "FILAMENT" && i.unit === "G");
  const products = (itemsQuery.data ?? []).filter((i) => i.kind === "PRODUCT" && i.unit === "PCS");

  const pickLine = (orderId: string, lineId?: string): void => {
    const order = ordersQuery.data?.find((o) => o.id === orderId);
    const line = lineId ? order?.items.find((l) => l.id === lineId) : order?.items[0];
    setForm((f) => ({
      ...f,
      order_id: orderId,
      order_item_id: line?.id ?? "",
      product_name: line?.product_name ?? f.product_name,
      variant: line?.variant ?? f.variant,
      channel: order?.channel ?? f.channel,
      quantity: line?.quantity ?? f.quantity,
      filament_grams: line?.weight_g ?? f.filament_grams,
      print_hours: line?.print_hours ?? f.print_hours,
      product_item_id: line?.inventory_item_id ?? "",
    }));
  };
  const selectedOrder = ordersQuery.data?.find((o) => o.id === form.order_id);
  const selectedLine = selectedOrder?.items.find((l) => l.id === form.order_item_id);

  return (
    <div className="space-y-6" dir="rtl">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-bold">تولید</h1>
        <div className="flex flex-wrap gap-2 text-sm">
          <QueryNotice query={summaryQuery} />
          {summaryQuery.isSuccess && (
            <>
              <Badge variant="secondary">
                برنامه‌ریزی‌شده: {faNumber(String(summaryQuery.data?.planned ?? 0))}
              </Badge>
              <Badge variant="warning">
                در حال چاپ: {faNumber(String(summaryQuery.data?.in_progress ?? 0))}
              </Badge>
              <Badge variant="success">
                تمام‌شده: {faNumber(String(summaryQuery.data?.done ?? 0))}
              </Badge>
              <Badge variant="outline">
                فیلامنت موردنیاز: {faNumber(summaryQuery.data?.filament_grams_planned ?? "0")} گرم
              </Badge>
            </>
          )}
        </div>
      </div>

      {message && (
        <p className="rounded-md bg-muted px-3 py-2 text-sm" data-testid="production-message">
          {message}
        </p>
      )}

      <div className="grid gap-4 xl:grid-cols-5">
        <Card className="xl:col-span-3">
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">کارهای تولید</CardTitle>
            <select
              className="h-8 rounded-md border border-input bg-background px-2 text-sm text-foreground"
              value={statusFilter}
              data-testid="production-filter"
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
          </CardHeader>
          <CardContent>
            <QueryNotice query={jobsQuery} />
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-muted-foreground">
                    <th className="py-2 text-start font-medium">#</th>
                    <th className="py-2 text-start font-medium">محصول</th>
                    <th className="py-2 text-start font-medium">سفارش</th>
                    <th className="py-2 text-start font-medium">تعداد</th>
                    <th className="py-2 text-start font-medium">فیلامنت</th>
                    <th className="py-2 text-start font-medium">قیمت واحد</th>
                    <th className="py-2 text-start font-medium">وضعیت</th>
                    <th className="py-2 text-start font-medium">اقدام</th>
                  </tr>
                </thead>
                <tbody>
                  {(jobsQuery.isSuccess ? jobsQuery.data.slice(0, OPERATION_PAGE_SIZE) : []).map(
                    (job) => (
                      <tr key={job.id} className="border-b" data-testid={`job-${job.id}`}>
                        <td className="num py-2">{faNumber(String(job.job_number))}</td>
                        <td className="py-2">
                          {job.product_name}
                          {job.variant === "chain" && (
                            <Badge variant="secondary" className="ms-1">
                              زنجیر
                            </Badge>
                          )}
                        </td>
                        <td className="num py-2">
                          {job.order_number ? faNumber(String(job.order_number)) : "—"}
                        </td>
                        <td className="num py-2">{faNumber(job.quantity)}</td>
                        <td className="py-2 text-xs">
                          {job.filament_item_name ?? "—"}
                          {toDecimal(job.filament_grams).gt(0) && (
                            <div className="num text-muted-foreground">
                              {faNumber(job.filament_grams)} گرم × {faNumber(job.quantity)} ={" "}
                              {faNumber(
                                toDecimal(job.filament_grams).times(job.quantity).toString(),
                              )}{" "}
                              گرم
                            </div>
                          )}
                        </td>
                        <td className="py-2">
                          <Money value={job.unit_price} currency="TOMAN" />
                        </td>
                        <td className="py-2">
                          <Badge variant={STATUS_VARIANT[job.status]}>
                            {STATUS_LABEL[job.status]}
                          </Badge>
                        </td>
                        <td className="py-2">
                          <div className="flex flex-wrap gap-1">
                            {job.status === "PLANNED" && (
                              <Button
                                size="sm"
                                variant="outline"
                                data-testid={`job-${job.id}-start`}
                                disabled={act.isPending}
                                onClick={() => act.mutate({ job, action: "start" })}
                              >
                                شروع چاپ
                              </Button>
                            )}
                            {(job.status === "PLANNED" || job.status === "IN_PROGRESS") && (
                              <>
                                <Button
                                  size="sm"
                                  data-testid={`job-${job.id}-finish`}
                                  disabled={
                                    act.isPending ||
                                    !job.filament_item_id ||
                                    !job.product_item_id ||
                                    !toDecimal(job.filament_grams).gt(0)
                                  }
                                  onClick={() => act.mutate({ job, action: "finish" })}
                                >
                                  پایان (کسر فیلامنت)
                                </Button>
                                <Button
                                  size="sm"
                                  variant="outline"
                                  data-testid={`job-${job.id}-configure`}
                                  onClick={() => setEditingJob({ ...job })}
                                >
                                  اتصال انبار
                                </Button>
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  disabled={act.isPending}
                                  onClick={() => act.mutate({ job, action: "cancel" })}
                                >
                                  لغو
                                </Button>
                              </>
                            )}
                          </div>
                        </td>
                      </tr>
                    ),
                  )}
                  {jobsQuery.isSuccess && jobsQuery.data.length === 0 && (
                    <tr>
                      <td colSpan={8} className="py-6 text-center text-muted-foreground">
                        کار تولیدی ثبت نشده است.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            <OperationPagination
              page={page}
              next={jobsQuery.isSuccess && jobsQuery.data.length > OPERATION_PAGE_SIZE}
              busy={jobsQuery.isFetching}
              onChange={setPage}
            />
            {editingJob && (
              <div className="mt-3 space-y-2 rounded border p-3" data-testid="job-stock-editor">
                <p className="text-sm font-medium">اتصال انبار — {editingJob.product_name}</p>
                <QueryNotice query={itemsQuery} />
                {editingJob.order_id && (
                  <select
                    aria-label="ردیف سفارش برای اصلاح اتصال"
                    value={editingJob.order_item_id ?? ""}
                    onChange={(e) =>
                      setEditingJob({ ...editingJob, order_item_id: e.target.value || null })
                    }
                  >
                    <option value="">ردیف سفارش را انتخاب کنید</option>
                    {ordersQuery.data
                      ?.find((o) => o.id === editingJob.order_id)
                      ?.items.map((l, i) => (
                        <option key={l.id} value={l.id}>
                          {faNumber(String(i + 1))} — {l.product_name}
                        </option>
                      ))}
                  </select>
                )}
                <select
                  aria-label="فیلامنت کار تولید"
                  data-testid="job-mapping-filament"
                  value={editingJob.filament_item_id ?? ""}
                  onChange={(e) =>
                    setEditingJob({ ...editingJob, filament_item_id: e.target.value || null })
                  }
                >
                  <option value="">فیلامنت را انتخاب کنید</option>
                  {filaments.map((i) => (
                    <option key={i.id} value={i.id}>
                      {i.name}
                    </option>
                  ))}
                </select>
                <select
                  aria-label="محصول مقصد کار تولید"
                  data-testid="job-mapping-product"
                  value={editingJob.product_item_id ?? ""}
                  onChange={(e) =>
                    setEditingJob({ ...editingJob, product_item_id: e.target.value || null })
                  }
                >
                  <option value="">محصول مقصد را انتخاب کنید</option>
                  {products.map((i) => (
                    <option key={i.id} value={i.id}>
                      {i.name}
                    </option>
                  ))}
                </select>
                <Input
                  aria-label="گرم فیلامنت هر عدد"
                  data-testid="job-mapping-grams"
                  value={editingJob.filament_grams}
                  onChange={(e) => setEditingJob({ ...editingJob, filament_grams: e.target.value })}
                />
                <Button
                  data-testid="job-mapping-save"
                  disabled={saveMapping.isPending || !itemsQuery.isSuccess}
                  onClick={() => saveMapping.mutate()}
                >
                  ذخیرهٔ اتصال
                </Button>
                <Button variant="ghost" onClick={() => setEditingJob(null)}>
                  انصراف
                </Button>
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">ثبت کار تولید</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div>
              <Label className="text-xs">از روی سفارش</Label>
              <select
                className="flex h-9 w-full rounded-md border border-input bg-background px-2 text-sm text-foreground"
                value={form.order_id}
                data-testid="job-order"
                onChange={(e) => pickLine(e.target.value)}
              >
                <option value="">— بدون سفارش —</option>
                {(ordersQuery.data ?? []).map((o) => (
                  <option key={o.id} value={o.id}>
                    #{o.order_number} — {o.customer_name}
                  </option>
                ))}
              </select>
            </div>
            <QueryNotice query={ordersQuery} />
            <QueryNotice query={itemsQuery} />
            {selectedOrder && (
              <div>
                <Label className="text-xs">ردیف سفارش</Label>
                <select
                  className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm text-foreground"
                  data-testid="job-order-line"
                  value={form.order_item_id}
                  onChange={(e) => pickLine(form.order_id, e.target.value)}
                >
                  {selectedOrder.items.map((l, i) => (
                    <option key={l.id} value={l.id}>
                      {faNumber(String(i + 1))} — {l.product_name} × {faNumber(l.quantity)}
                    </option>
                  ))}
                </select>
              </div>
            )}
            <div>
              <Label className="text-xs">نام محصول</Label>
              <Input
                data-testid="job-product"
                value={form.product_name}
                onChange={(e) => setForm((f) => ({ ...f, product_name: e.target.value }))}
              />
            </div>
            <div className="grid grid-cols-3 gap-2">
              <div>
                <Label className="text-xs">تعداد</Label>
                <Input
                  className="num"
                  data-testid="job-quantity"
                  value={form.quantity}
                  onChange={(e) => setForm((f) => ({ ...f, quantity: e.target.value }))}
                />
              </div>
              <div>
                <Label className="text-xs">وزن هر عدد (گرم)</Label>
                <Input
                  className="num"
                  data-testid="job-grams"
                  value={form.filament_grams}
                  onChange={(e) => setForm((f) => ({ ...f, filament_grams: e.target.value }))}
                />
              </div>
              <div>
                <Label className="text-xs">زمان چاپ (ساعت)</Label>
                <Input
                  className="num"
                  value={form.print_hours}
                  onChange={(e) => setForm((f) => ({ ...f, print_hours: e.target.value }))}
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <Label className="text-xs">نوع</Label>
                <select
                  className="flex h-9 w-full rounded-md border border-input bg-background px-2 text-sm text-foreground"
                  value={form.variant}
                  disabled={!!form.order_id}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, variant: e.target.value as "plain" | "chain" }))
                  }
                >
                  <option value="plain">ساده</option>
                  <option value="chain">حلقه‌دار</option>
                </select>
              </div>
              <div>
                <Label className="text-xs">کانال</Label>
                <select
                  className="flex h-9 w-full rounded-md border border-input bg-background px-2 text-sm text-foreground"
                  value={form.channel}
                  disabled={!!form.order_id}
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
              <Label className="text-xs">فیلامنت مصرفی (از انبار)</Label>
              <select
                className="flex h-9 w-full rounded-md border border-input bg-background px-2 text-sm text-foreground"
                value={form.filament_item_id}
                data-testid="job-filament"
                onChange={(e) => setForm((f) => ({ ...f, filament_item_id: e.target.value }))}
              >
                <option value="">—</option>
                {filaments.map((i) => (
                  <option key={i.id} value={i.id}>
                    {i.name} ({faNumber(i.quantity)} گرم موجود)
                  </option>
                ))}
              </select>
            </div>
            <div>
              <Label className="text-xs">افزودن به محصولات انبار</Label>
              <select
                className="flex h-9 w-full rounded-md border border-input bg-background px-2 text-sm text-foreground"
                value={form.product_item_id}
                data-testid="job-product-item"
                onChange={(e) => setForm((f) => ({ ...f, product_item_id: e.target.value }))}
              >
                <option value="">—</option>
                {products.map((i) => (
                  <option key={i.id} value={i.id}>
                    {i.name} ({faNumber(i.quantity)} عدد)
                  </option>
                ))}
              </select>
            </div>
            {selectedLine ? (
              <p className="text-xs text-muted-foreground" data-testid="job-price-snapshot">
                قیمت و بهای واحد از ردیف ذخیره‌شدهٔ سفارش؛ بدون محاسبهٔ مجدد با ثابت‌های تازه:{" "}
                <Money value={selectedLine.unit_price} currency="TOMAN" /> /{" "}
                <Money value={selectedLine.unit_cost} currency="TOMAN" />
              </p>
            ) : (
              <p className="text-xs text-muted-foreground">
                کار مستقل با ثابت‌های فعلی قیمت‌گذاری می‌شود. برای پایان تولید، فیلامنت، وزن مثبت و
                محصول مقصد لازم است.
              </p>
            )}
            <Button
              className="w-full"
              data-testid="job-submit"
              disabled={createJob.isPending || !form.product_name.trim()}
              onClick={() => createJob.mutate()}
            >
              ثبت کار تولید
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
