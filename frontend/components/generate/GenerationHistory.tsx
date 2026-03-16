"use client"

import { useCallback, useEffect, useState } from "react"
import { Button } from "@/components/ui/button"

import type { GenerationRequest, OutputType } from "@/lib/types"

const OUTPUT_TYPE_LABELS: Record<OutputType, string> = {
  email: "Email",
  linkedin: "LinkedIn",
  pdf: "PDF",
}

const OUTPUT_TYPE_COLORS: Record<OutputType, string> = {
  email: "bg-blue-50 text-blue-700 border-blue-200",
  linkedin: "bg-sky-50 text-sky-700 border-sky-200",
  pdf: "bg-purple-50 text-purple-700 border-purple-200",
}

interface GenerationHistoryProps {
  onSelect: (request: GenerationRequest) => void
  onRegenerate: (params: { output_type: OutputType; prompt: string }) => void
}

export function GenerationHistory({ onSelect, onRegenerate }: GenerationHistoryProps) {
  const [items, setItems] = useState<GenerationRequest[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const limit = 10

  const fetchHistory = useCallback(async (currentOffset: number) => {
    setIsLoading(true)
    setError(null)
    try {
      const res = await fetch(`/api/v1/generate/?limit=${limit}&offset=${currentOffset}`)
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        const raw = (body as Record<string, unknown>).detail ?? (body as Record<string, unknown>).error
        throw new Error(typeof raw === "string" ? raw : `Request failed (${res.status})`)
      }
      const json = await res.json()
      if (currentOffset === 0) {
        setItems(json.data)
      } else {
        setItems((prev) => [...prev, ...json.data])
      }
      setTotal(json.total)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load generation history.")
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchHistory(0)
  }, [fetchHistory])

  async function handleDelete(id: string) {
    if (!window.confirm("Delete this generated item? This cannot be undone.")) return
    const res = await fetch(`/api/v1/generate/${id}`, { method: "DELETE" })
    if (res.ok) {
      setItems((prev) => prev.filter((item) => item.id !== id))
      setTotal((t) => t - 1)
    }
  }

  function handleLoadMore() {
    const newOffset = offset + limit
    setOffset(newOffset)
    fetchHistory(newOffset)
  }

  if (isLoading && items.length === 0) {
    return <div className="text-sm text-gray-500 p-4">Loading history…</div>
  }

  if (error) {
    return <div className="text-sm text-red-600 p-4">{error}</div>
  }

  if (items.length === 0) {
    return (
      <div className="text-sm text-gray-500 p-4 text-center">
        No generated content yet
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-1 overflow-y-auto">
      {items.map((item) => (
        <div
          key={item.id}
          className="rounded-md border border-gray-200 bg-white p-3 flex flex-col gap-2"
        >
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-center gap-2 min-w-0">
              <span
                className={`shrink-0 rounded-full border px-2 py-0.5 text-xs font-medium ${
                  OUTPUT_TYPE_COLORS[item.output_type]
                }`}
              >
                {OUTPUT_TYPE_LABELS[item.output_type]}
              </span>
              <span
                className="text-sm text-gray-700 truncate"
                title={item.prompt}
              >
                {item.prompt.slice(0, 80)}{item.prompt.length > 80 ? "…" : ""}
              </span>
            </div>
            <span className="shrink-0 text-xs text-gray-400">
              {new Date(item.created_at).toLocaleDateString()}
            </span>
          </div>

          {item.status === "failed" && (
            <span className="text-xs text-red-600">
              {item.failure_reason === "no_kb_content"
                ? "No KB content found"
                : "Generation failed"}
            </span>
          )}

          <div className="flex gap-2 flex-wrap">
            {item.status === "completed" && (
              <Button
                variant="outline"
                size="sm"
                className="text-xs h-7 px-2"
                onClick={() => onSelect(item)}
              >
                View
              </Button>
            )}

            {item.output_type === "pdf" && item.pdf_url && (
              <a
                href={item.pdf_url}
                download
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center rounded-md border border-gray-300 bg-white px-2 py-0.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
              >
                Download
              </a>
            )}

            <Button
              variant="outline"
              size="sm"
              className="text-xs h-7 px-2"
              onClick={() => onRegenerate({ output_type: item.output_type, prompt: item.prompt })}
            >
              Regenerate
            </Button>

            <Button
              variant="ghost"
              size="sm"
              className="text-xs h-7 px-2 text-red-600 hover:text-red-700"
              onClick={() => handleDelete(item.id)}
            >
              Delete
            </Button>
          </div>
        </div>
      ))}

      {items.length < total && (
        <Button
          variant="outline"
          size="sm"
          className="mt-2 self-center"
          onClick={handleLoadMore}
          disabled={isLoading}
        >
          {isLoading ? "Loading…" : "Load More"}
        </Button>
      )}
    </div>
  )
}
