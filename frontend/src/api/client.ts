/**
 * Typed API client — openapi-fetch over the backend's OpenAPI schema.
 * Same-origin `/api` (Vite dev proxy → FastAPI). Mutating requests attach the
 * CSRF token header the backend requires on POST/PATCH/DELETE (cookie-issued)
 * and an `Idempotency-Key` (Phase 5 §4) so retried mutations are safe.
 */
import createClient from "openapi-fetch";
import type { paths } from "./schema";

export const API_BASE = "/api/v1";

// Schema paths are already origin-absolute (`/api/v1/...`). Base must be the
// bare origin (never a path prefix) so openapi-fetch does not double `/api/v1`;
// using the origin also keeps Request URLs absolute (required outside browsers).
const ORIGIN =
  typeof window !== "undefined" && window.location?.origin ? window.location.origin : "";

export const api = createClient<paths>({
  baseUrl: ORIGIN,
  credentials: "include",
  // Lazy fetch delegation — keeps runtime/test replacements of globalThis.fetch
  // effective (openapi-fetch would otherwise bind the original at import).
  fetch: (...args: Parameters<typeof fetch>) => globalThis.fetch(...args),
});

const CSRF_COOKIE = "vira_csrf";
const CSRF_HEADER = "X-CSRF-Token";
const IDEM_HEADER = "Idempotency-Key";
const SUDO_HEADER = "X-Sudo-Token";

export function getCsrfToken(): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${CSRF_COOKIE}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

/** Fresh UUIDv4 for one logical mutation (stable across app-level retries). */
export function newIdempotencyKey(): string {
  return crypto.randomUUID();
}

// ---------------------------------------------------------------- sudo ---
// Step-up token (5-minute TTL) issued by POST /auth/sudo after password/TOTP
// re-verification; attached to high-risk requests while still valid.
let sudoToken: { value: string; expiresAt: number } | null = null;

export function setSudoToken(value: string, expiresInSeconds: number): void {
  sudoToken = { value, expiresAt: Date.now() + expiresInSeconds * 1000 };
}

export function getSudoToken(): string | null {
  if (sudoToken && sudoToken.expiresAt > Date.now()) return sudoToken.value;
  sudoToken = null;
  return null;
}

export function clearSudoToken(): void {
  sudoToken = null;
}

// ------------------------------------------------------- 401 handling ---
// On 401: snapshot unsaved form drafts in memory, then redirect to /login
// (TanStack Router navigation is registered from the app shell).
type UnauthorizedHandler = () => void;
let unauthorizedHandler: UnauthorizedHandler | null = null;

export function onUnauthorized(handler: UnauthorizedHandler): void {
  unauthorizedHandler = handler;
}

// openapi-fetch consumes error bodies before returning them to callers. Keep a
// weakly-held parse promise from a clone so existing parseError(response) calls
// can still display the actual domain detail (e.g. insufficient stock).
const errorBodies = new WeakMap<Response, Promise<unknown>>();

// Attach CSRF + Idempotency-Key + sudo token on every call.
api.use({
  onRequest({ request }) {
    const method = request.method.toUpperCase();
    if (method !== "GET" && method !== "HEAD") {
      const token = getCsrfToken();
      if (token) request.headers.set(CSRF_HEADER, token);
      // Every POST/PATCH mutation carries a client-generated Idempotency-Key;
      // callers may set their own (stable across retries) beforehand.
      if (!request.headers.has(IDEM_HEADER)) {
        request.headers.set(IDEM_HEADER, newIdempotencyKey());
      }
    }
    // Sudo token rides on every request (System & Operations GETs included).
    const sudo = getSudoToken();
    if (sudo && !request.headers.has(SUDO_HEADER)) {
      request.headers.set(SUDO_HEADER, sudo);
    }
    return request;
  },
  onResponse({ response }) {
    if (!response.ok)
      errorBodies.set(
        response,
        response
          .clone()
          .json()
          .catch(() => undefined),
      );
    if (response.status === 401 && unauthorizedHandler) {
      unauthorizedHandler();
    }
    return response;
  },
});

/** RFC 9457 problem+json error surfaced to UI. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly detail: unknown;

  constructor(status: number, code: string, message: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
  }

  /** Optimistic-locking conflict: the record changed under us (Phase 2 §9). */
  get isStale(): boolean {
    return this.status === 409 && this.code === "stale_version";
  }

  /** Sudo step-up required for a high-risk action (Phase 5 §2). */
  get needsSudo(): boolean {
    return this.status === 403 && this.code === "sudo_required";
  }
}

export async function parseError(response: Response): Promise<ApiError> {
  let code = "http_error";
  let message = `خطای سرور (${response.status})`;
  let detail: unknown;
  try {
    const body = (await (errorBodies.get(response) ?? response.json())) as Record<string, unknown>;
    if (typeof body.code === "string") code = body.code;
    if (typeof body.detail === "string") message = body.detail;
    detail = body;
  } catch {
    /* non-json error body */
  }
  return new ApiError(response.status, code, message, detail);
}

/** Throw a parsed ApiError when an openapi-fetch result is an error. */
export async function throwIfError(res: { error?: unknown; response: Response }): Promise<void> {
  if (res.error) {
    throw await parseError(res.response);
  }
}

export type { paths };
