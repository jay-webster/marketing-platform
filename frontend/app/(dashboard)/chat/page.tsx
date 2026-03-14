import { redirect } from "next/navigation"
import { getUser } from "@/lib/dal"
import { cookies } from "next/headers"
import { EmptyState } from "@/components/layout/EmptyState"

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

export default async function ChatIndexPage() {
  await getUser()

  const cookieStore = await cookies()
  const token = cookieStore.get("auth-token")?.value

  // Try to redirect to the most recent session
  if (token) {
    const res = await fetch(
      `${API_URL}/api/v1/chat/sessions?limit=1`,
      {
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      }
    )
    if (res.ok) {
      const data = await res.json()
      if (data.data?.length > 0) {
        redirect(`/chat/${data.data[0].id}`)
      }
    }
  }

  // No sessions yet — show empty state
  return (
    <div className="flex h-full">
      <div className="flex-1 flex items-center justify-center">
        <EmptyState
          title="No conversations yet"
          description="Start your first conversation to explore your knowledge base."
        />
      </div>
    </div>
  )
}
