import { NextRequest, NextResponse } from "next/server";
import { getSessionFromCookie } from "@/lib/session";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function GET(request: NextRequest) {
  const session = await getSessionFromCookie();

  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  // Extract the raw token from the cookie to forward to backend
  const token = request.cookies.get("auth-token")?.value;

  if (!token) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const backendResponse = await fetch(`${API_URL}/api/v1/users/me`, {
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    cache: "no-store",
  });

  if (!backendResponse.ok) {
    if (backendResponse.status === 401) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    return NextResponse.json(
      { error: "Failed to fetch user" },
      { status: backendResponse.status }
    );
  }

  const user = await backendResponse.json();
  return NextResponse.json(user);
}
