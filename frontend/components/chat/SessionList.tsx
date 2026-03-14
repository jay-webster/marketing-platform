"use client"

import { useRouter } from "next/navigation"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { Plus, MessageSquare } from "lucide-react"

import { apiGet, apiPost } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"
import type { ChatSession } from "@/lib/types"

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  })
}

export function SessionList({ activeSessionId }: { activeSessionId?: string }) {
  const router = useRouter()
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ["chat-sessions"],
    queryFn: () => apiGet<ChatSession[]>("/api/v1/chat/sessions"),
  })

  async function handleNewChat() {
    const session = await apiPost<ChatSession>("/api/v1/chat/sessions", {})
    queryClient.invalidateQueries({ queryKey: ["chat-sessions"] })
    router.push(`/chat/${session.id}`)
  }

  return (
    <aside className="flex w-64 flex-col border-r bg-background shrink-0">
      <div className="p-3 border-b">
        <Button
          size="sm"
          className="w-full gap-2"
          onClick={handleNewChat}
        >
          <Plus className="h-4 w-4" />
          New Chat
        </Button>
      </div>
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {isLoading &&
          [1, 2, 3].map((i) => (
            <div key={i} className="p-2 space-y-1">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-3 w-16" />
            </div>
          ))}

        {data?.map((session) => (
          <button
            key={session.id}
            onClick={() => router.push(`/chat/${session.id}`)}
            className={cn(
              "w-full text-left rounded-md px-3 py-2 text-sm transition-colors",
              activeSessionId === session.id
                ? "bg-primary text-primary-foreground"
                : "hover:bg-muted"
            )}
          >
            <div className="flex items-center gap-2">
              <MessageSquare className="h-3 w-3 shrink-0" />
              <span className="truncate font-medium">
                {session.title ?? "New conversation"}
              </span>
            </div>
            <p
              className={cn(
                "text-xs mt-0.5 truncate",
                activeSessionId === session.id
                  ? "text-primary-foreground/70"
                  : "text-muted-foreground"
              )}
            >
              {formatDate(session.last_active_at)}
            </p>
          </button>
        ))}

        {!isLoading && data?.length === 0 && (
          <p className="text-xs text-muted-foreground text-center py-4">
            No conversations yet
          </p>
        )}
      </div>
    </aside>
  )
}
