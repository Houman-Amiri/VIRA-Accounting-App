/**
 * Privacy-first product analytics — Umami (Phase 7 §5).
 *
 * The tracker is injected ONLY when both `VITE_UMAMI_WEBSITE_ID` and
 * `VITE_UMAMI_SCRIPT_URL` are configured (self-hosted Umami outside the app
 * runtime).  Every payload passes a strict zero-PII guard:
 *   - URL query parameters are stripped (`?search=...`, `?amount=...`)
 *   - UUID route segments are masked (`/accounts/:id`)
 *   - monetary figures, account names, payee text and receipt filenames are
 *     FORBIDDEN — payloads are built from a small key whitelist only.
 */

const UMAMI_SRC = import.meta.env.VITE_UMAMI_SCRIPT_URL as string | undefined;
const UMAMI_WEBSITE_ID = import.meta.env.VITE_UMAMI_WEBSITE_ID as string | undefined;

export type AnalyticsEvent =
  | "journal_entry_created"
  | "bank_statement_imported"
  | "reconciliation_completed"
  | "report_viewed";

/** Only these payload keys may ever leave the machine. */
const ALLOWED_KEYS = new Set(["event", "route", "entity", "status", "source"]);
const UUID_RE = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi;

export function analyticsEnabled(): boolean {
  return Boolean(UMAMI_SRC && UMAMI_WEBSITE_ID);
}

/** Mask UUIDs and strip query/hash — safe, non-identifying route shapes. */
export function sanitizeRoute(pathname: string): string {
  const noQuery = pathname.split("?")[0].split("#")[0];
  return noQuery.replace(UUID_RE, ":id");
}

/** Whitelist + drop anything forbidden (amounts, names, payees, filenames). */
export function sanitizePayload(data: Record<string, unknown> | undefined): Record<string, string> {
  const out: Record<string, string> = {};
  if (!data) return out;
  for (const [key, value] of Object.entries(data)) {
    if (!ALLOWED_KEYS.has(key)) continue; // money/PII keys never pass
    if (value == null) continue;
    let text = String(value);
    if (key === "route") text = sanitizeRoute(text);
    // defense in depth: never let a long digit string (an amount) through
    text = text.replace(/\d{5,}/g, "#");
    out[key] = text;
  }
  return out;
}

declare global {
  interface Window {
    umami?: {
      track: (event: string, data?: Record<string, string>) => void;
    };
  }
}

let injected = false;

export function initAnalytics(): void {
  if (!analyticsEnabled() || injected) return;
  injected = true;
  const script = document.createElement("script");
  script.async = true;
  script.src = UMAMI_SRC as string;
  script.setAttribute("data-website-id", UMAMI_WEBSITE_ID as string);
  script.setAttribute("data-do-not-track", "true");
  document.head.appendChild(script);
}

/** Typed, redaction-guarded wrapper around `window.umami.track()`. */
export function trackEvent(event: AnalyticsEvent, data?: Record<string, unknown>): void {
  if (!analyticsEnabled()) return;
  const payload = sanitizePayload({ event, ...data });
  window.umami?.track(event, payload);
}

export interface Analytics {
  track: (event: AnalyticsEvent, data?: Record<string, unknown>) => void;
  enabled: boolean;
}

export function useAnalytics(): Analytics {
  return {
    track: trackEvent,
    enabled: analyticsEnabled(),
  };
}
