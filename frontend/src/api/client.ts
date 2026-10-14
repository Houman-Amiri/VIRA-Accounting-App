/**
 * Typed API client — openapi-fetch over the backend's OpenAPI schema.
 * Same-origin `/api` (Vite dev proxy → FastAPI). Mutating requests attach the
 * CSRF token header the backend requires on POST/PUT/DELETE (cookie-issued).
 */
import createClient from "openapi-fetch";
import type { paths } from "./schema";

export const API_BASE = "/api/v1";

export const api = createClient<paths>({ baseUrl: API_BASE, credentials: "include" });

const CSRF_COOKIE = "vira_csrf";
const CSRF_HEADER = "X-CSRF-Token";

export function getCsrfToken(): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${CSRF_COOKIE}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

// Attach CSRF on every mutating call.
api.use({
  onRequest({ request }) {
    const method = request.method.toUpperCase();
    if (method !== "GET" && method !== "HEAD") {
      const token = getCsrfToken();
      if (token) request.headers.set(CSRF_HEADER, token);
    }
    return request;
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
}

export async function parseError(response: Response): Promise<ApiError> {
  let code = "http_error";
  let message = `خطای سرور (${response.status})`;
  let detail: unknown;
  try {
    const body = (await response.json()) as Record<string, unknown>;
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
