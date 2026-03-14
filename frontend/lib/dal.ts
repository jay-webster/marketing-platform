import "server-only";

import { cache } from "react";
import { redirect } from "next/navigation";
import { cookies } from "next/headers";
import { getSessionFromCookie } from "@/lib/session";
import type { AuthUser, SessionPayload } from "@/lib/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/**
 * Verify that a valid session cookie exists.
 * Returns the session payload or redirects to /login.
 */
export const verifySession = cache(async (): Promise<SessionPayload> => {
  const session = await getSessionFromCookie();

  if (!session) {
    redirect("/login");
  }

  return session;
});

/**
 * Get the current authenticated user from the backend API.
 * Throws (redirects) if no valid session exists.
 * Memoised per request via React.cache().
 */
export const getUser = cache(async (): Promise<AuthUser> => {
  // Verify session first — redirects if invalid
  await verifySession();

  const cookieStore = await cookies();
  const token = cookieStore.get("auth-token")?.value;

  if (!token) {
    redirect("/login");
  }

  const response = await fetch(`${API_URL}/api/v1/users/me`, {
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    cache: "no-store",
  });

  if (!response.ok) {
    if (response.status === 401) {
      redirect("/login");
    }
    throw new Error(`Failed to fetch user: ${response.status}`);
  }

  const json = await response.json();
  const data = json?.request_id !== undefined ? json.data : json;
  return data as AuthUser;
});

/**
 * Require the current user to have a specific role.
 * Redirects to / if the role does not match.
 */
export async function requireRole(
  role: "admin" | "marketer" | "marketing_manager"
): Promise<AuthUser> {
  const user = await getUser();

  if (user.role !== role) {
    redirect("/");
  }

  return user;
}
