/**
 * انبار — warehouse of filaments and produced models (MASTER_PROMPT §3.1).
 *
 * Tabs: کالاها (items + stock movements), هشدارها (stockout alarm + suggested
 * supplier), تأمین‌کنندگان (scores of price/quality/delivery), گردش انبار
 * (append-only movement ledger). Quantities use the shared decimal helpers;
 * money is rendered through <Money currency="TOMAN" />.
 */
import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, parseError } from "@/api/client";
import { OperationPagination, OPERATION_PAGE_SIZE } from "@/components/operation-pagination";
import { QueryNotice } from "@/components/query-notice";
import { parseNum } from "@/lib/priceCalc";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Money } from "@/components/money";
import { faNumber } from "@/lib/fa";

type Item = {
  id: string;
  name: string;
  kind: "FILAMENT" | "PRODUCT";
  color: string | null;
  unit: "G" | "PCS";
  quantity: string;
  min_quantity: string;
  unit_price: string;
  supplier_id: string | null;
  supplier_name: string | null;
  purchased_at: string | null;
  is_active: boolean;
  version_id: number;
  low_stock: boolean;
  value: string;
};

type Supplier = {
  id: string;
  name: string;
  address: string | null;
  phone: string | null;
  score_price: number;
  score_quality: number;
  score_delivery: number;
  score: number;
  is_active: boolean;
  version_id: number;
};

type Alarm = {
  item_id: string;
  name: string;
  kind: "FILAMENT" | "PRODUCT";
  quantity: string;
  min_quantity: string;
  unit: "G" | "PCS";
  suggested_supplier: string | null;
};

type Movement = {
  id: string;
  item_name: string;
  kind: "IN" | "OUT" | "ADJUST";
  quantity: string;
  reason: string | null;
  note: string | null;
  occurred_at: string;
  created_at: string;
};

type Summary = {
  filament_count: number;
  product_count: number;
  total_value: string;
  low_stock_count: number;
  items: Item[];
};

const KIND_LABEL: Record<string, string> = { FILAMENT: "فیلامنت", PRODUCT: "محصول" };
const UNIT_LABEL: Record<string, string> = { G: "گرم", PCS: "عدد" };
const MOVEMENT_LABEL: Record<string, string> = {
  IN: "ورود",
  OUT: "خروج",
  ADJUST: "شمارش",
};

function errText(error: unknown): string {
  if (error instanceof Error) return error.message;
  return "خطای نامشخص";
}

