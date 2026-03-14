import { notFound } from "next/navigation"
import Link from "next/link"
import { cookies } from "next/headers"
import { getUser } from "@/lib/dal"
import { ContentDetail } from "@/components/content/ContentDetail"
import { Button } from "@/components/ui/button"
import { ChevronLeft } from "lucide-react"
import type { ContentDetail as ContentDetailType } from "@/lib/types"

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

export default async function ContentDetailPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  await getUser()

  const { id } = await params
  const cookieStore = await cookies()
  const token = cookieStore.get("auth-token")?.value

  const res = await fetch(`${API_URL}/api/v1/ingestion/documents/${id}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    cache: "no-store",
  })

  if (res.status === 404) notFound()
  if (!res.ok) throw new Error(`Failed to fetch content: ${res.status}`)

  const item: ContentDetailType = await res.json()

  return (
    <div className="p-6 max-w-4xl space-y-6">
      <Button variant="ghost" size="sm" asChild className="-ml-2">
        <Link href="/content">
          <ChevronLeft className="h-4 w-4 mr-1" />
          Back to Content
        </Link>
      </Button>
      <ContentDetail item={item} />
    </div>
  )
}
