import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { vi } from "vitest";
import type { PricingSettings } from "@/lib/pricing-settings";

// Router navigation itself is covered by Playwright; retain real hooks and math here.
vi.mock("@tanstack/react-router", () => ({
  Link: ({ to, children, className }: { to: string; children: ReactNode; className?: string }) => (
    <a href={to} className={className}>
      {children}
    </a>
  ),
}));

export const SETTINGS: PricingSettings = {
  filamentPerGram: "3000.0000",
  electricityPerKwh: "1400.0000",
  depreciationPerHour: "10000.0000",
  profitFactor: "2.5000",
  chainPerUnit: "8000.0000",
  shipmentPerBatch: "150000.0000",
  labelPerUnit: "8000.0000",
  version_id: 1,
  updated_at: "2026-10-16T00:00:00Z",
};

export function renderWithPricing(
  ui: ReactNode,
  overrides: Partial<PricingSettings> = {},
  seed = true,
) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity }, mutations: { retry: false } },
  });
  client.setQueryData(["calendar-settings"], {
    calendar: "jalali",
    version_id: 0,
    timezone: "Asia/Tehran",
    scope: "installation",
  });
  // Isolate pricing assertions from the unrelated settings panels' HTTP calls.
  client.setQueryData(["session-user"], { role: "OWNER", username: "owner" });
  client.setQueryData(["warehouse", "catalog", "types"], []);
  client.setQueryData(["warehouse", "catalog", "units"], []);
  client.setQueryData(["warehouse", "suppliers"], []);
  if (seed) client.setQueryData(["pricing-settings"], { ...SETTINGS, ...overrides });
  return { ...render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>), client };
}