export function WarehousePage(): React.JSX.Element {
  const queryClient = useQueryClient();
  const [search, setSearch] = React.useState("");
  const [kindFilter, setKindFilter] = React.useState<"" | "FILAMENT" | "PRODUCT">("");
  const [lowOnly, setLowOnly] = React.useState(false);
  const [moveFor, setMoveFor] = React.useState<Item | null>(null);
  const [moveKind, setMoveKind] = React.useState<"IN" | "OUT" | "ADJUST">("IN");
  const [moveQty, setMoveQty] = React.useState("");
  const [newItem, setNewItem] = React.useState({
    name: "",
    kind: "FILAMENT" as "FILAMENT" | "PRODUCT",
    color: "",
    unit: "G" as "G" | "PCS",
    quantity: "",
    min_quantity: "0",
    unit_price: "",
    supplier_id: "",
  });
  const [newSupplier, setNewSupplier] = React.useState({
    name: "",
    address: "",
    phone: "",
    score_price: "50",
    score_quality: "50",
    score_delivery: "50",
  });
  const [movementPage, setMovementPage] = React.useState(0);
  const [message, setMessage] = React.useState<string | null>(null);

  const summaryQuery = useQuery({
    queryKey: ["warehouse", "summary"],
    queryFn: async () => {
      const res = await api.GET("/api/v1/warehouse/summary");
      if (res.error) throw await parseError(res.response);
      return res.data as unknown as Summary;
    },
  });

  const alarmsQuery = useQuery({
    queryKey: ["warehouse", "alarms"],
    queryFn: async () => {
      const res = await api.GET("/api/v1/warehouse/alarms");
      if (res.error) throw await parseError(res.response);
      return res.data as unknown as Alarm[];
    },
  });

  const suppliersQuery = useQuery({
    queryKey: ["warehouse", "suppliers"],
    queryFn: async () => {
      const res = await api.GET("/api/v1/warehouse/suppliers", {
        params: { query: {} },
      });
      if (res.error) throw await parseError(res.response);
      return res.data as unknown as Supplier[];
    },
  });

  const movementsQuery = useQuery({
    queryKey: ["warehouse", "movements", movementPage],
    queryFn: async () => {
      const res = await api.GET("/api/v1/warehouse/movements", {
        params: {
          query: { offset: movementPage * OPERATION_PAGE_SIZE, limit: OPERATION_PAGE_SIZE + 1 },
        },
      });
      if (res.error) throw await parseError(res.response);
      return res.data as unknown as Movement[];
    },
  });

  const invalidate = (): void => {
    void queryClient.invalidateQueries({ queryKey: ["warehouse"] });
    void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
  };

  const createItem = useMutation({
    mutationFn: async () => {
      const res = await api.POST("/api/v1/warehouse/items", {
        body: {
          name: newItem.name,
          kind: newItem.kind,
          color: newItem.color || null,
          unit: newItem.unit,
          quantity: parseNum(newItem.quantity || "0").toString(),
          min_quantity: parseNum(newItem.min_quantity || "0").toString(),
          unit_price: parseNum(newItem.unit_price || "0").toString(),
          supplier_id: newItem.supplier_id || null,
        },
      });
      if (res.error) throw await parseError(res.response);
      return res.data;
    },
    onSuccess: () => {
      setNewItem({
        name: "",
        kind: "FILAMENT",
        color: "",
        unit: "G",
        quantity: "",
        min_quantity: "0",
        unit_price: "",
        supplier_id: "",
      });
      setMessage("کالا ثبت شد ✓");
      invalidate();
    },
    onError: (e) => setMessage(errText(e)),
  });

  const createSupplier = useMutation({
    mutationFn: async () => {
      const res = await api.POST("/api/v1/warehouse/suppliers", {
        body: {
          name: newSupplier.name,
          address: newSupplier.address || null,
          phone: newSupplier.phone || null,
          score_price: Number(newSupplier.score_price),
          score_quality: Number(newSupplier.score_quality),
          score_delivery: Number(newSupplier.score_delivery),
        },
      });
      if (res.error) throw await parseError(res.response);
      return res.data;
    },
    onSuccess: () => {
      setNewSupplier({
        name: "",
        address: "",
        phone: "",
        score_price: "50",
        score_quality: "50",
        score_delivery: "50",
      });
      setMessage("تأمین‌کننده ثبت شد ✓");
      invalidate();
    },
    onError: (e) => setMessage(errText(e)),
  });

  const moveStock = useMutation({
    mutationFn: async () => {
      if (!moveFor) throw new Error("کالا انتخاب نشده است");
      const res = await api.POST("/api/v1/warehouse/items/{item_id}/movements", {
        params: { path: { item_id: moveFor.id } },
        body: { kind: moveKind, quantity: parseNum(moveQty || "0").toString(), reason: "manual" },
      });
      if (res.error) throw await parseError(res.response);
      return res.data;
    },
    onSuccess: () => {
      setMoveFor(null);
      setMoveQty("");
      setMessage("گردش انبار ثبت شد ✓");
      invalidate();
    },
    onError: (e) => setMessage(errText(e)),
  });

  const items = React.useMemo(
    () => (summaryQuery.isSuccess ? summaryQuery.data.items : []),
    [summaryQuery.data, summaryQuery.isSuccess],
  );
  const filtered = React.useMemo(
    () =>
      items.filter(
        (i) =>
          (!kindFilter || i.kind === kindFilter) &&
          (!lowOnly || i.low_stock) &&
          (!search.trim() ||
            i.name.includes(search.trim()) ||
            (i.color ?? "").includes(search.trim())),
      ),
    [items, kindFilter, lowOnly, search],
  );

  return (
    <div className="space-y-6" dir="rtl">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-bold">انبار</h1>
        <div className="flex flex-wrap gap-2 text-sm">
          <QueryNotice query={summaryQuery} />
          {summaryQuery.isSuccess && (
            <>
              <Badge variant="secondary">
                فیلامنت: {faNumber(String(summaryQuery.data?.filament_count ?? 0))}
              </Badge>
              <Badge variant="secondary">
                محصول: {faNumber(String(summaryQuery.data?.product_count ?? 0))}
              </Badge>
              <Badge
                variant={
                  !alarmsQuery.isSuccess
                    ? "outline"
                    : alarmsQuery.data?.length
                      ? "destructive"
                      : "success"
                }
              >
                هشدار موجودی:{" "}
                {alarmsQuery.isSuccess ? faNumber(String(alarmsQuery.data.length)) : "نامشخص"}
              </Badge>
              <Badge variant="outline">
                ارزش انبار: <Money value={summaryQuery.data?.total_value ?? "0"} currency="TOMAN" />
              </Badge>
            </>
          )}
        </div>
      </div>

      {message && (
        <p className="rounded-md bg-muted px-3 py-2 text-sm" data-testid="warehouse-message">
          {message}
        </p>
      )}

      <Tabs defaultValue="items">
        <TabsList>
          <TabsTrigger value="items">کالاها</TabsTrigger>
          <TabsTrigger value="alarms">
            هشدارها
            {(alarmsQuery.data?.length ?? 0) > 0
              ? ` (${faNumber(String(alarmsQuery.data?.length ?? 0))})`
              : ""}
          </TabsTrigger>
          <TabsTrigger value="suppliers">تأمین‌کنندگان</TabsTrigger>
          <TabsTrigger value="movements">گردش انبار</TabsTrigger>
        </TabsList>

        {/* ----------------------------------------------------------- items */}
        <TabsContent value="items">
          <div className="grid gap-4 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <CardHeader>
                <CardTitle className="text-base">کالاهای انبار</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <QueryNotice query={summaryQuery} />
                <div className="flex flex-wrap items-end gap-2">
                  <div className="w-48">
                    <Label className="text-xs">جستجو</Label>
                    <Input
                      data-testid="warehouse-search"
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                      placeholder="نام یا رنگ…"
                    />
                  </div>
                  <div className="w-36">
                    <Label className="text-xs">نوع</Label>
                    <select
                      className="flex h-9 w-full rounded-md border border-input bg-background px-2 text-sm text-foreground"
                      value={kindFilter}
                      onChange={(e) => setKindFilter(e.target.value as typeof kindFilter)}
                    >
                      <option value="">همه</option>
                      <option value="FILAMENT">فیلامنت</option>
                      <option value="PRODUCT">محصول</option>
                    </select>
                  </div>
                  <Label className="flex items-center gap-2 pb-2 text-xs">
                    <input
                      type="checkbox"
                      data-testid="low-only"
                      checked={lowOnly}
                      onChange={(e) => setLowOnly(e.target.checked)}
                    />
                    فقط کمبود موجودی
                  </Label>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-muted-foreground">
                        <th className="py-2 text-start font-medium">نام</th>
                        <th className="py-2 text-start font-medium">نوع</th>
                        <th className="py-2 text-start font-medium">رنگ</th>
                        <th className="py-2 text-start font-medium">موجودی</th>
                        <th className="py-2 text-start font-medium">حداقل</th>
                        <th className="py-2 text-start font-medium">قیمت واحد</th>
                        <th className="py-2 text-start font-medium">ارزش</th>
                        <th className="py-2 text-start font-medium">تأمین‌کننده</th>
                        <th className="py-2 text-start font-medium" />
                      </tr>
                    </thead>
                    <tbody>
                      {filtered.map((item) => (
                        <tr key={item.id} className="border-b" data-testid={`item-${item.id}`}>
                          <td className="py-2">
                            {item.name}{" "}
                            {item.low_stock && <Badge variant="destructive">کمبود</Badge>}
                          </td>
                          <td className="py-2">{KIND_LABEL[item.kind]}</td>
                          <td className="py-2">{item.color ?? "—"}</td>
                          <td className="py-2">
                            <span className="num">{faNumber(item.quantity)}</span>{" "}
                            <span className="text-xs text-muted-foreground">
                              {UNIT_LABEL[item.unit]}
                            </span>
                          </td>
                          <td className="num py-2 text-muted-foreground">
                            {faNumber(item.min_quantity)}
                          </td>
                          <td className="py-2">
                            <Money value={item.unit_price} currency="TOMAN" />
                          </td>
                          <td className="py-2">
                            <Money value={item.value} currency="TOMAN" />
                          </td>
                          <td className="py-2">{item.supplier_name ?? "—"}</td>
                          <td className="py-2 text-end">
                            <Button
                              size="sm"
                              variant="outline"
                              data-testid={`move-${item.id}`}
                              onClick={() => {
                                setMoveFor(item);
                                setMoveKind("IN");
                                setMoveQty("");
                              }}
                            >
                              گردش
                            </Button>
                          </td>
                        </tr>
                      ))}
                      {summaryQuery.isSuccess && filtered.length === 0 && (
                        <tr>
                          <td colSpan={9} className="py-6 text-center text-muted-foreground">
                            کالایی یافت نشد.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>

                {moveFor && (
                  <div className="rounded-md border p-3" data-testid="movement-form">
                    <p className="pb-2 text-sm font-medium">
                      گردش انبار — {moveFor.name} (موجودی فعلی:{" "}
                      <span className="num">{faNumber(moveFor.quantity)}</span>{" "}
                      {UNIT_LABEL[moveFor.unit]})
                    </p>
                    <div className="flex flex-wrap items-end gap-2">
                      <div className="w-32">
                        <Label className="text-xs">نوع</Label>
                        <select
                          className="flex h-9 w-full rounded-md border border-input bg-background px-2 text-sm text-foreground"
                          value={moveKind}
                          onChange={(e) => setMoveKind(e.target.value as typeof moveKind)}
                        >
                          <option value="IN">ورود</option>
                          <option value="OUT">خروج</option>
                          <option value="ADJUST">شمارش (تعیین موجودی)</option>
                        </select>
                      </div>
                      <div className="w-32">
                        <Label className="text-xs">مقدار</Label>
                        <Input
                          className="num"
                          data-testid="movement-qty"
                          value={moveQty}
                          onChange={(e) => setMoveQty(e.target.value)}
                        />
                      </div>
                      <Button
                        data-testid="movement-submit"
                        onClick={() => moveStock.mutate()}
                        disabled={moveStock.isPending}
                      >
                        ثبت
                      </Button>
                      <Button variant="ghost" onClick={() => setMoveFor(null)}>
                        انصراف
                      </Button>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">ثبت کالای جدید</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div>
                  <Label className="text-xs">نام</Label>
                  <Input
                    data-testid="new-item-name"
                    value={newItem.name}
                    onChange={(e) => setNewItem((v) => ({ ...v, name: e.target.value }))}
                  />
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <Label className="text-xs">نوع</Label>
                    <select
                      className="flex h-9 w-full rounded-md border border-input bg-background px-2 text-sm text-foreground"
                      value={newItem.kind}
                      data-testid="new-item-kind"
                      onChange={(e) =>
                        setNewItem((v) => ({
                          ...v,
                          kind: e.target.value as "FILAMENT" | "PRODUCT",
                          unit: e.target.value === "FILAMENT" ? "G" : "PCS",
                        }))
                      }
                    >
                      <option value="FILAMENT">فیلامنت</option>
                      <option value="PRODUCT">محصول</option>
                    </select>
                  </div>
                  <div>
                    <Label className="text-xs">واحد</Label>
                    <select
                      className="flex h-9 w-full rounded-md border border-input bg-background px-2 text-sm text-foreground"
                      value={newItem.unit}
                      onChange={(e) =>
                        setNewItem((v) => ({ ...v, unit: e.target.value as "G" | "PCS" }))
                      }
                    >
                      <option value="G">گرم</option>
                      <option value="PCS">عدد</option>
                    </select>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <Label className="text-xs">رنگ</Label>
                    <Input
                      value={newItem.color}
                      onChange={(e) => setNewItem((v) => ({ ...v, color: e.target.value }))}
                    />
                  </div>
                  <div>
                    <Label className="text-xs">تأمین‌کننده</Label>
                    <select
                      className="flex h-9 w-full rounded-md border border-input bg-background px-2 text-sm text-foreground"
                      value={newItem.supplier_id}
                      onChange={(e) => setNewItem((v) => ({ ...v, supplier_id: e.target.value }))}
                    >
                      <option value="">—</option>
                      {(suppliersQuery.isSuccess ? suppliersQuery.data : []).map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.name}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <div>
                    <Label className="text-xs">موجودی اولیه</Label>
                    <Input
                      className="num"
                      data-testid="new-item-quantity"
                      value={newItem.quantity}
                      onChange={(e) => setNewItem((v) => ({ ...v, quantity: e.target.value }))}
                    />
                  </div>
                  <div>
                    <Label className="text-xs">حداقل</Label>
                    <Input
                      className="num"
                      value={newItem.min_quantity}
                      data-testid="new-item-min"
                      onChange={(e) => setNewItem((v) => ({ ...v, min_quantity: e.target.value }))}
                    />
                  </div>
                  <div>
                    <Label className="text-xs">قیمت واحد</Label>
                    <Input
                      className="num"
                      value={newItem.unit_price}
                      data-testid="new-item-price"
                      onChange={(e) => setNewItem((v) => ({ ...v, unit_price: e.target.value }))}
                    />
                  </div>
                </div>
                <Button
                  className="w-full"
                  data-testid="new-item-submit"
                  onClick={() => createItem.mutate()}
                  disabled={createItem.isPending || !newItem.name.trim()}
                >
                  ثبت کالا
                </Button>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* ---------------------------------------------------------- alarms */}
        <TabsContent value="alarms">
          <QueryNotice query={alarmsQuery} />
          <Card>
            <CardHeader>
              <CardTitle className="text-base">هشدار کمبود موجودی</CardTitle>
            </CardHeader>
            <CardContent>
              {(alarmsQuery.data ?? []).length === 0 ? (
                <p className="py-4 text-sm text-muted-foreground">
                  موجودی همهٔ کالاها بالای حداقل است ✓
                </p>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-muted-foreground">
                      <th className="py-2 text-start font-medium">کالا</th>
                      <th className="py-2 text-start font-medium">موجودی</th>
                      <th className="py-2 text-start font-medium">حداقل</th>
                      <th className="py-2 text-start font-medium">پیشنهاد خرید از</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(alarmsQuery.isSuccess ? alarmsQuery.data : []).map((a) => (
                      <tr key={a.item_id} className="border-b" data-testid={`alarm-${a.item_id}`}>
                        <td className="py-2">
                          {a.name} <Badge variant="secondary">{KIND_LABEL[a.kind]}</Badge>
                        </td>
                        <td className="num py-2 text-destructive">{faNumber(a.quantity)}</td>
                        <td className="num py-2">{faNumber(a.min_quantity)}</td>
                        <td className="py-2">{a.suggested_supplier ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ------------------------------------------------------- suppliers */}
        <TabsContent value="suppliers">
          <QueryNotice query={suppliersQuery} />
          <div className="grid gap-4 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <CardHeader>
                <CardTitle className="text-base">
                  تأمین‌کنندگان — امتیاز قیمت/کیفیت/زمان تحویل
                </CardTitle>
              </CardHeader>
              <CardContent>
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-muted-foreground">
                      <th className="py-2 text-start font-medium">نام</th>
                      <th className="py-2 text-start font-medium">قیمت</th>
                      <th className="py-2 text-start font-medium">کیفیت</th>
                      <th className="py-2 text-start font-medium">تحویل</th>
                      <th className="py-2 text-start font-medium">امتیاز کل</th>
                      <th className="py-2 text-start font-medium">تماس</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...(suppliersQuery.data ?? [])]
                      .sort((a, b) => b.score - a.score)
                      .map((s) => (
                        <tr key={s.id} className="border-b" data-testid={`supplier-${s.id}`}>
                          <td className="py-2">{s.name}</td>
                          <td className="num py-2">{faNumber(String(s.score_price))}</td>
                          <td className="num py-2">{faNumber(String(s.score_quality))}</td>
                          <td className="num py-2">{faNumber(String(s.score_delivery))}</td>
                          <td className="py-2">
                            <Badge variant={s.score >= 70 ? "success" : "secondary"}>
                              {faNumber(String(s.score))}
                            </Badge>
                          </td>
                          <td className="py-2 text-xs text-muted-foreground">{s.phone ?? "—"}</td>
                        </tr>
                      ))}
                    {suppliersQuery.isSuccess && suppliersQuery.data.length === 0 && (
                      <tr>
                        <td colSpan={6} className="py-6 text-center text-muted-foreground">
                          تأمین‌کننده‌ای ثبت نشده است.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">ثبت تأمین‌کننده</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div>
                  <Label className="text-xs">نام</Label>
                  <Input
                    data-testid="new-supplier-name"
                    value={newSupplier.name}
                    onChange={(e) => setNewSupplier((v) => ({ ...v, name: e.target.value }))}
                  />
                </div>
                <div>
                  <Label className="text-xs">آدرس</Label>
                  <Input
                    value={newSupplier.address}
                    onChange={(e) => setNewSupplier((v) => ({ ...v, address: e.target.value }))}
                  />
                </div>
                <div>
                  <Label className="text-xs">تلفن</Label>
                  <Input
                    value={newSupplier.phone}
                    onChange={(e) => setNewSupplier((v) => ({ ...v, phone: e.target.value }))}
                  />
                </div>
                <div className="grid grid-cols-3 gap-2">
                  {(
                    [
                      ["score_price", "قیمت"],
                      ["score_quality", "کیفیت"],
                      ["score_delivery", "تحویل"],
                    ] as const
                  ).map(([key, label]) => (
                    <div key={key}>
                      <Label className="text-xs">{label}</Label>
                      <Input
                        className="num"
                        value={newSupplier[key]}
                        onChange={(e) => setNewSupplier((v) => ({ ...v, [key]: e.target.value }))}
                      />
                    </div>
                  ))}
                </div>
                <Button
                  className="w-full"
                  data-testid="new-supplier-submit"
                  onClick={() => createSupplier.mutate()}
                  disabled={createSupplier.isPending || !newSupplier.name.trim()}
                >
                  ثبت تأمین‌کننده
                </Button>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* ------------------------------------------------------- movements */}
        <TabsContent value="movements">
          <QueryNotice query={movementsQuery} />
          <Card>
            <CardHeader>
              <CardTitle className="text-base">گردش انبار (فقط افزودنی)</CardTitle>
            </CardHeader>
            <CardContent>
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-muted-foreground">
                    <th className="py-2 text-start font-medium">تاریخ</th>
                    <th className="py-2 text-start font-medium">کالا</th>
                    <th className="py-2 text-start font-medium">نوع</th>
                    <th className="py-2 text-start font-medium">مقدار</th>
                    <th className="py-2 text-start font-medium">علت</th>
                    <th className="py-2 text-start font-medium">توضیح</th>
                  </tr>
                </thead>
                <tbody>
                  {(movementsQuery.isSuccess
                    ? movementsQuery.data.slice(0, OPERATION_PAGE_SIZE)
                    : []
                  ).map((m) => (
                    <tr key={m.id} className="border-b">
                      <td className="num py-2">{m.occurred_at}</td>
                      <td className="py-2">{m.item_name}</td>
                      <td className="py-2">
                        <Badge variant={m.kind === "OUT" ? "warning" : "secondary"}>
                          {MOVEMENT_LABEL[m.kind]}
                        </Badge>
                      </td>
                      <td className="num py-2">{faNumber(m.quantity)}</td>
                      <td className="py-2">{m.reason ?? "—"}</td>
                      <td className="py-2 text-xs text-muted-foreground">{m.note ?? "—"}</td>
                    </tr>
                  ))}
                  {movementsQuery.isSuccess && movementsQuery.data.length === 0 && (
                    <tr>
                      <td colSpan={6} className="py-6 text-center text-muted-foreground">
                        گردشی ثبت نشده است.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
              <OperationPagination
                page={movementPage}
                next={movementsQuery.isSuccess && movementsQuery.data.length > OPERATION_PAGE_SIZE}
                busy={movementsQuery.isFetching}
                onChange={setMovementPage}
              />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
