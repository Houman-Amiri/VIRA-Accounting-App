/**
 * سفارش‌ها — customer orders (MASTER_PROMPT §3.2).
 *
 * Order list with status/search/date filters, a line-item form whose
 * unit price can be filled straight from the pricing engine (قیمت نهایی.xlsx),
 * status transitions, proforma PDF download and the daily/weekly/monthly/annual
 * sales report.
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
import { parseNum } from "@/lib/priceCalc";
import { CalendarInput } from "@/components/calendar-input";
import { useCalendar } from "@/lib/calendar-settings";
import { tehranToday, validIso } from "@/lib/calendar";
import { faDate, faNumber } from "@/lib/fa";
import { cn } from "@/lib/cn";
import { useVariables } from "@/lib/pricing-settings";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  CALCULATED_CHARGE_PREFIX,
  clearTransfer,
  readTransfer,
  writeTransfer,
} from "@/lib/order-pricing-transfer";

/**
 * «هزینهٔ طراحی» (hours × the design-rate variable) or one of the owner's
 * monetary variables with the quantity typed for this line. Both land on the order
 * total and print on their own row in the proforma.
 */
type OrderLineCharge = {
  kind: "DESIGN" | "VARIABLE";
  id?: string;
  quantity?: string;
  rate?: string;
  legacy?: boolean;
  variable_id: string;
  name: string;
  hours: string;
  amount: string;
};

type ReadCharge = {
  id: string;
  kind: "DESIGN" | "VARIABLE";
  variable_id: string | null;
  name: string;
  hours: string;
  rate: string;
  amount: string;
  quantity?: string | null;
};

type OrderLine = {
  /** Warehouse item, when the owner picks one; empty means a free line. */
  inventory_item_id: string;
  /** The product name. A free line carries its own; a warehouse line may too. */
  product_name: string;
  variant: "plain" | "chain";
  quantity: string;
  unit_price: string;
  unit_cost: string;
  notes: string;
  charges: OrderLineCharge[];
};

type WarehouseItem = {
  id: string;
  name: string;
  kind: string;
  unit: string;
  quantity: string;
  unit_price: string;
};

type PlannedJobView = {
  job_id: string;
  job_number: number;
  product_name: string;
  quantity: string;
};

