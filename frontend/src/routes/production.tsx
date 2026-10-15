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
import { computePrice, DEFAULT_CONSTANTS, type PriceInputs } from "@/lib/priceCalc";
import { faNumber } from "@/lib/fa";

type Job = {
  id: string;
  job_number: number;
  order_id: string | null;
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
  kind: "FILAMENT" | "PRODUCT";
  unit: "G" | "PCS";
  quantity: string;
};

type OrderOption = {
  id: string;
  order_number: number;
  customer_name: string;
  status: string;
  items: Array<{
    id: string;
    product_name: string;
    variant: "plain" | "chain";
    quantity: string;
    weight_g: string;
    print_hours: string;
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
  const queryClient = useQueryClient();
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
    queryKey: ["production", "jobs", statusFilter],
    queryFn: async () => {
      const res = await api.GET("/api/v1/production/jobs", {
        params: { query: statusFilter ? { status: statusFilter } : {} },
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
      const res = await api.GET("/api/v1/warehouse/items", { params: { query: {} } });
      if (res.error) throw await parseError(res.response);
      return res.data as unknown as Item[];
    },
  });

  const ordersQuery = useQuery({
    queryKey: ["orders", "open"],
    queryFn: async () => {
      const res = await api.GET("/api/v1/orders", { params: { query: {} } });
      if (res.error) throw await parseError(res.response);
      return (res.data as unknown as OrderOption[]).filter(
        (o) => !["CANCELLED", "DELIVERED"].includes(o.status),
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
      const inputs: PriceInputs = {
        weightG: form.filament_grams || "0",
        printHours: form.print_hours || "0",
        quantity: form.quantity || "1",
        variant: form.variant,
        channel: form.channel,
      };
      let unitCost = "0";
      let unitPrice = "0";
      try {
        const priced = computePrice(inputs, DEFAULT_CONSTANTS);
        unitCost = priced.unitProductionWithChain.toFixed(4);
        unitPrice = priced.unitFinalPrice.toFixed(4);
      } catch {
        // invalid numbers → the job is still created with zero price snapshot
      }
      const res = await api.POST("/api/v1/production/jobs", {
        body: {
          product_name: form.product_name,
          quantity: form.quantity || "1",
          variant: form.variant,
          channel: form.channel,
          order_id: form.order_id || null,
          order_item_id: form.order_item_id || null,
          filament_item_id: form.filament_item_id || null,
          product_item_id: form.product_item_id || null,
          filament_grams: form.filament_grams || "0",
          print_hours: form.print_hours || "0",
          unit_cost: unitCost,
          unit_price: unitPrice,
        },
      });
      if (res.error) throw await parseError(res.response);
      return res.data;
    },
    onSuccess: () => {
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

  const filaments = (itemsQuery.data ?? []).filter((i) => i.kind === "FILAMENT");
  const products = (itemsQuery.data ?? []).filter((i) => i.kind === "PRODUCT");

  const pickOrder = (orderId: string): void => {
    const order = (ordersQuery.data ?? []).find((o) => o.id === orderId);
    const firstLine = order?.items[0];
    setForm((f) => ({
      ...f,
      order_id: orderId,
      order_item_id: firstLine?.id ?? "",
      product_name: firstLine?.product_name ?? f.product_name,
      variant: firstLine?.variant ?? f.variant,
      quantity: firstLine?.quantity ?? f.quantity,
      filament_grams: firstLine?.weight_g ?? f.filament_grams,
      print_hours: firstLine?.print_hours ?? f.print_hours,
    }));
  };

  return (
    <div className="space-y-6" dir="rtl">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-bold">تولید</h1>
        <div className="flex gap-2 text-sm">
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
              onChange={(e) => setStatusFilter(e.target.value)}
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
                  {(jobsQuery.data ?? []).map((job) => (
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
                        {Number(job.filament_grams) > 0 && (
                          <div className="num text-muted-foreground">
                            {faNumber(job.filament_grams)} گرم × {faNumber(job.quantity)} ={" "}
                            {faNumber(String(Number(job.filament_grams) * Number(job.quantity)))}{" "}
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
                                onClick={() => act.mutate({ job, action: "finish" })}
                              >
                                پایان (کسر فیلامنت)
                              </Button>
                              <Button
                                size="sm"
                                variant="ghost"
                                onClick={() => act.mutate({ job, action: "cancel" })}
                              >
                                لغو
                              </Button>
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                  {(jobsQuery.data ?? []).length === 0 && (
                    <tr>
                      <td colSpan={8} className="py-6 text-center text-muted-foreground">
                        کار تولیدی ثبت نشده است.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
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
                onChange={(e) => pickOrder(e.target.value)}
              >
                <option value="">— بدون سفارش —</option>
                {(ordersQuery.data ?? []).map((o) => (
                  <option key={o.id} value={o.id}>
                    #{o.order_number} — {o.customer_name}
                  </option>
                ))}
              </select>
            </div>
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
            <p className="text-xs text-muted-foreground">
              بهای تمام‌شده و قیمت فروش هر عدد هنگام ثبت، از ماشین‌حساب قیمت‌گذاری (فایل اکسل)
              محاسبه و ذخیره می‌شود.
            </p>
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
