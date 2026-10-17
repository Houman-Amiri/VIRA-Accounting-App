import { useQuery } from "@tanstack/react-query";
import { api, parseError } from "@/api/client";
import type { components } from "@/api/schema";

export type CatalogChoice = components["schemas"]["CatalogRead"];
export type CatalogCategory = "types" | "units";
export function useItemCatalog(category: CatalogCategory) {
  return useQuery({
    queryKey: ["warehouse", "catalog", category],
    queryFn: async () => {
      const res = await api.GET("/api/v1/warehouse/catalog/{category}", {
        params: { path: { category } },
      });
      if (res.error) throw await parseError(res.response);
      if (!res.data) throw new Error("دریافت اطلاعات پایه ناموفق بود.");
      return res.data;
    },
  });
}

/** Legacy fixtures/readers may not yet provide the persisted display name. */
export function itemUnitLabel(item: { unit: string; unit_name?: string }) {
  return (
    item.unit_name || ({ G: "گرم", PCS: "عدد" } as Record<string, string>)[item.unit] || item.unit
  );
}
