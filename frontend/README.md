# V.I.R.A — Frontend (Phase 3)

Persian RTL SPA: React 19 + TypeScript (strict) + Vite, TanStack (Router/Query/Table/Virtual),
shadcn/ui-style Tailwind components, decimal.js money math.

## Commands

```bash
pnpm install
pnpm openapi-ts   # regenerate src/api/schema.d.ts from ../backend/openapi.json
pnpm dev          # dev server on :5173, /api proxied to VIRA_API_URL (default :8787)
pnpm test         # Vitest unit suite
pnpm build        # tsc --noEmit && vite build
pnpm e2e          # Playwright smoke (playwright install chromium first)
```

## Conventions

- **Money**: API strings are exact 4-decimal values; all client math is `decimal.js`
  (`src/lib/money.ts`) — native JS `number` is never used for money.
- **Presentation**: Persian digits (`faNumber`), Jalali dates (`date-fns-jalali`),
  `<Money />` isolates figures LTR inside RTL flow, tabular-nums, accounting negatives.
- **State**: TanStack Query for server data; Zustand for ephemeral UI only.
- **URL is truth**: filters/dates/pagination live in URL search params (Zod-validated).
- **Charts**: ECharts, 2D only, RTL, dark/light.
