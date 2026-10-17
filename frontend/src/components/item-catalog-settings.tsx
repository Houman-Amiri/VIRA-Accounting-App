import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, parseError } from "@/api/client";
import { useItemCatalog } from "@/lib/item-catalog";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Badge } from "./ui/badge";

type Category = "types" | "units" | "suppliers";
type Choice = { id: string; name: string; is_active: boolean; version_id: number };
const labels = { types: "نوع کالا", units: "واحد", suppliers: "تأمین‌کننده" };

function CatalogPanel({ category, canWrite }: { category: Category; canWrite: boolean }) {
  const types = useItemCatalog("types");
  const units = useItemCatalog("units");
  const suppliers = useQuery({
    queryKey: ["warehouse", "suppliers"],
    queryFn: async () => {
      const res = await api.GET("/api/v1/warehouse/suppliers");
      if (res.error) throw await parseError(res.response);
      return res.data!;
    },
  });
  const query = category === "types" ? types : category === "units" ? units : suppliers;
  const cache = useQueryClient();
  const [name, setName] = useState("");
  const [message, setMessage] = useState("");
  const [confirmation, setConfirmation] = useState<Choice | null>(null);
  const mutation = useMutation({
    mutationFn: async (operation: { action: "create" | "delete" | "activate"; row?: Choice }) => {
      const row = operation.row;
      if (operation.action === "create") {
        const res =
          category === "suppliers"
            ? await api.POST("/api/v1/warehouse/suppliers", {
                body: { name: name.trim(), score_price: 50, score_quality: 50, score_delivery: 50 },
              })
            : await api.POST("/api/v1/warehouse/catalog/{category}", {
                params: { path: { category } },
                body: { name: name.trim() },
              });
        if (res.error) throw await parseError(res.response);
        return "گزینه ثبت شد.";
      }
      if (!row) throw new Error("گزینه انتخاب نشده است.");
      if (operation.action === "delete") {
        const res =
          category === "suppliers"
            ? await api.DELETE("/api/v1/warehouse/suppliers/{supplier_id}", {
                params: { path: { supplier_id: row.id }, query: { version_id: row.version_id } },
              })
            : await api.DELETE("/api/v1/warehouse/catalog/{category}/{ident}", {
                params: {
                  path: { category, ident: row.id },
                  query: { version_id: row.version_id },
                },
              });
        if (res.error) throw await parseError(res.response);
        return res.data!.reason;
      }
      const res =
        category === "suppliers"
          ? await api.PATCH("/api/v1/warehouse/suppliers/{supplier_id}", {
              params: { path: { supplier_id: row.id } },
              body: { version_id: row.version_id, is_active: true },
            })
          : await api.PATCH("/api/v1/warehouse/catalog/{category}/{ident}", {
              params: { path: { category, ident: row.id } },
              body: { version_id: row.version_id, is_active: true },
            });
      if (res.error) throw await parseError(res.response);
      return "گزینه دوباره فعال شد.";
    },
    onMutate: () => setMessage(""),
    onSuccess: async (message, operation) => {
      setMessage(message);
      setConfirmation(null);
      if (operation.action === "create") setName("");
      await cache.invalidateQueries({ queryKey: ["warehouse"] });
      await cache.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (error) =>
      setMessage(error instanceof Error ? error.message : "ذخیره ناموفق بود؛ فهرست را تازه کنید."),
  });
  return (
    <section
      className="min-w-0 space-y-3 rounded-lg border p-3"
      aria-label={labels[category]}
      data-testid={`catalog-${category}`}
    >
      <h3 className="font-semibold">{labels[category]}</h3>
      {query.isPending ? (
        <p role="status">دریافت فهرست…</p>
      ) : query.error ? (
        <div role="alert">
          <p>دریافت فهرست ناموفق بود.</p>
          <Button variant="outline" onClick={() => void query.refetch()}>
            تلاش مجدد
          </Button>
        </div>
      ) : (
        <>
          <ul className="max-h-72 space-y-2 overflow-y-auto">
            {(query.data ?? []).map((row) => (
              <li
                key={row.id}
                className="flex flex-wrap items-center gap-2 rounded-md bg-muted/40 p-2 text-sm"
                data-testid={`catalog-row-${row.id}`}
              >
                <span className="min-w-0 flex-1 break-words">{row.name}</span>
                <Badge variant={row.is_active ? "success" : "secondary"}>
                  {row.is_active ? "فعال" : "غیرفعال"}
                </Badge>
                {row.is_active ? (
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={!canWrite || mutation.isPending}
                    aria-label={`حذف ${row.name}`}
                    onClick={() => {
                      setMessage("");
                      setConfirmation(row);
                    }}
                  >
                    حذف
                  </Button>
                ) : (
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={!canWrite || mutation.isPending}
                    aria-label={`فعال‌سازی ${row.name}`}
                    onClick={() => mutation.mutate({ action: "activate", row })}
                  >
                    فعال‌سازی مجدد
                  </Button>
                )}
              </li>
            ))}
          </ul>
          {confirmation && (
            <div
              role="alertdialog"
              aria-label={`تأیید حذف ${confirmation.name}`}
              className="space-y-2 rounded-md border border-destructive/50 p-3 text-sm"
            >
              <p>
                «{confirmation.name}» حذف شود؟ اگر استفاده شده باشد، برای حفظ سوابق فقط غیرفعال
                می‌شود؛ گزینه‌های پیش‌فرض نیز نگه‌داری می‌شوند.
              </p>
              <div className="flex gap-2">
                <Button
                  variant="destructive"
                  disabled={mutation.isPending || !canWrite}
                  onClick={() => mutation.mutate({ action: "delete", row: confirmation })}
                >
                  تأیید حذف
                </Button>
                <Button
                  variant="outline"
                  disabled={mutation.isPending}
                  onClick={() => setConfirmation(null)}
                >
                  انصراف
                </Button>
              </div>
            </div>
          )}
          <form
            className="flex flex-wrap items-end gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              mutation.mutate({ action: "create" });
            }}
          >
            <div className="min-w-0 flex-1">
              <Label htmlFor={`catalog-name-${category}`}>نام {labels[category]}</Label>
              <Input
                id={`catalog-name-${category}`}
                data-testid={`catalog-name-${category}`}
                maxLength={200}
                required
                disabled={!canWrite || mutation.isPending}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
            <Button
              variant="outline"
              type="submit"
              disabled={!canWrite || mutation.isPending || !name.trim()}
            >
              افزودن
            </Button>
          </form>
        </>
      )}
      {message && (
        <p
          role={mutation.isError ? "alert" : "status"}
          className={mutation.isError ? "text-sm text-destructive" : "text-sm text-foreground"}
        >
          {message}
        </p>
      )}
      {mutation.isError && (
        <Button
          variant="outline"
          onClick={() => {
            setConfirmation(null);
            void query.refetch();
          }}
        >
          تازه‌سازی فهرست
        </Button>
      )}
    </section>
  );
}

