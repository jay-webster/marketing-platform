import { NextRequest, NextResponse } from "next/server";
import { jwtVerify } from "jose";

const AUTH_SECRET = process.env.AUTH_SECRET;

function getSecretKey(): Uint8Array | null {
  if (!AUTH_SECRET) return null;
  return new TextEncoder().encode(AUTH_SECRET);
}

async function isValidToken(token: string): Promise<boolean> {
  const key = getSecretKey();
  if (!key) return false;

  try {
    await jwtVerify(token, key, { algorithms: ["HS256"] });
    return true;
  } catch {
    return false;
  }
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  const token = request.cookies.get("auth-token")?.value;
  const authenticated = token ? await isValidToken(token) : false;

  // Redirect authenticated users away from /login
  if (pathname === "/login" && authenticated) {
    return NextResponse.redirect(new URL("/", request.url));
  }

  // All protected paths: anything that is NOT /login and NOT /api/
  const isPublicPath =
    pathname === "/login" ||
    pathname.startsWith("/api/") ||
    pathname.startsWith("/_next/") ||
    pathname === "/favicon.ico";

  if (!isPublicPath && !authenticated) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("next", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    /*
     * Match all request paths EXCEPT:
     * - _next/static (static files)
     * - _next/image (image optimization)
     * - favicon.ico
     * - api/auth/* (auth route handlers — must be public)
     */
    "/((?!_next/static|_next/image|favicon.ico|api/auth/).*)",
  ],
};
