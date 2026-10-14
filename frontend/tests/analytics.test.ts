/** Phase 7 §5 — Umami analytics: zero-PII redaction guard + opt-in injection. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  analyticsEnabled,
  initAnalytics,
  sanitizePayload,
  sanitizeRoute,
  trackEvent,
} from "@/lib/analytics";

describe("analytics redaction guard", () => {
  it("strips query params and masks UUIDs in routes", () => {
    const uuid = "123e4567-e89b-42d3-a456-426614174000";
    expect(sanitizeRoute(`/accounts/${uuid}?amount=99000&search=foo`)).toBe("/accounts/:id");
    expect(sanitizeRoute("/journal/new?x=1")).toBe("/journal/new");
  });

  it("drops forbidden keys (money, payees, filenames) entirely", () => {
    const out = sanitizePayload({
      event: "journal_entry_created",
      amount: "1500.50",
      payee: "شرکت نوین",
      account_name: "صندوق",
      filename: "receipt-123.pdf",
      route: "/journal/new",
      status: "ok",
    });
    expect(out).toEqual({ event: "journal_entry_created", route: "/journal/new", status: "ok" });
    expect(Object.keys(out)).not.toContain("amount");
    expect(Object.keys(out)).not.toContain("payee");
  });

  it("masks long digit strings (amounts) even inside allowed keys", () => {
    const out = sanitizePayload({ entity: "9900012345" });
    expect(out.entity).toBe("#");
  });

  it("is inert without env configuration", () => {
    expect(analyticsEnabled()).toBe(false);
    const spy = vi.fn();
    window.umami = { track: spy };
    trackEvent("report_viewed", { route: "/statements" });
    expect(spy).not.toHaveBeenCalled();
  });
});

describe("script injection", () => {
  beforeEach(() => {
    document.querySelectorAll("script[data-website-id]").forEach((s) => s.remove());
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("does not inject without both env vars (current test env)", () => {
    initAnalytics();
    expect(document.querySelectorAll("script[data-website-id]").length).toBe(0);
  });
});