export function ItemCatalogSettings() {
  const user = useQuery({
    queryKey: ["session-user"],
    queryFn: async () => {
      const res = await api.GET("/api/v1/auth/me");
      if (res.error) throw await parseError(res.response);
      return res.data;
    },
  });
  const canWrite = user.data?.role === "OWNER" || user.data?.role === "BOOKKEEPER";
  return (
    <Card id="item-catalog-settings">
      <CardHeader>
        <CardTitle>اطلاعات پایهٔ کالا</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">
          این فهرست‌ها در دیتابیس همین نصب ذخیره و با انبار مشترک‌اند. ویرایش برای مالک و دفتردار
          مجاز است. حذف گزینهٔ استفاده‌شده، سوابق را پاک نمی‌کند و فقط انتخاب جدید را متوقف می‌کند.
        </p>
        <p className="text-sm text-muted-foreground">
          نوع تازه، کالای عمومی است و خودکار فیلامنت یا محصول تولیدی محسوب نمی‌شود. واحدهای تازه هیچ
          تبدیل ضمنی ندارند؛ تولید فعلی فقط فیلامنت با گرم و محصول با عدد را می‌پذیرد. نوع و واحد
          کالای ثبت‌شده تغییر نمی‌کند.
        </p>
        {!canWrite && (
          <p role="status">
            {user.isPending ? "در حال تأیید مجوز ویرایش…" : "اطلاعات پایه در حالت فقط خواندنی است."}
          </p>
        )}
        <div className="grid min-w-0 gap-4">
          <CatalogPanel category="types" canWrite={canWrite} />
          <CatalogPanel category="units" canWrite={canWrite} />
          <CatalogPanel category="suppliers" canWrite={canWrite} />
        </div>
      </CardContent>
    </Card>
  );
}
