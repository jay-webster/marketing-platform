import "server-only";

import { jwtVerify } from "jose";
import { cookies } from "next/headers";
import type { SessionPayload } from "@/lib/types";

const AUTH_SECRET = process.env.AUTH_SECRET;

function getSecretKey(): Uint8Array {
  if (!AUTH_SECRET) {
    throw new Error("AUTH_SECRET environment variable is not set");
  }
  return new TextEncoder().encode(AUTH_SECRET);
}

export async function getSessionFromCookie(): Promise<SessionPayload | null> {
  const cookieStore = await cookies();
  const token = cookieStore.get("auth-token")?.value;

  if (!token) {
    return null;
  }

  try {
    const { payload } = await jwtVerify(token, getSecretKey(), {
      algorithms: ["HS256"],
    });

    return {
      sub: payload.sub as string,
      email: payload.email as string,
      role: payload.role as string,
      session_id: payload.session_id as string,
      exp: payload.exp as number,
    };
  } catch {
    // Token is invalid, expired, or malformed
    return null;
  }
}