type ProductionPlan = {
  created: PlannedJobView[];
  skipped: string[];
  warnings: string[];
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
  discount_type?: "AMOUNT" | "PERCENT";
  discount_value?: string;
  discount_amount?: string;
  items: Array<
    {
      id: string;
      product_name: string;
      inventory_item_name?: string | null;
      charges_total?: string;
      charges?: ReadCharge[];
      notes?: string | null;
    } & Omit<OrderLine, "charges" | "notes">
  >;
  warnings?: string[];
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

/** The orders page lists live work; finished/cancelled orders live in history. */
const ACTIVE_STATUSES = ["NEW", "CONFIRMED", "IN_PRODUCTION", "READY"];

const emptyLine = (): OrderLine => ({
  inventory_item_id: "",
  product_name: "",
  variant: "plain",
  quantity: "1",
  unit_price: "",
  unit_cost: "",
  notes: "",
  charges: [],
});

/** A pristine order form — used on cancel and after a successful edit. */
const blankForm = () => ({
  order_date: tehranToday(),
  customer_name: "",
  customer_phone: "",
  customer_address: "",
  notes: "",
  discount_type: "AMOUNT" as "AMOUNT" | "PERCENT",
  discount_value: "",
  items: [emptyLine()],
});

/** A line is usable when it names its product or points at a warehouse item. */
function lineReady(line: OrderLine): boolean {
  if (!line.product_name.trim() && !line.inventory_item_id) return false;
  // A free line has no catalogue price to fall back on, so the owner sets one.
  if (!line.inventory_item_id) {
    try {
      return parseNum(line.unit_price).gt(0);
    } catch {
      return false;
    }
  }
  return true;
}

function errText(error: unknown): string {
  return error instanceof Error ? error.message : "خطای نامشخص";
}

export function OrdersPage(): React.JSX.Element {
  const { calendar, ready: calendarReady } = useCalendar();
  const [fromInvalid, setFromInvalid] = React.useState(false);
  const [toInvalid, setToInvalid] = React.useState(false);
  const queryClient = useQueryClient();
  const [page, setPage] = React.useState(0);
  // «اقلام» is a dropdown: one order's items are expanded at a time, so the
  // table stays compact even when an order carries many lines.
  const [openItems, setOpenItems] = React.useState<string | null>(null);
  const [statusFilter, setStatusFilter] = React.useState("");
  const [search, setSearch] = React.useState("");
  const [dateFrom, setDateFrom] = React.useState("");
  const [dateTo, setDateTo] = React.useState("");
  const [period, setPeriod] = React.useState<"daily" | "weekly" | "monthly" | "annual">("monthly");
  const [message, setMessage] = React.useState<string | null>(null);
  const [createWarnings, setCreateWarnings] = React.useState<string[]>([]);
  /** Item 8: a NEW (not yet confirmed) order stays fully editable. */
  const [transfer] = React.useState(() => readTransfer<ReturnType<typeof blankForm>, Order>());
  const [tab, setTab] = React.useState(transfer ? "form" : "list");
  const [editing, setEditing] = React.useState<Order | null>(transfer?.editing ?? null);
  /** Item 9: deleting asks once inside the row, no browser prompt. */
  const [confirmDelete, setConfirmDelete] = React.useState<string | null>(null);
  const [form, setForm] = React.useState<ReturnType<typeof blankForm>>(() => {
    if (!transfer?.form?.items?.[transfer.lineIndex]) return blankForm();
    const form = transfer.form;
    if (!transfer.result) return form;
    const result = transfer.result;
    return {
      ...form,
      items: form.items.map((line, index) =>
        index !== transfer.lineIndex
          ? line
          : {
              ...line,
              quantity: result.quantity,
              unit_price: result.unitPrice,
              unit_cost: result.unitCost,
              notes: [line.notes?.split(/\n?جزئیات قیمت‌گذاری:/)[0] || "", result.details]
                .filter(Boolean)
                .join("\n"),
              charges: [
                ...line.charges.filter(
                  (charge) => !charge.name.startsWith(CALCULATED_CHARGE_PREFIX),
                ),
                ...result.oneTime.map((entry) => ({
                  kind: "VARIABLE" as const,
                  variable_id: "",
                  name: (CALCULATED_CHARGE_PREFIX + entry.name).slice(0, 120),
                  quantity: "",
                  hours: "",
                  amount: entry.amount,
                  legacy: true,
                })),
              ],
            },
      ),
    };
  });
  React.useEffect(() => {
    if (transfer) clearTransfer();
  }, [transfer]);

  const filtersReady =
    calendarReady && !fromInvalid && !toInvalid && !(dateFrom && dateTo && dateFrom > dateTo);
  const ordersQuery = useQuery({
    enabled: filtersReady,
    queryKey: ["orders", statusFilter, search, dateFrom, dateTo, page],
    queryFn: async () => {
      const res = await api.GET("/api/v1/orders", {
        params: {
          query: {
            limit: OPERATION_PAGE_SIZE + 1,
            offset: page * OPERATION_PAGE_SIZE,
            status_group: "active" as const,
            ...(statusFilter ? { status: statusFilter } : {}),
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

  const warehouseQuery = useQuery({
    queryKey: ["warehouse", "items", "orderable"],
    queryFn: async () => {
      const res = await api.GET("/api/v1/warehouse/items");
      if (res.error) throw await parseError(res.response);
      return (res.data as unknown as WarehouseItem[]).filter(
        (item) => item.kind === "PRODUCT" && item.unit === "PCS",
      );
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

  /** Drop a line; the form always keeps at least one empty row to fill. */
  const removeLine = (index: number): void => {
    setForm((current) => {
      const remaining = current.items.filter((_, position) => position !== index);
      return { ...current, items: remaining.length ? remaining : [emptyLine()] };
    });
  };

  const startEditing = (order: Order): void => {
    setConfirmDelete(null);
    setCreateWarnings([]);
    setEditing(order);
    setTab("form");
    setForm({
      order_date: order.order_date,
      customer_name: order.customer_name,
      customer_phone: order.customer_phone ?? "",
      customer_address: order.customer_address ?? "",
      notes: order.notes ?? "",
      discount_type: order.discount_type ?? "AMOUNT",
      discount_value:
        order.discount_value && parseNum(order.discount_value).gt(0) ? order.discount_value : "",
      items: order.items.map((line) => ({
        inventory_item_id: line.inventory_item_id ?? "",
        product_name: line.product_name,
        variant: line.variant,
        quantity: line.quantity,
        unit_price: line.unit_price,
        unit_cost: line.unit_cost,
        notes: line.notes ?? "",
        charges: (line.charges ?? []).map((charge) => ({
          kind: charge.kind,
          id: charge.id,
          quantity: charge.quantity ?? "",
          rate: charge.rate,
          legacy: charge.kind === "VARIABLE" && charge.quantity == null,
          variable_id: charge.variable_id ?? "",
          name: charge.name,
          hours: charge.kind === "DESIGN" ? charge.hours : "",
          amount: charge.kind === "DESIGN" ? "" : charge.amount,
        })),
      })),
    });
    setPage(0);
    setMessage(null);
  };

  const cancelEditing = (): void => {
    setEditing(null);
    setForm((f) => ({ ...blankForm(), order_date: f.order_date }));
  };

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
          // Only direct sales remain; the server keeps the historical column.
          channel: "direct" as const,
          notes: form.notes || null,
          discount_type: form.discount_type,
          discount_value: parseNum(form.discount_value || "0").toString(),
          items: form.items.map((line) => ({
            // A free line carries its name; a warehouse line falls back to the
            // item's own name on the server when this is empty.
            product_name: line.product_name.trim(),
            inventory_item_id: line.inventory_item_id || null,
            variant: line.variant,
            quantity: parseNum(line.quantity || "1").toString(),
            // 0 means "use the warehouse price", decided by the server
            unit_price: line.unit_price.trim() ? parseNum(line.unit_price).toString() : "0",
            unit_cost: line.unit_cost.trim() ? parseNum(line.unit_cost).toString() : "0",
            notes: line.notes || null,
            charges: line.charges.map((charge) => ({
              kind: charge.kind,
              id: charge.id ?? null,
              quantity:
                charge.kind === "VARIABLE" && !charge.legacy
                  ? parseNum(charge.quantity || "0").toString()
                  : null,
              variable_id: charge.variable_id || null,
              name: charge.kind === "DESIGN" ? "هزینه طراحی" : charge.name,
              hours:
                charge.kind === "DESIGN" && charge.hours.trim()
                  ? parseNum(charge.hours).toString()
                  : "0",
              amount:
                charge.kind === "VARIABLE" && charge.legacy && charge.amount.trim()
                  ? parseNum(charge.amount).toString()
                  : "0",
            })),
          })),
        },
      });
      if (res.error) throw await parseError(res.response);
      return res.data as unknown as Order;
    },
    onSuccess: (created: Order) => {
      setTab("list");
      setPage(0);
      setForm((f) => ({
        ...f,
        customer_name: "",
        customer_phone: "",
        customer_address: "",
        discount_type: "AMOUNT",
        discount_value: "",
        items: [emptyLine()],
      }));
      const warnings = created.warnings ?? [];
      setMessage(
        warnings.length ? `سفارش ثبت شد ✓ — هشدار: ${warnings.join(" | ")}` : "سفارش ثبت شد ✓",
      );
      setCreateWarnings(warnings);
      invalidate();
    },
    onError: (e) => setMessage(errText(e)),
  });

  const saveOrder = useMutation({
    mutationFn: async () => {
      if (!editing) throw new Error("سفارشی برای ویرایش انتخاب نشده است");
      if (!calendarReady || !validIso(form.order_date))
        throw new Error("تاریخ معتبر و تنظیم تقویم باید دریافت شوند.");
      const res = await api.PATCH("/api/v1/orders/{order_id}", {
        params: { path: { order_id: editing.id } },
        body: {
          version_id: editing.version_id,
          order_date: form.order_date,
          customer_name: form.customer_name,
          customer_phone: form.customer_phone || null,
          customer_address: form.customer_address || null,
          // Only direct sales remain; the server keeps the historical column.
          channel: "direct" as const,
          notes: form.notes || null,
          discount_type: form.discount_type,
          discount_value: parseNum(form.discount_value || "0").toString(),
          items: form.items.map((line) => ({
            product_name: line.product_name.trim(),
            inventory_item_id: line.inventory_item_id || null,
            variant: line.variant,
            quantity: parseNum(line.quantity || "1").toString(),
            unit_price: line.unit_price.trim() ? parseNum(line.unit_price).toString() : "0",
            unit_cost: line.unit_cost.trim() ? parseNum(line.unit_cost).toString() : "0",
            notes: line.notes || null,
            charges: line.charges.map((charge) => ({
              kind: charge.kind,
              id: charge.id ?? null,
              quantity:
                charge.kind === "VARIABLE" && !charge.legacy
                  ? parseNum(charge.quantity || "0").toString()
                  : null,
              variable_id: charge.variable_id || null,
              name: charge.kind === "DESIGN" ? "هزینه طراحی" : charge.name,
              hours:
                charge.kind === "DESIGN" && charge.hours.trim()
                  ? parseNum(charge.hours).toString()
                  : "0",
              amount:
                charge.kind === "VARIABLE" && charge.legacy && charge.amount.trim()
                  ? parseNum(charge.amount).toString()
                  : "0",
            })),
          })),
        },
      });
      if (res.error) throw await parseError(res.response);
      return res.data as unknown as Order;
    },
    onSuccess: (saved: Order) => {
      setTab("list");
      setMessage(`سفارش #${faNumber(String(saved.order_number))} ویرایش شد ✓`);
      setEditing(null);
      setCreateWarnings([]);
      setForm((f) => ({ ...blankForm(), order_date: f.order_date }));
      invalidate();
    },
    onError: (e) => setMessage(errText(e)),
  });

  const deleteOrder = useMutation({
    mutationFn: async (order: Order) => {
      const res = await api.DELETE("/api/v1/orders/{order_id}", {
        params: { path: { order_id: order.id } },
      });
      if (res.error) throw await parseError(res.response);
      return order;
    },
    onSuccess: (order: Order) => {
      setMessage(`سفارش #${faNumber(String(order.order_number))} حذف شد ✓`);
      setConfirmDelete(null);
      if (editing?.id === order.id) setEditing(null);
      invalidate();
    },
    onError: (e) => {
      setConfirmDelete(null);
      setMessage(errText(e));
    },
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

  const variablesQuery = useVariables();
  const variables = React.useMemo(
    () => (variablesQuery.data ?? []).filter((variable) => variable.is_active),
    [variablesQuery.data],
  );
  /** The variable the owner marked as «نرخ هر ساعت طراحی» (settings page). */
  const designRate = React.useMemo(
    () => variables.find((variable) => variable.is_design_rate),
    [variables],
  );
  const chargeAmount = React.useCallback(
    (charge: OrderLineCharge) => {
      try {
        if (charge.kind === "DESIGN") {
          return parseNum(charge.hours || "0")
            .times(parseNum(charge.rate ?? designRate?.value ?? "0"))
            .toDecimalPlaces(4);
        }
        if (charge.legacy) return parseNum(charge.amount || "0");
        const variable = variables.find((row) => row.id === charge.variable_id);
        return parseNum(charge.quantity || "0")
          .times(parseNum(charge.rate ?? variable?.value ?? "0"))
          .toDecimalPlaces(4);
      } catch {
        return parseNum("0");
      }
    },
    [designRate, variables],
  );

  const orderable = React.useMemo(() => warehouseQuery.data ?? [], [warehouseQuery.data]);
  const productById = React.useMemo(
    () => new Map(orderable.map((item) => [item.id, item])),
    [orderable],
  );

  /** Stock notice for one line: the order is still saved, production covers it. */
  const lineShortage = (line: OrderLine): string | null => {
    const item = productById.get(line.inventory_item_id);
    if (!item) return null;
    try {
      const ordered = parseNum(line.quantity || "0");
      const stock = parseNum(item.quantity || "0");
      if (ordered.gt(stock)) {
        return `موجودی ${faNumber(item.quantity)} عدد — کمبود ${faNumber(
          ordered.minus(stock).toString(),
        )} عدد به خط تولید می‌رود.`;
      }
    } catch {
      return null;
    }
    return null;
  };

  const pickProduct = (index: number, itemId: string): void => {
    const item = productById.get(itemId);
    updateLine(index, {
      inventory_item_id: itemId,
      product_name: item ? item.name : "",
      // the warehouse price is the reference price; the user may still edit it
      unit_price: item ? item.unit_price : "",
    });
  };

  const updateLine = (index: number, patch: Partial<OrderLine>): void =>
    setForm((f) => ({
      ...f,
      items: f.items.map((line, i) => (i === index ? { ...line, ...patch } : line)),
    }));

  const updateCharge = (
    lineIndex: number,
    chargeIndex: number,
    patch: Partial<OrderLineCharge>,
  ): void =>
    setForm((f) => ({
      ...f,
      items: f.items.map((line, i) =>
        i === lineIndex
          ? {
              ...line,
              charges: line.charges.map((charge, j) =>
                j === chargeIndex ? { ...charge, ...patch } : charge,
              ),
            }
          : line,
      ),
    }));

  const addCharge = (lineIndex: number, charge: OrderLineCharge): void =>
    setForm((f) => ({
      ...f,
      items: f.items.map((line, i) =>
        i === lineIndex ? { ...line, charges: [...line.charges, charge] } : line,
      ),
    }));

  const removeCharge = (lineIndex: number, chargeIndex: number): void =>
    setForm((f) => ({
      ...f,
      items: f.items.map((line, i) =>
        i === lineIndex
          ? { ...line, charges: line.charges.filter((_charge, j) => j !== chargeIndex) }
          : line,
      ),
    }));

  const planProduction = useMutation({
    mutationFn: async (order: Order) => {
      const res = await api.POST("/api/v1/orders/{order_id}/production", {
        params: { path: { order_id: order.id } },
      });
      if (res.error) throw await parseError(res.response);
      return res.data as unknown as ProductionPlan;
    },
    onSuccess: (plan) => {
      const names = plan.created
        .map((job) => `#${faNumber(String(job.job_number))} ${job.product_name}`)
        .join("، ");
      const extra = plan.warnings.length ? ` — ${plan.warnings.join(" | ")}` : "";
      setMessage(`به خط تولید اضافه شد ✓ ${names}${extra}`);
      void queryClient.invalidateQueries({ queryKey: ["production"] });
      invalidate();
    },
    onError: (e) => setMessage(errText(e)),
  });

  const formSubtotal = React.useMemo(() => {
    try {
      return form.items
        .reduce((sum, line) => {
          // «هزینهٔ طراحی» و متغیرهای هر ردیف، بخشی از مبلغ سفارش‌اند.
          const charges = line.charges.reduce(
            (total, charge) => total.plus(chargeAmount(charge)),
            parseNum("0"),
          );
          let price = parseNum(line.unit_price);
          if (price.lte(0) && line.inventory_item_id) {
            price = parseNum(productById.get(line.inventory_item_id)?.unit_price ?? "0");
          }
          return sum.plus(parseNum(line.quantity).times(price)).plus(charges);
        }, parseNum("0"))
        .toDecimalPlaces(4);
    } catch {
      return parseNum("0");
    }
  }, [form.items, chargeAmount, productById]);

  const discount = React.useMemo(() => {
    const zero = parseNum("0");
    try {
      const value = parseNum(form.discount_value || "0");
      if (value.isNegative() || value.decimalPlaces() > 4 || value.gte("100000000000000"))
        return { amount: zero, error: "تخفیف باید نامنفی و حداکثر چهار رقم اعشار باشد." };
      if (form.discount_type === "PERCENT" && value.gt(100))
        return { amount: zero, error: "درصد تخفیف نمی‌تواند بیشتر از ۱۰۰ باشد." };
      const amount =
        form.discount_type === "PERCENT"
          ? formSubtotal.times(value).div(100).toDecimalPlaces(4)
          : value;
      if (amount.gt(formSubtotal))
        return { amount: zero, error: "مبلغ تخفیف نمی‌تواند بیشتر از جمع سفارش باشد." };
      return { amount, error: null };
    } catch {
      return { amount: zero, error: "مقدار تخفیف معتبر نیست." };
    }
  }, [form.discount_type, form.discount_value, formSubtotal]);
  const formTotal = formSubtotal.minus(discount.amount);

  return (
    <div className="space-y-6" dir="rtl">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-xl font-bold">سفارش‌ها</h1>
          <p className="text-xs text-muted-foreground">
            سفارش‌های فعال؛ سفارش‌های تحویل‌شده و لغوشده در تاریخچهٔ سفارشات هستند.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Link
            to="/orders/history"
            data-testid="orders-history-link"
            className="inline-flex h-9 items-center rounded-md border border-input px-3 text-sm hover:bg-accent"
          >
            تاریخچهٔ سفارشات
          </Link>
          <Badge variant="outline">
            فروش دوره:{" "}
            {reportQuery.isSuccess ? (
              <Money value={reportQuery.data.revenue} currency="TOMAN" />
            ) : (
              "نامشخص"
            )}
          </Badge>
        </div>
      </div>

      {message && (
        <p className="rounded-md bg-muted px-3 py-2 text-sm" data-testid="orders-message">
          {message}
        </p>
      )}

      <Tabs value={tab} onValueChange={setTab} dir="rtl">
        <TabsList aria-label="بخش سفارش‌ها">
          <TabsTrigger value="list" data-testid="orders-tab-list">
            فهرست سفارش‌ها
          </TabsTrigger>
          <TabsTrigger value="form" data-testid="orders-tab-form">
            ثبت سفارش
          </TabsTrigger>
        </TabsList>
        <TabsContent value="list">
          <Card className="min-w-0">
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
                    data-testid="orders-status"
                    onChange={(e) => {
                      setStatusFilter(e.target.value);
                      setPage(0);
                    }}
                  >
                    <option value="">همه</option>
                    {ACTIVE_STATUSES.map((value) => (
                      <option key={value} value={value}>
                        {STATUS_LABEL[value]}
                      </option>
                    ))}
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
                    {(filtersReady && ordersQuery.isSuccess
                      ? ordersQuery.data.slice(0, OPERATION_PAGE_SIZE)
                      : []
                    ).map((order) => (
                      <React.Fragment key={order.id}>
                        <tr className="border-b" data-testid={`order-${order.id}`}>
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
                              aria-controls={`order-items-${order.id}`}
                              data-testid={`order-${order.id}-items-toggle`}
                              onClick={() =>
                                setOpenItems((current) => (current === order.id ? null : order.id))
                              }
                              className={cn(
                                "inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs hover:bg-accent",
                                openItems === order.id && "bg-accent",
                              )}
                            >
                              <span className="num">{faNumber(String(order.items.length))}</span>
                              قلم
                              {(order.warnings ?? []).length > 0 && (
                                <span className="rounded-full bg-amber-100 px-1.5 text-[10px] text-amber-800 dark:bg-amber-900/40 dark:text-amber-200">
                                  کمبود
                                </span>
                              )}
                              <span aria-hidden className="text-[10px] text-muted-foreground">
                                {openItems === order.id ? "▲" : "▼"}
                              </span>
                            </button>
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
                              {ACTIVE_STATUSES.includes(order.status) &&
                                order.status !== "READY" && (
                                  <Button
                                    size="sm"
                                    variant="outline"
                                    data-testid={`order-${order.id}-to-production`}
                                    disabled={planProduction.isPending}
                                    onClick={() => planProduction.mutate(order)}
                                  >
                                    افزودن به خط تولید
                                  </Button>
                                )}
                              {order.status === "NEW" && (
                                <>
                                  <Button
                                    size="sm"
                                    variant="outline"
                                    data-testid={`order-${order.id}-edit`}
                                    onClick={() => startEditing(order)}
                                  >
                                    ویرایش
                                  </Button>
                                  {confirmDelete === order.id ? (
                                    <>
                                      <Button
                                        size="sm"
                                        variant="destructive"
                                        data-testid={`order-${order.id}-delete-confirm`}
                                        disabled={deleteOrder.isPending}
                                        onClick={() => deleteOrder.mutate(order)}
                                      >
                                        تأیید حذف
                                      </Button>
                                      <Button
                                        size="sm"
                                        variant="ghost"
                                        onClick={() => setConfirmDelete(null)}
                                      >
                                        انصراف
                                      </Button>
                                    </>
                                  ) : (
                                    <Button
                                      size="sm"
                                      variant="ghost"
                                      className="text-destructive"
                                      data-testid={`order-${order.id}-delete`}
                                      onClick={() => setConfirmDelete(order.id)}
                                    >
                                      حذف
                                    </Button>
                                  )}
                                </>
                              )}
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
                        {openItems === order.id && (
                          <tr
                            id={`order-items-${order.id}`}
                            data-testid={`order-${order.id}-items`}
                            className="border-b bg-muted/40"
                          >
                            <td colSpan={8} className="px-2 py-2">
                              <div className="grid gap-2 sm:grid-cols-2">
                                <ul className="space-y-1 text-xs" aria-label="اقلام سفارش">
                                  {order.items.map((line, index) => (
                                    <li
                                      key={index}
                                      className="flex items-center justify-between gap-2 rounded border bg-background px-2 py-1"
                                    >
                                      <span>
                                        {line.product_name}
                                        {line.variant === "chain" ? " (زنجیر)" : ""}
                                        {!line.inventory_item_id && (
                                          <span className="ms-1 text-[10px] text-muted-foreground">
                                            بدون موجودی انبار
                                          </span>
                                        )}
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
                                      {line.notes && (
                                        <p
                                          className="w-full whitespace-pre-line text-[10px] text-muted-foreground"
                                          data-testid={`order-${order.id}-line-${index}-notes`}
                                        >
                                          {line.notes}
                                        </p>
                                      )}
                                      {(line.charges ?? []).length > 0 && (
                                        <ul
                                          className="w-full space-y-0.5 ps-3 text-[10px] text-muted-foreground"
                                          data-testid={`order-${order.id}-line-${index}-charges`}
                                          aria-label="هزینهٔ طراحی و متغیرها"
                                        >
                                          {(line.charges ?? []).map((charge) => (
                                            <li key={charge.id} className="flex justify-between">
                                              <span>
                                                {charge.name}
                                                {(charge.kind === "DESIGN" ||
                                                  charge.quantity != null) && (
                                                  <>
                                                    {" — "}
                                                    {charge.kind === "DESIGN"
                                                      ? `${faNumber(charge.hours)} ساعت`
                                                      : faNumber(charge.quantity ?? "0")}{" "}
                                                    ×{" "}
                                                    <Money
                                                      value={charge.rate}
                                                      currency="TOMAN"
                                                      hideCurrency
                                                    />
                                                  </>
                                                )}
                                              </span>
                                              <Money
                                                value={charge.amount}
                                                currency="TOMAN"
                                                hideCurrency
                                              />
                                            </li>
                                          ))}
                                        </ul>
                                      )}
                                    </li>
                                  ))}
                                </ul>
                                {(order.warnings ?? []).length > 0 && (
                                  <ul
                                    className="space-y-1 rounded-md bg-amber-50 px-2 py-1 text-[11px] text-amber-800 dark:bg-amber-900/30 dark:text-amber-200"
                                    data-testid={`order-${order.id}-warning`}
                                    aria-label="کمبود موجودی"
                                  >
                                    {(order.warnings ?? []).map((warning) => (
                                      <li key={warning}>{warning}</li>
                                    ))}
                                  </ul>
                                )}
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
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
        </TabsContent>
        <TabsContent value="form">
          <Card className="min-w-0">
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-base">
                {editing ? `ویرایش سفارش #${faNumber(String(editing.order_number))}` : "ثبت سفارش"}
              </CardTitle>
              {editing && <Badge variant="secondary">تأییدنشده — قابل ویرایش</Badge>}
            </CardHeader>
            <CardContent className="space-y-3">
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
                <Label className="text-xs">نام مشتری</Label>
                <Input
                  data-testid="order-customer"
                  value={form.customer_name}
                  onChange={(e) => setForm((f) => ({ ...f, customer_name: e.target.value }))}
                />
              </div>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                <div>
                  <Label className="text-xs">تلفن</Label>
                  <Input
                    className="num"
                    data-testid="order-phone"
                    value={form.customer_phone}
                    onChange={(e) => setForm((f) => ({ ...f, customer_phone: e.target.value }))}
                  />
                </div>
                <div>
                  <Label className="text-xs">آدرس</Label>
                  <Input
                    data-testid="order-address"
                    value={form.customer_address}
                    onChange={(e) => setForm((f) => ({ ...f, customer_address: e.target.value }))}
                  />
                </div>
              </div>
              <div>
                <Label className="text-xs">یادداشت سفارش</Label>
                <Input
                  data-testid="order-notes"
                  value={form.notes}
                  placeholder="مثلاً رنگ، بسته‌بندی یا زمان تحویل"
                  onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
                />
              </div>

              <div className="space-y-2 rounded-md border p-2">
                <div className="flex items-center justify-between">
                  <p className="text-xs font-medium">اقلام سفارش</p>
                  <p className="text-xs text-muted-foreground">
                    نام کالا را بنویسید؛ اگر در انبار موجود است از فهرست هم می‌توانید انتخاب کنید.
                    کالای بدون موجودی مستقیم به خط تولید می‌رود.
                  </p>
                </div>
                <QueryNotice query={warehouseQuery} />
                {warehouseQuery.isSuccess && orderable.length === 0 && (
                  <p className="rounded-md bg-muted px-2 py-1 text-xs" role="status">
                    انبار خالی است؛ نام کالا را دستی بنویسید و قیمت هر عدد را وارد کنید. لازم نیست
                    اول محصول را در انبار بسازید.
                  </p>
                )}
                {form.items.map((line, index) => (
                  <div
                    key={index}
                    className="space-y-1 rounded-md border-b bg-background/40 p-2 pb-2 last:border-0"
                    data-testid={`line-${index}`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-[11px] text-muted-foreground">
                        ردیف <span className="num">{faNumber(String(index + 1))}</span>
                      </span>
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        className="h-6 px-2 text-[11px] text-destructive hover:bg-destructive/10"
                        aria-label={`حذف ردیف ${faNumber(String(index + 1))}`}
                        data-testid={`line-remove-${index}`}
                        disabled={form.items.length === 1 && !lineReady(line)}
                        title="حذف این ردیف"
                        onClick={() => removeLine(index)}
                      >
                        حذف ردیف
                      </Button>
                    </div>
                    <div className="grid grid-cols-2 gap-1">
                      <Input
                        className="h-8 text-xs"
                        aria-label={`نام کالای ردیف ${faNumber(String(index + 1))}`}
                        data-testid={`line-name-${index}`}
                        placeholder="نام کالا"
                        value={line.product_name}
                        onChange={(e) => {
                          const name = e.target.value;
                          const item = productById.get(line.inventory_item_id);
                          // Typing a new name means the line is no longer that item.
                          updateLine(
                            index,
                            item && item.name !== name
                              ? { product_name: name, inventory_item_id: "" }
                              : { product_name: name },
                          );
                        }}
                      />
                      <select
                        aria-label={`محصول انبار برای ردیف ${faNumber(String(index + 1))}`}
                        data-testid={`line-product-${index}`}
                        className="flex h-8 w-full rounded-md border border-input bg-background px-2 text-xs text-foreground"
                        value={line.inventory_item_id}
                        onChange={(e) => pickProduct(index, e.target.value)}
                      >
                        <option value="">— بدون موجودی در انبار —</option>
                        {orderable.map((item) => (
                          <option key={item.id} value={item.id}>
                            {item.name} ({faNumber(item.quantity)} عدد موجود)
                          </option>
                        ))}
                      </select>
                      <select
                        aria-label={`نوع ردیف ${faNumber(String(index + 1))}`}
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
                    <div className="grid grid-cols-3 gap-1">
                      <Input
                        className="num h-8 text-xs"
                        aria-label={`تعداد ردیف ${faNumber(String(index + 1))}`}
                        data-testid={`line-quantity-${index}`}
                        placeholder="تعداد"
                        value={line.quantity}
                        onChange={(e) => updateLine(index, { quantity: e.target.value })}
                      />
                      <Input
                        className="num h-8 text-xs"
                        aria-label={`قیمت واحد ردیف ${faNumber(String(index + 1))}`}
                        data-testid={`line-price-${index}`}
                        placeholder="قیمت واحد (از انبار)"
                        value={line.unit_price}
                        onChange={(e) => updateLine(index, { unit_price: e.target.value })}
                      />
                      <Input
                        className="num h-8 text-xs"
                        aria-label={`بهای تمام‌شده ردیف ${faNumber(String(index + 1))}`}
                        data-testid={`line-cost-${index}`}
                        placeholder="بهای تمام‌شده (اختیاری)"
                        value={line.unit_cost}
                        onChange={(e) => updateLine(index, { unit_cost: e.target.value })}
                      />
                    </div>
                    <Link
                      to="/price-calc"
                      data-testid={`line-pricing-${index}`}
                      className="inline-block text-xs text-primary underline"
                      onClick={(event) => {
                        try {
                          writeTransfer({ form, editing, lineIndex: index });
                        } catch {
                          event.preventDefault();
                          setMessage(
                            "ذخیرهٔ موقت فرم ممکن نیست؛ دسترسی مرورگر به حافظه را فعال کنید.",
                          );
                        }
                      }}
                    >
                      محاسبهٔ قیمت این ردیف
                    </Link>
                    {line.notes && (
                      <p
                        className="whitespace-pre-line rounded border bg-muted/40 p-2 text-xs text-muted-foreground"
                        data-testid={`line-pricing-details-${index}`}
                      >
                        {line.notes}
                      </p>
                    )}
                    <div
                      className="space-y-1 rounded-md border border-dashed p-1.5"
                      data-testid={`line-charges-${index}`}
                    >
                      {line.charges.map((charge, chargeIndex) => (
                        <div
                          key={`${charge.kind}-${chargeIndex}`}
                          className="flex items-center gap-1 text-[11px]"
                        >
                          <span className="min-w-0 flex-1 truncate">
                            {charge.kind === "DESIGN" ? "هزینه طراحی" : charge.name}
                            {charge.kind === "VARIABLE" && !charge.legacy && (
                              <span className="ms-1 text-[10px] text-muted-foreground">
                                (هر واحد{" "}
                                <Money
                                  value={
                                    charge.rate ??
                                    variables.find((v) => v.id === charge.variable_id)?.value ??
                                    "0"
                                  }
                                  currency="TOMAN"
                                  hideCurrency
                                />
                                )
                              </span>
                            )}
                            {charge.kind === "DESIGN" && (charge.rate != null || designRate) && (
                              <span className="ms-1 text-[10px] text-muted-foreground">
                                (هر ساعت{" "}
                                <Money
                                  value={charge.rate ?? designRate?.value ?? "0"}
                                  currency="TOMAN"
                                  hideCurrency
                                />
                                )
                              </span>
                            )}
                          </span>
                          <Input
                            className="num h-7 w-16 text-xs"
                            aria-label={
                              charge.kind === "DESIGN"
                                ? `ساعت طراحی ردیف ${faNumber(String(index + 1))}`
                                : `${charge.legacy ? (charge.name.startsWith(CALCULATED_CHARGE_PREFIX) ? "مبلغ یک‌باره" : "مبلغ قبلی") : "مقدار"} ${charge.name} ردیف ${faNumber(String(index + 1))}`
                            }
                            data-testid={
                              charge.kind === "DESIGN"
                                ? `line-design-hours-${index}`
                                : `line-variable-amount-${index}-${chargeIndex}`
                            }
                            inputMode="decimal"
                            placeholder={
                              charge.kind === "DESIGN"
                                ? "ساعت"
                                : charge.legacy
                                  ? "مبلغ قبلی"
                                  : "مقدار"
                            }
                            value={
                              charge.kind === "DESIGN"
                                ? charge.hours
                                : charge.legacy
                                  ? charge.amount
                                  : (charge.quantity ?? "")
                            }
                            onChange={(e) =>
                              updateCharge(
                                index,
                                chargeIndex,
                                charge.kind === "DESIGN"
                                  ? { hours: e.target.value }
                                  : charge.legacy
                                    ? { amount: e.target.value }
                                    : { quantity: e.target.value },
                              )
                            }
                          />
                          <span className="num w-20 shrink-0 text-xs">
                            <Money
                              value={chargeAmount(charge).toFixed(4)}
                              currency="TOMAN"
                              hideCurrency
                            />
                          </span>
                          <button
                            type="button"
                            className="text-destructive"
                            aria-label={`حذف ${charge.name}`}
                            data-testid={`line-charge-remove-${index}-${chargeIndex}`}
                            onClick={() => removeCharge(index, chargeIndex)}
                          >
                            ×
                          </button>
                        </div>
                      ))}
                      <div className="flex flex-wrap items-center gap-1">
                        {designRate && !line.charges.some((charge) => charge.kind === "DESIGN") && (
                          <Button
                            size="sm"
                            variant="ghost"
                            className="h-6 px-2 text-[11px]"
                            data-testid={`line-design-add-${index}`}
                            onClick={() =>
                              addCharge(index, {
                                kind: "DESIGN",
                                variable_id: designRate.id,
                                name: "هزینه طراحی",
                                hours: "",
                                amount: "",
                              })
                            }
                          >
                            + ساعت طراحی
                          </Button>
                        )}
                        <select
                          aria-label={`افزودن متغیر به ردیف ${faNumber(String(index + 1))}`}
                          data-testid={`line-variable-add-${index}`}
                          className="h-6 rounded-md border border-input bg-background px-1 text-[11px] text-foreground"
                          value=""
                          onChange={(e) => {
                            const variable = variables.find((row) => row.id === e.target.value);
                            if (!variable) return;
                            addCharge(index, {
                              kind: "VARIABLE",
                              variable_id: variable.id,
                              name: variable.name,
                              hours: "",
                              quantity: "",
                              amount: "",
                            });
                          }}
                        >
                          <option value="">+ افزودن متغیر</option>
                          {variables
                            .filter((variable) => variable.basis === "AMOUNT")
                            .map((variable) => (
                              <option key={variable.id} value={variable.id}>
                                {variable.name}
                              </option>
                            ))}
                        </select>
                        {variables.some((v) => v.basis !== "AMOUNT") && (
                          <span className="text-[10px] text-muted-foreground">
                            فقط متغیرهای مبلغی قابل افزودن هستند.
                          </span>
                        )}
                        {!designRate && variables.length > 0 && (
                          <span className="text-[10px] text-muted-foreground">
                            برای «هزینهٔ طراحی»، در تنظیمات قیمت‌گذاری یکی از متغیرها را نرخ هر ساعت
                            طراحی کنید.
                          </span>
                        )}
                      </div>
                    </div>
                    {lineShortage(line) && (
                      <p
                        className="text-xs text-amber-700 dark:text-amber-400"
                        data-testid={`line-warning-${index}`}
                      >
                        {lineShortage(line)}
                      </p>
                    )}
                  </div>
                ))}
                <div className="flex items-center justify-between">
                  <Button
                    size="sm"
                    variant="ghost"
                    data-testid="line-add"
                    onClick={() => setForm((f) => ({ ...f, items: [...f.items, emptyLine()] }))}
                  >
                    + افزودن قلم
                  </Button>
                  <span className="text-sm">
                    جمع اقلام و هزینه‌ها: <Money value={formSubtotal.toFixed(4)} currency="TOMAN" />
                  </span>
                </div>
              </div>

              <div className="space-y-2 rounded-md border p-3" data-testid="order-discount">
                <p className="text-sm font-medium">تخفیف کل سفارش</p>
                <p className="text-xs text-muted-foreground">
                  تخفیف از جمع اقلام، هزینهٔ طراحی و متغیرها کسر می‌شود.
                </p>
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  <div>
                    <Label htmlFor="order-discount-type" className="text-xs">
                      نوع تخفیف
                    </Label>
                    <select
                      id="order-discount-type"
                      data-testid="order-discount-type"
                      className="flex h-9 w-full rounded-md border border-input bg-background px-2 text-sm text-foreground"
                      value={form.discount_type}
                      onChange={(e) =>
                        setForm((f) => ({
                          ...f,
                          discount_type: e.target.value as "AMOUNT" | "PERCENT",
                          discount_value: "",
                        }))
                      }
                    >
                      <option value="AMOUNT">مبلغ (تومان)</option>
                      <option value="PERCENT">درصد</option>
                    </select>
                  </div>
                  <div>
                    <Label htmlFor="order-discount-value" className="text-xs">
                      {form.discount_type === "PERCENT" ? "درصد تخفیف" : "مبلغ تخفیف (تومان)"}
                    </Label>
                    <Input
                      id="order-discount-value"
                      data-testid="order-discount-value"
                      className="num"
                      inputMode="decimal"
                      placeholder="۰"
                      value={form.discount_value}
                      aria-invalid={Boolean(discount.error)}
                      onChange={(e) => setForm((f) => ({ ...f, discount_value: e.target.value }))}
                    />
                  </div>
                </div>
                {discount.error && (
                  <p
                    role="alert"
                    className="text-xs text-destructive"
                    data-testid="order-discount-error"
                  >
                    {discount.error}
                  </p>
                )}
                <div className="flex flex-wrap justify-between gap-2 text-xs">
                  <span>جمع قبل از تخفیف</span>
                  <Money value={formSubtotal.toFixed(4)} currency="TOMAN" />
                </div>
                <div className="flex flex-wrap justify-between gap-2 text-xs">
                  <span>مبلغ تخفیف</span>
                  <Money value={discount.amount.toFixed(4)} currency="TOMAN" />
                </div>
                <div
                  className="flex flex-wrap justify-between gap-2 text-sm font-semibold"
                  data-testid="order-final-total"
                >
                  <span>مبلغ قابل پرداخت</span>
                  <Money value={formTotal.toFixed(4)} currency="TOMAN" />
                </div>
              </div>

              {createWarnings.length > 0 && (
                <ul
                  className="space-y-1 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:bg-amber-900/30 dark:text-amber-200"
                  data-testid="order-warnings"
                >
                  {createWarnings.map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              )}

              <div className="flex flex-wrap gap-2">
                <Button
                  className="flex-1"
                  data-testid="order-submit"
                  disabled={
                    (editing ? saveOrder.isPending : createOrder.isPending) ||
                    Boolean(discount.error) ||
                    !form.customer_name.trim() ||
                    !calendarReady ||
                    !validIso(form.order_date) ||
                    !form.items.length ||
                    form.items.some((line) => !lineReady(line))
                  }
                  onClick={() => {
                    setCreateWarnings([]);
                    if (editing) saveOrder.mutate();
                    else createOrder.mutate();
                  }}
                >
                  {editing ? "ذخیرهٔ تغییرات" : "ثبت سفارش"}
                </Button>
                {editing && (
                  <Button variant="outline" data-testid="order-edit-cancel" onClick={cancelEditing}>
                    انصراف از ویرایش
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

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
