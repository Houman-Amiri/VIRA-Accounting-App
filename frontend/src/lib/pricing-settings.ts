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

export function usePricingSettings(fresh = false) {
  return useQuery({
    queryKey: ["pricing-settings"],
    refetchOnMount: fresh ? "always" : true,
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

// ------------------------------------------------ owner-defined constants ---
export type CustomMethod = "PER_UNIT" | "PER_BATCH" | "PERCENT_OF_COST" | "PERCENT_OF_PRICE";
export type CustomConstant = components["schemas"]["PricingCustomConstantRead"];

/** What each calculation method means, said the way the owner reads it. */
export const CUSTOM_METHODS: ReadonlyArray<{ value: CustomMethod; label: string; hint: string }> = [
  {
    value: "PER_UNIT",
    label: "مبلغ ثابت برای هر عدد",
    hint: "مقدار را به‌ازای هر عدد به قیمت نهایی اضافه می‌کند.",
  },
  {
    value: "PER_BATCH",
    label: "مبلغ ثابت برای هر محموله",
    hint: "مقدار بین تعداد سفارش تقسیم می‌شود و سهم هر عدد اضافه می‌گردد.",
  },
  {
    value: "PERCENT_OF_COST",
    label: "درصدی از هزینهٔ تولید",
    hint: "درصدی از بهای تمام‌شدهٔ هر عدد (فیلامنت + برق + استهلاک).",
  },
  {
    value: "PERCENT_OF_PRICE",
    label: "درصدی از قیمت فروش",
    hint: "درصدی از قیمت فروش هر عدد پیش از افزودن همین ثابت‌ها.",
  },
];

export const CUSTOM_METHOD_LABEL: Record<CustomMethod, string> = Object.fromEntries(
  CUSTOM_METHODS.map((m) => [m.value, m.label]),
) as Record<CustomMethod, string>;

const CUSTOM_KEY = ["pricing-custom-constants"];

export function useCustomConstants(fresh = false) {
  return useQuery({
    queryKey: CUSTOM_KEY,
    refetchOnMount: fresh ? "always" : true,
    queryFn: async () => {
      const res = await api.GET("/api/v1/settings/pricing/constants");
      if (res.error) throw await parseError(res.response);
      return (res.data ?? []) as unknown as CustomConstant[];
    },
    retry: false,
  });
}

export function useCreateCustomConstant() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (body: components["schemas"]["PricingCustomConstantCreate"]) => {
      const res = await api.POST("/api/v1/settings/pricing/constants", { body });
      if (res.error) throw await parseError(res.response);
      if (!res.data) throw new Error("افزودن ثابت ناموفق بود.");
      return res.data;
    },
    onSuccess: () => void client.invalidateQueries({ queryKey: CUSTOM_KEY }),
  });
}

export function useUpdateCustomConstant() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({
      id,
      patch,
    }: {
      id: string;
      patch: components["schemas"]["PricingCustomConstantUpdate"];
    }) => {
      const res = await api.PATCH("/api/v1/settings/pricing/constants/{constant_id}", {
        params: { path: { constant_id: id } },
        body: patch,
      });
      if (res.error) throw await parseError(res.response);
      if (!res.data) throw new Error("ذخیرهٔ ثابت ناموفق بود.");
      return res.data;
    },
    onSuccess: () => void client.invalidateQueries({ queryKey: CUSTOM_KEY }),
  });
}

export function useDeleteCustomConstant() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      const res = await api.DELETE("/api/v1/settings/pricing/constants/{constant_id}", {
        params: { path: { constant_id: id } },
      });
      if (res.error) throw await parseError(res.response);
      return id;
    },
    onSuccess: () => void client.invalidateQueries({ queryKey: CUSTOM_KEY }),
  });
}

// ------------------------------------------------- owner-defined variables ---
export type VariableScope = "PER_UNIT" | "PER_ORDER";
export type VariableBasis = "AMOUNT" | "PERCENT_OF_COST" | "PERCENT_OF_PRICE";
export type VariableAllocation = "ONE_TIME" | "SPLIT";
export type PricingVariable = components["schemas"]["PricingVariableRead"];

/**
 * جزیی means the number lands on every piece; کلی means it lands on the order
 * as a whole — and then either once on the total or spread over the quantity.
 */
