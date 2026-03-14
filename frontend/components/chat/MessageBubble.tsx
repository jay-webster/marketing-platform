import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import type { ChatMessage } from "@/lib/types"

export function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user"

  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[75%] rounded-lg px-4 py-3 text-sm",
          isUser
            ? "bg-slate-700 text-white"
            : "bg-white border border-border text-foreground"
        )}
      >
        <p className="whitespace-pre-wrap">{message.content}</p>
        {!isUser && message.is_generated_content && (
          <Badge
            variant="outline"
            className="mt-2 text-xs border-amber-400 text-amber-600"
          >
            AI-generated
          </Badge>
        )}
      </div>
    </div>
  )
}
