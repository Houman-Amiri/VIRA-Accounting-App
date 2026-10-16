/** Phase 5 §4 — client middleware: CSRF, Idempotency-Key, sudo token, 401. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  api,
  clearSudoToken,
  getSudoToken,
  newIdempotencyKey,
  onUnauthorized,
  parseError,
  setSudoToken,
} from "@/api/client";

function stubFetch(capture: Request[]): typeof fetch {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url =
      typeof input === "string" && input.startsWith("/")
        ? `http://localhost${input}`
        : (input as RequestInfo);
    const req = new Request(url, init);
    capture.push(req);
    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }) as unknown as typeof fetch;
}

describe("api client middleware", () => {
  let captured: Request[];

  beforeEach(() => {
    captured = [];
    globalThis.fetch = stubFetch(captured);
    document.cookie = "vira_csrf=csrf-token-value";
    clearSudoToken();
  });

  afterEach(() => {
    onUnauthorized(() => {});
  });

  it("adds CSRF and Idempotency-Key headers on POST", async () => {
    await api.POST("/api/v1/journal-entries", { body: {} as never });
    const req = captured[0];
    expect(req.headers.get("X-CSRF-Token")).toBe("csrf-token-value");
    expect(req.headers.get("Idempotency-Key")).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/,
    );
  });

  it("respects a caller-provided Idempotency-Key (stable across retries)", async () => {
    const key = newIdempotencyKey();
    await api.POST("/api/v1/journal-entries", {
      body: {} as never,
      headers: { "Idempotency-Key": key },
    } as never);
    await api.POST("/api/v1/journal-entries", {
      body: {} as never,
      headers: { "Idempotency-Key": key },
    } as never);
    expect(captured[0].headers.get("Idempotency-Key")).toBe(key);
    expect(captured[1].headers.get("Idempotency-Key")).toBe(key);
  });

  it("never adds Idempotency-Key on GET", async () => {
    await api.GET("/api/v1/accounts");
    expect(captured[0].headers.get("Idempotency-Key")).toBeNull();
    expect(captured[0].headers.get("X-CSRF-Token")).toBeNull();
  });

  it("attaches the sudo token while valid and drops it after expiry", async () => {
    setSudoToken("sudo-abc", 300);
    expect(getSudoToken()).toBe("sudo-abc");
    await api.POST("/api/v1/journal-entries", { body: {} as never });
    expect(captured[0].headers.get("X-Sudo-Token")).toBe("sudo-abc");
    // simulate expiry
    setSudoToken("sudo-old", -1);
    expect(getSudoToken()).toBeNull();
    await api.POST("/api/v1/journal-entries", { body: {} as never });
    expect(captured[1].headers.get("X-Sudo-Token")).toBeNull();
  });

  it("invokes the unauthorized handler on 401", async () => {
    const handler = vi.fn();
    onUnauthorized(handler);
    globalThis.fetch = vi.fn(
      async () => new Response(JSON.stringify({ code: "unauthenticated" }), { status: 401 }),
    ) as unknown as typeof fetch;
    await api.POST("/api/v1/journal-entries", { body: {} as never });
    expect(handler).toHaveBeenCalledTimes(1);
    onUnauthorized(() => {}); // reset
  });
});

it("preserves real domain details after openapi-fetch has consumed the response", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = vi.fn(
    async () =>
      new Response(JSON.stringify({ code: "insufficient_stock", detail: "موجودی کافی نیست" }), {
        status: 409,
        headers: { "Content-Type": "application/problem+json" },
      }),
  );
  try {
    const result = await api.POST("/api/v1/production/jobs/{job_id}/finish", {
      params: { path: { job_id: "test" } },
    });
    expect(result.response.bodyUsed).toBe(true);
    const error = await parseError(result.response);
    expect(error.code).toBe("insufficient_stock");
    expect(error.message).toBe("موجودی کافی نیست");
    expect((await parseError(result.response)).message).toBe(error.message);
  } finally {
    globalThis.fetch = original;
  }
});
