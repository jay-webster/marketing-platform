"use client"

import { useState, useCallback } from "react"
import type { ChatMessage, SourceDoc, SSEChunkEvent, SSEDoneEvent } from "@/lib/types"

const API_URL =
  typeof window !== "undefined"
    ? (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000")
    : (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000")

export function useChat(initialMessages: ChatMessage[] = []) {
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages)
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamingText, setStreamingText] = useState("")
  const [sourceDocs, setSourceDocs] = useState<SourceDoc[]>([])
  const [error, setError] = useState<string | null>(null)

  const sendMessage = useCallback(
    async (sessionId: string, text: string) => {
      const userMsg: ChatMessage = {
        id: crypto.randomUUID(),
        session_id: sessionId,
        role: "user",
        content: text,
        is_generated_content: false,
        source_documents: null,
        created_at: new Date().toISOString(),
      }

      setMessages((prev) => [...prev, userMsg])
      setIsStreaming(true)
      setStreamingText("")
      setSourceDocs([])
      setError(null)

      try {
        const response = await fetch(
          `${API_URL}/api/v1/chat/sessions/${sessionId}/messages`,
          {
            method: "POST",
            credentials: "include",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ content: text }),
          }
        )

        if (!response.ok || !response.body) {
          throw new Error(`HTTP ${response.status}`)
        }

        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ""
        let accumulatedText = ""
        let isGenerated = false

        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split("\n")
          buffer = lines.pop() ?? ""

          let eventType = ""
          let dataLine = ""

          for (const line of lines) {
            if (line.startsWith("event: ")) {
              eventType = line.slice(7).trim()
            } else if (line.startsWith("data: ")) {
              dataLine = line.slice(6).trim()
            } else if (line === "") {
              if (eventType && dataLine) {
                try {
                  const payload = JSON.parse(dataLine)

                  if (eventType === "chunk") {
                    const chunk = payload as SSEChunkEvent
                    accumulatedText += chunk.text
                    isGenerated = chunk.is_generated_content
                    setStreamingText(accumulatedText)
                  } else if (eventType === "done") {
                    const doneEvent = payload as SSEDoneEvent
                    const assistantMsg: ChatMessage = {
                      id: doneEvent.message_id,
                      session_id: doneEvent.session_id,
                      role: "assistant",
                      content: accumulatedText,
                      is_generated_content: isGenerated,
                      source_documents: doneEvent.source_documents,
                      created_at: new Date().toISOString(),
                    }
                    setMessages((prev) => [...prev, assistantMsg])
                    setSourceDocs(doneEvent.source_documents)
                    setStreamingText("")
                    setIsStreaming(false)
                  } else if (eventType === "error") {
                    throw new Error(payload.detail ?? "Stream error")
                  }
                } catch {
                  // Malformed SSE frame — skip
                }
              }
              eventType = ""
              dataLine = ""
            }
          }
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to send message")
        setIsStreaming(false)
        setStreamingText("")
      }
    },
    []
  )

  return {
    messages,
    sendMessage,
    isStreaming,
    streamingText,
    sourceDocs,
    error,
    setMessages,
  }
}
