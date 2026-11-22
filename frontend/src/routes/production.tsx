/**
 * تولید — production jobs (MASTER_PROMPT §3.3).
 *
 * A job is planned from an order line (or manually). Its filament composition
 * is picked here, also for jobs that came from an order, and finishing it
 * consumes the filament and puts the produced models into the warehouse.
 * Delivering the order afterwards takes those models out again.
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

type FilamentRow = {
  id: string;
  filament_item_id: string | null;
  filament_item_name: string | null;
  grams_per_unit: string;
  unit_cost: string;
  grams_total: string;
};

type Job = {
  id: string;
  job_number: number;
  order_id: string | null;
  order_item_id: string | null;
  order_number: number | null;
  /** The ordered quantity of the linked order line (item 1 of the owner's list). */
  order_item_quantity?: string | null;
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
  filaments: FilamentRow[];
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

/**
 * «PLA — رنگ سفید» in the spool choosers: two spools of the same material are
 * told apart by their colour, and the owner asked for it next to the name.
 * When the name already ends with that colour («PLA سفید») it is not repeated.
 */
function spoolLabel(item: { name: string; color?: string | null }): string {
  const color = (item.color ?? "").trim();
  if (!color || item.name.includes(color)) return item.name;
  return `${item.name} — رنگ ${color}`;
}

const STATUS_VARIANT: Record<string, "secondary" | "warning" | "success" | "destructive"> = {
  PLANNED: "secondary",
  IN_PROGRESS: "warning",
  DONE: "success",
  CANCELLED: "destructive",
};

/** Item 6: only orders that are still being worked on can start a new job. */
const OPEN_ORDER_STATUSES = ["NEW", "CONFIRMED", "IN_PRODUCTION"];

/** Same quantity, told in the owner's words. */
function quantitiesDiffer(a: string, b: string): boolean {
  try {
    return !toDecimal(a).equals(toDecimal(b));
  } catch {
    return true;
  }
}

function errText(error: unknown): string {
  return error instanceof Error ? error.message : "خطای نامشخص";
}

type SpoolRow = { item_id: string; grams: string };

