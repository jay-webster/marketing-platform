import { NextRequest, NextResponse } from "next/server"

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

async function handler(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params
  // Read auth token directly from the incoming request cookies (same as middleware)
  const token = request.cookies.get("auth-token")?.value

  const searchParams = request.nextUrl.searchParams.toString()
  const backendUrl = `${BACKEND_URL}/api/v1/${path.join("/")}${searchParams ? `?${searchParams}` : ""}`

  const forwardedHeaders: Record<string, string> = {}
  const contentType = request.headers.get("Content-Type")
  if (contentType) {
    forwardedHeaders["Content-Type"] = contentType
  }
  if (token) {
    forwardedHeaders["Authorization"] = `Bearer ${token}`
  }

  const isBodyMethod = !["GET", "HEAD", "DELETE"].includes(request.method)

  // Read body as text to avoid ReadableStream duplex streaming issues
  const body = isBodyMethod ? await request.text() : undefined

  let backendResponse: Response
  try {
    backendResponse = await fetch(backendUrl, {
      method: request.method,
      headers: forwardedHeaders,
      ...(body !== undefined ? { body } : {}),
    })
  } catch {
    return NextResponse.json(
      { error: "Failed to connect to backend" },
      { status: 503 }
    )
  }

  const responseHeaders: Record<string, string> = {}
  const responseContentType = backendResponse.headers.get("Content-Type")
  if (responseContentType) {
    responseHeaders["Content-Type"] = responseContentType
  }
  if (responseContentType?.includes("text/event-stream")) {
    responseHeaders["Cache-Control"] = "no-cache"
    responseHeaders["X-Accel-Buffering"] = "no"
  }

  return new NextResponse(backendResponse.body, {
    status: backendResponse.status,
    headers: responseHeaders,
  })
}

export {
  handler as GET,
  handler as POST,
  handler as PUT,
  handler as PATCH,
  handler as DELETE,
}