export const VARIABLE_SCOPES: ReadonlyArray<{
  value: VariableScope;
  label: string;
  hint: string;
}> = [
  {
    value: "PER_UNIT",
    label: "جزیی — روی هر عدد",
    hint: "این مقدار در قیمت هر عدد حساب می‌شود؛ با تغییر تیراژ، قیمت هر عدد ثابت می‌ماند.",
  },
  {
    value: "PER_ORDER",
    label: "کلی — روی کل سفارش",
    hint: "این مقدار برای کل سفارش حساب می‌شود؛ می‌توانید یک‌جا به جمع کل اضافه شود یا بین تعداد تقسیم شود.",
  },
];

export const VARIABLE_BASES: ReadonlyArray<{
  value: VariableBasis;
  label: string;
  hint: string;
}> = [
  { value: "AMOUNT", label: "مبلغ (تومان)", hint: "یک مبلغ ثابت که خودتان هر بار می‌نویسید." },
  {
    value: "PERCENT_OF_COST",
    label: "درصدی از بهای تمام‌شده",
    hint: "درصدی از هزینهٔ تولید هر عدد (فیلامنت + برق + استهلاک) که در فایل محاسبه آمده است.",
  },
  {
    value: "PERCENT_OF_PRICE",
    label: "درصدی از قیمت فروش",
    hint: "درصدی از قیمت فروش هر عدد پیش از افزودن ثابت‌ها و متغیرها.",
  },
];

export const VARIABLE_ALLOCATIONS: ReadonlyArray<{
  value: VariableAllocation;
  label: string;
  hint: string;
}> = [
  {
    value: "ONE_TIME",
    label: "یک‌جا روی جمع کل سفارش",
    hint: "فقط یک بار به جمع کل اضافه می‌شود و قیمت هر عدد را تغییر نمی‌دهد (مثل مالیات یا کرایهٔ ارسال). اگر در یک سفارش چند بار تکرار می‌شود (مثلاً ۲ محموله)، تعدادش را کنار مقدار متغیر در صفحهٔ قیمت‌گذاری بنویسید.",
  },
  {
    value: "SPLIT",
    label: "تقسیم بین تعداد",
    hint: "بین تعداد سفارش تقسیم می‌شود و سهم هر عدد در قیمت واحد می‌آید (مثل اجرت کارگاه).",
  },
];

export const VARIABLE_SCOPE_LABEL: Record<VariableScope, string> = {
  PER_UNIT: "جزیی (هر عدد)",
  PER_ORDER: "کلی (کل سفارش)",
};

export const VARIABLE_BASIS_LABEL: Record<VariableBasis, string> = Object.fromEntries(
  VARIABLE_BASES.map((basis) => [basis.value, basis.label]),
) as Record<VariableBasis, string>;

export const VARIABLE_ALLOCATION_LABEL: Record<VariableAllocation, string> = Object.fromEntries(
  VARIABLE_ALLOCATIONS.map((allocation) => [allocation.value, allocation.label]),
) as Record<VariableAllocation, string>;

const VARIABLE_KEY = ["pricing-variables"];

export function useVariables(fresh = false) {
  return useQuery({
    queryKey: VARIABLE_KEY,
    refetchOnMount: fresh ? "always" : true,
    queryFn: async () => {
      const res = await api.GET("/api/v1/settings/pricing/variables");
      if (res.error) throw await parseError(res.response);
      return (res.data ?? []) as unknown as PricingVariable[];
    },
    retry: false,
  });
}

export function useCreateVariable() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (body: components["schemas"]["PricingVariableCreate"]) => {
      const res = await api.POST("/api/v1/settings/pricing/variables", { body });
      if (res.error) throw await parseError(res.response);
      if (!res.data) throw new Error("افزودن متغیر ناموفق بود.");
      return res.data;
    },
    onSuccess: () => void client.invalidateQueries({ queryKey: VARIABLE_KEY }),
  });
}

export function useUpdateVariable() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({
      id,
      patch,
    }: {
      id: string;
      patch: components["schemas"]["PricingVariableUpdate"];
    }) => {
      const res = await api.PATCH("/api/v1/settings/pricing/variables/{variable_id}", {
        params: { path: { variable_id: id } },
        body: patch,
      });
      if (res.error) throw await parseError(res.response);
      if (!res.data) throw new Error("ذخیرهٔ متغیر ناموفق بود.");
      return res.data;
    },
    onSuccess: () => void client.invalidateQueries({ queryKey: VARIABLE_KEY }),
  });
}

export function useDeleteVariable() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      const res = await api.DELETE("/api/v1/settings/pricing/variables/{variable_id}", {
        params: { path: { variable_id: id } },
      });
      if (res.error) throw await parseError(res.response);
      return id;
    },
    onSuccess: () => void client.invalidateQueries({ queryKey: VARIABLE_KEY }),
  });
}
