import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function POST(request: NextRequest) {
  let body: { email: string; password: string };

  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { error: "Invalid request body" },
      { status: 400 }
    );
  }

  const { email, password } = body;

  if (!email || !password) {
    return NextResponse.json(
      { error: "Email and password are required" },
      { status: 400 }
    );
  }

  let backendResponse: Response;
  try {
    backendResponse = await fetch(`${API_URL}/api/v1/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
  } catch {
    return NextResponse.json(
      { error: "Failed to connect to authentication service" },
      { status: 503 }
    );
  }

  if (!backendResponse.ok) {
    const errorData = await backendResponse.json().catch(() => ({
      detail: "Authentication failed",
    }));
    const raw = errorData.detail;
    const message =
      typeof raw === "string"
        ? raw
        : raw && typeof raw === "object"
        ? (raw as Record<string, string>).error ?? "Authentication failed"
        : "Authentication failed";
    return NextResponse.json(
      { error: message },
      { status: backendResponse.status }
    );
  }

  const responseData = await backendResponse.json();
  const accessToken: string | undefined =
    responseData?.data?.access_token ?? responseData?.access_token;

  if (!accessToken) {
    return NextResponse.json(
      { error: "No token received from server" },
      { status: 500 }
    );
  }

  const cookieStore = await cookies();
  cookieStore.set("auth-token", accessToken, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    // Token TTL — 8 hours default; adjust to match backend JWT exp
    maxAge: 60 * 60 * 8,
  });

  return NextResponse.json({ ok: true });
}
