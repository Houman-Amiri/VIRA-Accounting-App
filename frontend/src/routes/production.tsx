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
  filaments: Array<{
    id: string;
    filament_item_id: string | null;
    filament_item_name: string | null;
    grams_per_unit: string;
    unit_cost: string;
    grams_total: string;
  }>;
  filament_ready: boolean;
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

type SpoolRow = { item_id: string; grams: string };

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
    product_item_id: "",
    print_hours: "",
    // item 6: a printed model may need several spools, each with its own grams
    filaments: [{ item_id: "", grams: "" }] as SpoolRow[],
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
      const spools = form.filaments
        .filter((row) => row.item_id && row.grams.trim() !== "")
        .map((row) => ({
          filament_item_id: row.item_id,
          grams_per_unit: parseNum(row.grams).toString(),
        }));
      if (new Set(spools.map((row) => row.filament_item_id)).size !== spools.length)
        throw new Error("هر فیلامنت فقط یک بار در یک کار تولید قابل انتخاب است.");
      const totalGrams = spools.reduce(
        (sum, row) => sum.plus(toDecimal(row.grams_per_unit)),
        toDecimal("0"),
      );
      const inputs: PriceInputs = {
        weightG: totalGrams.toString(),
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
          product_item_id: form.product_item_id || null,
          filaments: spools,
          filament_grams: totalGrams.toString(),
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
        print_hours: "",
        filaments: [{ item_id: "", grams: "" }],
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
          product_item_id: editingJob.product_item_id,
          filaments: editingJob.filaments
            .filter((row) => {
              if (!row.filament_item_id) return false;
              try {
                return parseNum(row.grams_per_unit).gt(0);
              } catch {
                throw new Error(`گرم فیلامنت نامعتبر است: ${row.grams_per_unit}`);
              }
            })
            .map((row) => ({
              filament_item_id: row.filament_item_id!,
              grams_per_unit: parseNum(row.grams_per_unit).toString(),
              unit_cost: parseNum(row.unit_cost).toString(),
            })),
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
      product_item_id: line?.inventory_item_id ?? "",
    }));
  };
  const totalGramsPerUnit = form.filaments.reduce((sum, row) => {
    try {
      return row.grams.trim() ? sum.plus(toDecimal(row.grams)) : sum;
    } catch {
      return sum;
    }
  }, toDecimal("0"));
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
                        <td className="py-2 text-xs" data-testid={`job-${job.id}-spools`}>
                          {job.filaments.length === 0 && (job.filament_item_name ?? "—")}
                          {job.filaments.map((row) => (
                            <div key={row.id} className="num text-muted-foreground">
                              {row.filament_item_name ?? "فیلامنت حذف‌شده"}:{" "}
                              {faNumber(row.grams_per_unit)} گرم × {faNumber(job.quantity)} ={" "}
                              {faNumber(row.grams_total)} گرم
                            </div>
                          ))}
                          {!job.filament_ready && (
                            <div className="text-[11px] text-amber-700 dark:text-amber-400">
                              فیلامنت‌ها انتخاب نشده‌اند؛ پایان تولید ممکن نیست.
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
                                    act.isPending || !job.filament_ready || !job.product_item_id
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
                {editingJob.filaments.map((row, index) => (
                  <div key={row.id} className="grid grid-cols-[1fr_6rem_auto] gap-1">
                    <select
                      aria-label={`فیلامنت ${faNumber(String(index + 1))} کار تولید`}
                      data-testid={`job-mapping-filament-${index}`}
                      value={row.filament_item_id ?? ""}
                      onChange={(e) =>
                        setEditingJob({
                          ...editingJob,
                          filaments: editingJob.filaments.map((r, i) =>
                            i === index ? { ...r, filament_item_id: e.target.value || null } : r,
                          ),
                        })
                      }
                    >
                      <option value="">فیلامنت را انتخاب کنید</option>
                      {filaments.map((i) => (
                        <option key={i.id} value={i.id}>
                          {i.name}
                        </option>
                      ))}
                    </select>
                    <Input
                      className="num"
                      aria-label={`گرم فیلامنت هر عدد ردیف ${faNumber(String(index + 1))}`}
                      data-testid={`job-mapping-grams-${index}`}
                      value={row.grams_per_unit}
                      onChange={(e) =>
                        setEditingJob({
                          ...editingJob,
                          filaments: editingJob.filaments.map((r, i) =>
                            i === index ? { ...r, grams_per_unit: e.target.value } : r,
                          ),
                        })
                      }
                    />
                    <Button
                      size="sm"
                      variant="ghost"
                      aria-label={`حذف فیلامنت ردیف ${faNumber(String(index + 1))}`}
                      data-testid={`job-mapping-remove-${index}`}
                      onClick={() =>
                        setEditingJob({
                          ...editingJob,
                          filaments: editingJob.filaments.filter((_r, i) => i !== index),
                        })
                      }
                    >
                      ×
                    </Button>
                  </div>
                ))}
                <Button
                  size="sm"
                  variant="ghost"
                  data-testid="job-mapping-add"
                  onClick={() =>
                    setEditingJob({
                      ...editingJob,
                      filaments: [
                        ...editingJob.filaments,
                        {
                          id: `new-${editingJob.filaments.length}`,
                          filament_item_id: null,
                          filament_item_name: null,
                          grams_per_unit: "",
                          unit_cost: "0",
                          grams_total: "0",
                        },
                      ],
                    })
                  }
                >
                  + افزودن فیلامنت
                </Button>
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
            <div className="grid grid-cols-2 gap-2">
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
                <Label className="text-xs">زمان چاپ هر عدد (ساعت)</Label>
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
            <div className="space-y-2 rounded-md border p-2" data-testid="job-filaments">
              <div className="flex items-center justify-between">
                <Label className="text-xs">فیلامنت‌های مصرفی (از انبار)</Label>
                <span className="num text-xs text-muted-foreground">
                  جمع هر عدد: {faNumber(totalGramsPerUnit.toString())} گرم
                </span>
              </div>
              {form.filaments.map((row, index) => {
                const item = filaments.find((f) => f.id === row.item_id);
                const needed = (() => {
                  try {
                    return toDecimal(row.grams || "0").times(toDecimal(form.quantity || "1"));
                  } catch {
                    return toDecimal("0");
                  }
                })();
                const short = item ? needed.gt(toDecimal(item.quantity)) : false;
                return (
                  <div key={index} className="space-y-1" data-testid={`job-spool-${index}`}>
                    <div className="grid grid-cols-[1fr_6rem_auto] gap-1">
                      <select
                        aria-label={`فیلامنت ردیف ${faNumber(String(index + 1))}`}
                        data-testid={`job-spool-${index}-item`}
                        className="flex h-8 w-full rounded-md border border-input bg-background px-2 text-xs text-foreground"
                        value={row.item_id}
                        onChange={(e) =>
                          setForm((f) => ({
                            ...f,
                            filaments: f.filaments.map((r, i) =>
                              i === index ? { ...r, item_id: e.target.value } : r,
                            ),
                          }))
                        }
                      >
                        <option value="">— فیلامنت —</option>
                        {filaments.map((f) => (
                          <option key={f.id} value={f.id}>
                            {f.name} ({faNumber(f.quantity)} گرم)
                          </option>
                        ))}
                      </select>
                      <Input
                        className="num h-8 text-xs"
                        aria-label={`گرم هر عدد ردیف ${faNumber(String(index + 1))}`}
                        data-testid={`job-spool-${index}-grams`}
                        placeholder="گرم/عدد"
                        value={row.grams}
                        onChange={(e) =>
                          setForm((f) => ({
                            ...f,
                            filaments: f.filaments.map((r, i) =>
                              i === index ? { ...r, grams: e.target.value } : r,
                            ),
                          }))
                        }
                      />
                      <Button
                        size="sm"
                        variant="ghost"
                        aria-label={`حذف فیلامنت ردیف ${faNumber(String(index + 1))}`}
                        data-testid={`job-spool-${index}-remove`}
                        disabled={form.filaments.length === 1}
                        onClick={() =>
                          setForm((f) => ({
                            ...f,
                            filaments: f.filaments.filter((_r, i) => i !== index),
                          }))
                        }
                      >
                        ×
                      </Button>
                    </div>
                    {short && (
                      <p className="text-[11px] text-amber-700 dark:text-amber-400">
                        نیاز این کار {faNumber(needed.toString())} گرم است؛ موجودی کافی نیست.
                      </p>
                    )}
                  </div>
                );
              })}
              <Button
                size="sm"
                variant="ghost"
                data-testid="job-spool-add"
                disabled={form.filaments.length >= 20}
                onClick={() =>
                  setForm((f) => ({
                    ...f,
                    filaments: [...f.filaments, { item_id: "", grams: "" }],
                  }))
                }
              >
                + افزودن فیلامنت
              </Button>
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
              disabled={
                createJob.isPending ||
                !form.product_name.trim() ||
                form.filaments.some((row) => !row.item_id || !row.grams.trim())
              }
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
