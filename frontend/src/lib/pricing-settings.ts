import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, parseError } from "@/api/client";
import { DEFAULT_CONSTANTS, type PriceConstants } from "@/lib/priceCalc";
import type { components } from "@/api/schema";

export type PricingSettings = components["schemas"]["PricingRead"];
export type EditableConstant = Exclude<
  keyof PriceConstants,
  "printerPowerKw" | "commissionPercent" | "nylonPerUnit"
>;
export const PRICING_FIELDS: ReadonlyArray<[EditableConstant, string]> = [
  ["filamentPerGram", "قیمت هر گرم فیلامنت (تومان)"],
  ["electricityPerKwh", "قیمت هر کیلووات‌ساعت برق (تومان)"],
  ["depreciationPerHour", "استهلاک پرینتر در هر ساعت (تومان)"],
  ["profitFactor", "ضریب سود"],
  ["chainPerUnit", "حلقه و زنجیر هر عدد (تومان)"],
  ["shipmentPerBatch", "ارسال هر محموله (تومان)"],
  ["labelPerUnit", "لیبل هر عدد (تومان)"],
];

export function usePricingSettings() {
  return useQuery({
    queryKey: ["pricing-settings"],
    queryFn: async () => {
      const res = await api.GET("/api/v1/settings/pricing");
      if (res.error) throw await parseError(res.response);
      if (!res.data) throw new Error("دریافت ثابت‌های قیمت‌گذاری ناموفق بود.");
      return res.data;
    },
    retry: false,
  });
}

export function pricingConstants(data: PricingSettings): PriceConstants {
  return { ...DEFAULT_CONSTANTS, ...data };
}

export function useSavePricingSettings() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (body: components["schemas"]["PricingUpdate"]) => {
      const res = await api.PUT("/api/v1/settings/pricing", { body });
      if (res.error) throw await parseError(res.response);
      if (!res.data) throw new Error("ذخیرهٔ ثابت‌ها ناموفق بود.");
      return res.data;
    },
    onSuccess: async (data) => {
      await client.cancelQueries({ queryKey: ["pricing-settings"] });
      client.setQueryData(["pricing-settings"], data);
    },
  });
}
