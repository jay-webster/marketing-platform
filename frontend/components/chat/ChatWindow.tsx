"use client"

import { useEffect, useRef, useState } from "react"
import { Send } from "lucide-react"

import { Button } from "@/components/ui/button"
import { MessageBubble } from "./MessageBubble"
import { SourceDocs } from "./SourceDocs"
import { useChat } from "@/hooks/useChat"
import type { ChatMessage } from "@/lib/types"

export function ChatWindow({
  sessionId,
  initialMessages,
}: {
  sessionId: string
  initialMessages: ChatMessage[]
}) {
  const { messages, sendMessage, isStreaming, streamingText, error } =
    useChat(initialMessages)

  const [input, setInput] = useState("")
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, streamingText])

  async function handleSubmit() {
    const text = input.trim()
    if (!text || isStreaming) return
    setInput("")
    await sendMessage(sessionId, text)
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Message list */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && !isStreaming && (
          <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
            Send a message to start the conversation
          </div>
        )}

        {messages.map((message) => (
          <div key={message.id}>
            <MessageBubble message={message} />
            {message.role === "assistant" &&
              message.source_documents &&
              message.source_documents.length > 0 && (
                <div className="flex justify-start mt-1 max-w-[75%]">
                  <SourceDocs docs={message.source_documents} />
                </div>
              )}
          </div>
        ))}

        {/* Streaming assistant message */}
        {isStreaming && streamingText && (
          <div className="flex justify-start">
            <div className="max-w-[75%] rounded-lg px-4 py-3 text-sm bg-white border border-border">
              <p className="whitespace-pre-wrap">{streamingText}</p>
            </div>
          </div>
        )}

        {/* Typing indicator */}
        {isStreaming && !streamingText && (
          <div className="flex justify-start">
            <div className="rounded-lg px-4 py-3 bg-white border border-border">
              <div className="flex gap-1">
                <span className="h-2 w-2 rounded-full bg-muted-foreground animate-bounce [animation-delay:-0.3s]" />
                <span className="h-2 w-2 rounded-full bg-muted-foreground animate-bounce [animation-delay:-0.15s]" />
                <span className="h-2 w-2 rounded-full bg-muted-foreground animate-bounce" />
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="text-sm text-destructive text-center">{error}</div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      <div className="border-t p-4">
        <div className="flex gap-2 items-end">
          <textarea
            ref={textareaRef}
            className="flex-1 min-h-[40px] max-h-[200px] resize-none rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed"
            placeholder="Type a message… (Enter to send, Shift+Enter for new line)"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={1}
            disabled={isStreaming}
          />
          <Button
            size="icon"
            onClick={handleSubmit}
            disabled={isStreaming || !input.trim()}
          >
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  )
}