export function ProductionPage(): React.JSX.Element {
  const pricingQuery = usePricingSettings();
  const queryClient = useQueryClient();
  const [page, setPage] = React.useState(0);
  /** Inline filament editor — the only place a job's spools are chosen. */
  const [spoolJob, setSpoolJob] = React.useState<{ job: Job; rows: SpoolRow[] } | null>(null);
  /** Feedback stays inside the editor: the page-level note is out of sight there. */
  const [spoolError, setSpoolError] = React.useState<string | null>(null);
  const [statusFilter, setStatusFilter] = React.useState("");
  const [message, setMessage] = React.useState<string | null>(null);
  const [form, setForm] = React.useState({
    order_id: "",
    order_item_id: "",
    product_name: "",
    variant: "plain" as "plain" | "chain",
    channel: "marketplace" as "direct" | "marketplace",
    quantity: "1",
    print_hours: "",
    // a printed model may need several spools, each with its own grams
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
    queryKey: ["orders", "production-ready"],
    queryFn: async () => {
      const rows = await collectOperationPages(async (offset, limit) => {
        const res = await api.GET("/api/v1/orders", { params: { query: { offset, limit } } });
        if (res.error) throw await parseError(res.response);
        return res.data!;
      });
      return (rows as OrderOption[]).filter((o) => OPEN_ORDER_STATUSES.includes(o.status));
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

  /** A rejected row action stays beside that row; the page note is far above it. */
  const [actError, setActError] = React.useState<{ jobId: string; text: string } | null>(null);
  const act = useMutation({
    mutationFn: async (payload: { job: Job; action: "start" | "finish" | "cancel" }) => {
      const res = await api.POST(`/api/v1/production/jobs/{job_id}/${payload.action}`, {
        params: { path: { job_id: payload.job.id } },
      });
      if (res.error) throw await parseError(res.response);
      return res.data;
    },
    onSuccess: (_data, payload) => {
      setActError(null);
      setMessage(
        payload.action === "finish"
          ? "پایان چاپ ثبت شد ✓ محصول به انبار اضافه شد و فیلامنت کسر شد."
          : "وضعیت کار تولید به‌روز شد ✓",
      );
      invalidate();
    },
    onError: (e, payload) => {
      const text = errText(e);
      setActError({ jobId: payload.job.id, text });
      setMessage(text);
    },
  });

  const saveFilaments = useMutation({
    mutationFn: async () => {
      if (!spoolJob) throw new Error("کاری انتخاب نشده است");
      const job = spoolJob.job;
      // A row the owner started (picked a spool or typed grams) must be
      // complete. Dropping it silently used to look like "nothing changed".
      const started = spoolJob.rows.filter((row) => row.item_id !== "" || row.grams.trim() !== "");
      if (started.length === 0)
        throw new Error("حداقل یک فیلامنت انتخاب کنید و «گرم هر عدد» آن را بنویسید.");
      started.forEach((row, index) => {
        const label = `ردیف ${faNumber(String(index + 1))}`;
        if (!row.item_id) throw new Error(`${label}: فیلامنت را انتخاب کنید.`);
        if (!row.grams.trim()) throw new Error(`${label}: «گرم هر عدد» را وارد کنید.`);
      });
      const rows = started.map((row) => ({
        filament_item_id: row.item_id,
        grams_per_unit: parseNum(row.grams).toString(),
      }));
      if (new Set(rows.map((row) => row.filament_item_id)).size !== rows.length)
        throw new Error("هر فیلامنت فقط یک بار در یک کار تولید قابل انتخاب است.");
      const send = (versionId: number) =>
        api.PATCH("/api/v1/production/jobs/{job_id}", {
          params: { path: { job_id: job.id } },
          body: { version_id: versionId, filaments: rows },
        });
      let res = await send(job.version_id);
      if (res.error && res.response.status === 409) {
        // Someone (another tab, or a start/finish click) moved the job on.
        // Reload its revision and save once more instead of failing forever.
        const fresh = await api.GET("/api/v1/production/jobs/{job_id}", {
          params: { path: { job_id: job.id } },
        });
        if (fresh.error) throw await parseError(fresh.response);
        res = await send((fresh.data as unknown as Job).version_id);
      }
      if (res.error) {
        const error = await parseError(res.response);
        throw new Error(
          error.isStale
            ? "این کار همین حالا تغییر کرده بود؛ فهرست تازه شد — یک بار دیگر ذخیره کنید."
            : error.message,
        );
      }
      return (res.data ?? null) as unknown as Job | null;
    },
    onSuccess: (saved) => {
      // The row updates from the server's answer immediately, before any refetch.
      if (saved?.id) {
        queryClient.setQueriesData<Job[]>({ queryKey: ["production", "jobs"] }, (old) =>
          Array.isArray(old) ? old.map((row) => (row.id === saved.id ? (saved as Job) : row)) : old,
        );
      }
      setSpoolJob(null);
      setSpoolError(null);
      const spools = saved?.filaments?.length
        ? ` — ${saved.filaments
            .map(
              (row) =>
                `${row.filament_item_name ?? "فیلامنت"} ${faNumber(row.grams_per_unit)} گرم/عدد`,
            )
            .join(" + ")}`
        : "";
      setMessage(
        saved?.job_number
          ? `فیلامنت‌های کار #${faNumber(String(saved.job_number))} ذخیره شد ✓${spools}`
          : "فیلامنت‌های کار تولید ذخیره شد ✓",
      );
      invalidate();
    },
    onError: (e) => {
      setSpoolError(errText(e));
      setMessage(errText(e));
    },
  });

  const filaments = (itemsQuery.data ?? []).filter((i) => i.kind === "FILAMENT" && i.unit === "G");

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
    }));
  };

  /** The finish button is never dead: it asks for the missing spools instead. */
  const finish = (job: Job): void => {
    if (!job.filament_ready) {
      setMessage("برای پایان چاپ، ابتدا فیلامنت‌های مصرفی این کار را انتخاب کنید.");
      setSpoolJob({ job, rows: [{ item_id: "", grams: "" }] });
      return;
    }
    act.mutate({ job, action: "finish" });
  };

  const openSpools = (job: Job): void => {
    setSpoolError(null);
    setActError(null);
    setSpoolJob({
      job,
      rows: job.filaments.length
        ? job.filaments.map((row) => ({
            item_id: row.filament_item_id ?? "",
            grams: row.grams_per_unit,
          }))
        : [{ item_id: "", grams: "" }],
    });
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
        <p
          role="status"
          className="rounded-md bg-muted px-3 py-2 text-sm"
          data-testid="production-message"
        >
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
                    <th className="py-2 text-start font-medium">کار / سفارش</th>
                    <th className="py-2 ps-2 text-start font-medium">محصول</th>
                    <th className="py-2 ps-2 text-start font-medium">تعداد</th>
                    <th className="py-2 ps-2 text-start font-medium">فیلامنت</th>
                    <th className="py-2 ps-2 text-start font-medium">وضعیت</th>
                    <th className="py-2 ps-2 text-start font-medium">اقدام</th>
                  </tr>
                </thead>
                <tbody>
                  {(jobsQuery.isSuccess ? jobsQuery.data.slice(0, OPERATION_PAGE_SIZE) : []).map(
                    (job) => {
                      const ordered = job.order_item_quantity ?? null;
                      const partial = ordered ? quantitiesDiffer(ordered, job.quantity) : false;
                      return (
                        <tr
                          key={job.id}
                          className="border-b align-top"
                          data-testid={`job-${job.id}`}
                        >
                          <td className="py-3 pe-2">
                            <div className="num text-base font-bold">
                              #{faNumber(String(job.job_number))}
                            </div>
                            <div className="text-[11px] text-muted-foreground">
                              {job.order_number
                                ? `سفارش #${faNumber(String(job.order_number))}`
                                : "بدون سفارش"}
                            </div>
                          </td>
                          <td className="py-3 ps-2">
                            <div className="font-medium">{job.product_name}</div>
                            <div className="mt-1 flex flex-wrap items-center gap-1 text-[11px] text-muted-foreground">
                              <span>{job.variant === "chain" ? "حلقه و زنجیر" : "ساده"}</span>
                              <span>·</span>
                              <span>{job.channel === "marketplace" ? "بازارگاه" : "مستقیم"}</span>
                            </div>
                          </td>
                          <td className="num py-3 ps-2">
                            <div className="text-base font-bold">
                              {faNumber(job.quantity)} <span className="text-xs">عدد</span>
                            </div>
                            {ordered && (
                              <div className="text-[11px] text-muted-foreground">
                                {partial ? `از ${faNumber(ordered)} عدد سفارش` : "کل تعداد سفارش"}
                              </div>
                            )}
                          </td>
                          <td className="py-3 ps-2 text-xs" data-testid={`job-${job.id}-spools`}>
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
                          <td className="py-3 ps-2">
                            <Badge variant={STATUS_VARIANT[job.status]}>
                              {STATUS_LABEL[job.status]}
                            </Badge>
                          </td>
                          <td className="py-3 ps-2">
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
                                    disabled={act.isPending}
                                    onClick={() => finish(job)}
                                  >
                                    پایان (کسر فیلامنت)
                                  </Button>
                                  <Button
                                    size="sm"
                                    variant="outline"
                                    data-testid={`job-${job.id}-filaments`}
                                    onClick={() => openSpools(job)}
                                  >
                                    فیلامنت‌ها
                                  </Button>
                                  <Button
                                    size="sm"
                                    variant="ghost"
                                    data-testid={`job-${job.id}-cancel`}
                                    disabled={act.isPending}
                                    onClick={() => act.mutate({ job, action: "cancel" })}
                                  >
                                    لغو
                                  </Button>
                                </>
                              )}
                            </div>
                            {actError?.jobId === job.id && (
                              <p
                                role="alert"
                                data-testid={`job-${job.id}-action-error`}
                                className="mt-1 max-w-56 text-[11px] text-destructive"
                              >
                                {actError.text}
                              </p>
                            )}
                          </td>
                        </tr>
                      );
                    },
                  )}
                  {jobsQuery.isSuccess && jobsQuery.data.length === 0 && (
                    <tr>
                      <td colSpan={6} className="py-6 text-center text-muted-foreground">
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
            {spoolJob && (
              <div className="mt-3 space-y-2 rounded border p-3" data-testid="job-filament-editor">
                <p className="text-sm font-medium">
                  فیلامنت‌های مصرفی کار #{faNumber(String(spoolJob.job.job_number))} —{" "}
                  {spoolJob.job.product_name}
                </p>
                <p className="text-xs text-muted-foreground">
                  گرم هر عدد را وارد کنید؛ هنگام «پایان چاپ» همین مقدار × تعداد از انبار کسر می‌شود
                  و محصول به انبار اضافه می‌شود.
                </p>
                <QueryNotice query={itemsQuery} />
                {itemsQuery.isSuccess && filaments.length === 0 && (
                  <p className="rounded-md bg-amber-50 px-2 py-1 text-xs text-amber-800 dark:bg-amber-900/30 dark:text-amber-200">
                    هیچ فیلامنت فعالی با واحد گرم در انبار نیست؛ اول در صفحهٔ «انبار» یک فیلامنت
                    بسازید.
                  </p>
                )}
                {spoolError && (
                  <p
                    role="alert"
                    data-testid="job-filament-editor-error"
                    className="rounded-md bg-destructive/10 px-2 py-1 text-xs text-destructive"
                  >
                    {spoolError}
                  </p>
                )}
                {spoolJob.rows.map((row, index) => (
                  <div key={index} className="grid grid-cols-[1fr_6rem_auto] gap-1">
                    <select
                      aria-label={`فیلامنت ردیف ${faNumber(String(index + 1))} کار تولید`}
                      data-testid={`job-filament-editor-item-${index}`}
                      className="flex h-8 w-full rounded-md border border-input bg-background px-2 text-xs text-foreground"
                      value={row.item_id}
                      onChange={(e) =>
                        setSpoolJob((current) =>
                          current
                            ? {
                                ...current,
                                rows: current.rows.map((r, i) =>
                                  i === index ? { ...r, item_id: e.target.value } : r,
                                ),
                              }
                            : current,
                        )
                      }
                    >
                      <option value="">— فیلامنت —</option>
                      {filaments.map((f) => (
                        <option key={f.id} value={f.id}>
                          {spoolLabel(f)} ({faNumber(f.quantity)} گرم)
                        </option>
                      ))}
                    </select>
                    <Input
                      className="num h-8 text-xs"
                      aria-label={`گرم فیلامنت هر عدد ردیف ${faNumber(String(index + 1))}`}
                      data-testid={`job-filament-editor-grams-${index}`}
                      placeholder="گرم/عدد"
                      value={row.grams}
                      onChange={(e) =>
                        setSpoolJob((current) =>
                          current
                            ? {
                                ...current,
                                rows: current.rows.map((r, i) =>
                                  i === index ? { ...r, grams: e.target.value } : r,
                                ),
                              }
                            : current,
                        )
                      }
                    />
                    <Button
                      size="sm"
                      variant="ghost"
                      aria-label={`حذف فیلامنت ردیف ${faNumber(String(index + 1))}`}
                      data-testid={`job-filament-editor-remove-${index}`}
                      disabled={spoolJob.rows.length === 1}
                      onClick={() =>
                        setSpoolJob((current) =>
                          current
                            ? {
                                ...current,
                                rows: current.rows.filter((_r, i) => i !== index),
                              }
                            : current,
                        )
                      }
                    >
                      ×
                    </Button>
                  </div>
                ))}
                <div className="flex flex-wrap gap-1">
                  <Button
                    size="sm"
                    variant="ghost"
                    data-testid="job-filament-editor-add"
                    disabled={spoolJob.rows.length >= 20}
                    onClick={() =>
                      setSpoolJob((current) =>
                        current
                          ? { ...current, rows: [...current.rows, { item_id: "", grams: "" }] }
                          : current,
                      )
                    }
                  >
                    + افزودن فیلامنت
                  </Button>
                  <Button
                    size="sm"
                    data-testid="job-filament-editor-save"
                    disabled={saveFilaments.isPending}
                    onClick={() => {
                      setSpoolError(null);
                      saveFilaments.mutate();
                    }}
                  >
                    ذخیرهٔ فیلامنت‌ها
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      setSpoolError(null);
                      setSpoolJob(null);
                    }}
                  >
                    انصراف
                  </Button>
                </div>
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
                    #{o.order_number} — {o.customer_name} ({o.items.length} قلم)
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
                    setForm((f) => ({
                      ...f,
                      channel: e.target.value as "direct" | "marketplace",
                    }))
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
                            {spoolLabel(f)} ({faNumber(f.quantity)} گرم)
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
            {selectedLine ? (
              <p className="text-xs text-muted-foreground" data-testid="job-price-snapshot">
                قیمت و بهای واحد از ردیف ذخیره‌شدهٔ سفارش؛ بدون محاسبهٔ مجدد با ثابت‌های تازه:{" "}
                <Money value={selectedLine.unit_price} currency="TOMAN" /> /{" "}
                <Money value={selectedLine.unit_cost} currency="TOMAN" />
              </p>
            ) : (
              <p className="text-xs text-muted-foreground">
                کار مستقل با ثابت‌های فعلی قیمت‌گذاری می‌شود. برای پایان تولید، فیلامنت و وزن مثبت
                لازم است؛ محصول با همین نام در انبار ساخته یا پیدا می‌شود.
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
