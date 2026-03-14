import { notFound } from "next/navigation"
import { cookies } from "next/headers"
import { getUser } from "@/lib/dal"
import { ChatWindow } from "@/components/chat/ChatWindow"
import { SessionList } from "@/components/chat/SessionList"
import type { ChatMessage } from "@/lib/types"

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

export default async function ChatSessionPage({
  params,
}: {
  params: Promise<{ sessionId: string }>
}) {
  await getUser()

  const { sessionId } = await params
  const cookieStore = await cookies()
  const token = cookieStore.get("auth-token")?.value

  let initialMessages: ChatMessage[] = []

  if (token) {
    const res = await fetch(
      `${API_URL}/api/v1/chat/sessions/${sessionId}/messages`,
      {
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      }
    )
    if (res.status === 404) {
      notFound()
    }
    if (res.ok) {
      const data = await res.json()
      initialMessages = data.data ?? []
    }
  }

  return (
    <div className="flex h-full overflow-hidden">
      <SessionList activeSessionId={sessionId} />
      <div className="flex-1 overflow-hidden">
        <ChatWindow sessionId={sessionId} initialMessages={initialMessages} />
      </div>
    </div>
  )
}
