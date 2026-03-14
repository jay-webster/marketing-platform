import { cookies } from "next/headers"
import { notFound } from "next/navigation"
import { requireRole } from "@/lib/dal"
import { PRReviewCard } from "@/components/ingestion/PRReviewCard"
import type { PRReviewData } from "@/lib/types"

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

export default async function PRReviewPage({
  params,
}: {
  params: Promise<{ docId: string }>
}) {
  await requireRole("admin")
  const { docId } = await params

  const cookieStore = await cookies()
  const token = cookieStore.get("auth-token")?.value

  const res = await fetch(`${API_URL}/api/v1/ingestion/documents/${docId}/pr`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  })

  if (res.status === 404 || res.status === 409) {
    notFound()
  }

  if (!res.ok) {
    throw new Error("Failed to load PR review data")
  }

  const json = await res.json()
  const data: PRReviewData = json?.data ?? json

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Review Submission</h1>
        <p className="text-muted-foreground mt-1">
          Review the generated Markdown, select a destination folder, then merge or reject.
        </p>
      </div>
      <PRReviewCard data={data} />
    </div>
  )
}
