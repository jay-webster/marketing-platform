import type { APIError } from "@/lib/types";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
    public readonly request_id?: string
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

/**
 * Core fetch wrapper.
 * - All /api/v1/* paths go through the Next.js BFF proxy at /api/v1/[...path]
 *   which reads the httpOnly auth-token cookie and adds the Authorization header.
 * - Other relative paths (e.g. /api/auth/*) go to Next.js Route Handlers directly.
 * - Throws ApiError on non-2xx responses.
 */
export async function apiFetch<T = unknown>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const url = path;

  const response = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers ?? {}),
    },
  });

  if (!response.ok) {
    // 401 on the client side: redirect to login
    if (response.status === 401 && typeof window !== "undefined") {
      window.location.href = "/login";
    }

    let errorBody: Record<string, unknown> = {};
    try {
      errorBody = await response.json();
    } catch {
      // Response body is not JSON — use status text
    }

    // Backend may return detail as a string or as {error, code}
    const raw = errorBody.detail;
    const message =
      typeof raw === "string"
        ? raw
        : raw && typeof raw === "object"
        ? (raw as Record<string, string>).error ?? JSON.stringify(raw)
        : (response.statusText ?? "Request failed");

    throw new ApiError(
      response.status,
      message,
      typeof errorBody.request_id === "string" ? errorBody.request_id : undefined
    );
  }

  // 204 No Content — return empty
  if (response.status === 204) {
    return undefined as T;
  }

  const json = await response.json();
  // Unwrap FastAPI envelope: { data: ..., request_id: ... }
  return (json?.request_id !== undefined ? json.data : json) as T;
}

export function apiGet<T = unknown>(
  path: string,
  options: Omit<RequestInit, "method"> = {}
): Promise<T> {
  return apiFetch<T>(path, { ...options, method: "GET" });
}

export function apiPost<T = unknown>(
  path: string,
  body?: unknown,
  options: Omit<RequestInit, "method" | "body"> = {}
): Promise<T> {
  return apiFetch<T>(path, {
    ...options,
    method: "POST",
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}

export function apiPatch<T = unknown>(
  path: string,
  body?: unknown,
  options: Omit<RequestInit, "method" | "body"> = {}
): Promise<T> {
  return apiFetch<T>(path, {
    ...options,
    method: "PATCH",
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}

export function apiDelete<T = unknown>(
  path: string,
  options: Omit<RequestInit, "method"> = {}
): Promise<T> {
  return apiFetch<T>(path, { ...options, method: "DELETE" });
}
