import type { APIError } from "@/lib/types";

const API_URL =
  typeof window === "undefined"
    ? (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000")
    : (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000");

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
 * - Prepends NEXT_PUBLIC_API_URL for absolute backend paths
 * - Prepends nothing for relative /api/* paths (Next.js Route Handlers)
 * - Sets credentials: 'include' so the auth-token cookie is forwarded
 * - Throws ApiError on non-2xx responses
 */
export async function apiFetch<T = unknown>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  // Relative paths (e.g. /api/me) go to Next.js Route Handlers
  // Absolute paths (e.g. /api/v1/...) go to the FastAPI backend
  const url = path.startsWith("/api/v1/") || path.startsWith("/api/v1")
    ? `${API_URL}${path}`
    : path;

  const response = await fetch(url, {
    ...options,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers ?? {}),
    },
  });

  if (!response.ok) {
    let errorBody: Partial<APIError> = {};
    try {
      errorBody = await response.json();
    } catch {
      // Response body is not JSON — use status text
    }

    throw new ApiError(
      response.status,
      errorBody.detail ?? response.statusText ?? "Request failed",
      errorBody.request_id
    );
  }

  // 204 No Content — return empty
  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
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
