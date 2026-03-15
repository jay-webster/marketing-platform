"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import type { GenerationRequest } from "@/lib/types"

interface GenerationResultProps {
  request: GenerationRequest
  onReset: () => void
  onRegenerate: () => void
}

export function GenerationResult({ request, onReset, onRegenerate }: GenerationResultProps) {
  const [copied, setCopied] = useState(false)
  const [isRegenerating, setIsRegenerating] = useState(false)

  const result = request.result

  async function handleCopy(text: string) {
    await navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  async function handleRegenerate() {
    setIsRegenerating(true)
    try {
      await onRegenerate()
    } finally {
      setIsRegenerating(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Email result */}
      {request.output_type === "email" && result && (
        <div className="flex flex-col gap-3">
          <div className="rounded-md border border-gray-200 bg-gray-50 p-4">
            <div className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-1">Subject</div>
            <div className="text-sm text-gray-900">{result.subject || "(no subject generated)"}</div>
          </div>
          <div className="rounded-md border border-gray-200 bg-gray-50 p-4">
            <div className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-1">Body</div>
            <div className="text-sm text-gray-900 whitespace-pre-wrap">{result.body || ""}</div>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => handleCopy(`Subject: ${result.subject ?? ""}\n\n${result.body ?? ""}`)}
            className="self-start"
          >
            {copied ? "Copied!" : "Copy All"}
          </Button>
        </div>
      )}

      {/* LinkedIn result */}
      {request.output_type === "linkedin" && result && (
        <div className="flex flex-col gap-3">
          <div className="rounded-md border border-gray-200 bg-gray-50 p-4">
            <div className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-1">Post</div>
            <div className="text-sm text-gray-900 whitespace-pre-wrap">{result.post_text || ""}</div>
          </div>
          {result.hashtags && result.hashtags.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {result.hashtags.map((tag) => (
                <span key={tag} className="rounded-full bg-blue-50 border border-blue-200 px-2 py-0.5 text-xs text-blue-700">
                  {tag}
                </span>
              ))}
            </div>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              const tags = result.hashtags?.join(" ") ?? ""
              handleCopy(`${result.post_text ?? ""}\n\n${tags}`.trim())
            }}
            className="self-start"
          >
            {copied ? "Copied!" : "Copy Post"}
          </Button>
        </div>
      )}

      {/* PDF result */}
      {request.output_type === "pdf" && result && (
        <div className="flex flex-col gap-3">
          <div className="rounded-md border border-gray-200 bg-gray-50 p-4">
            <div className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-1">Generated PDF</div>
            <div className="text-sm text-gray-700">{result.pdf_filename ?? "document.pdf"}</div>
          </div>
          {result.pdf_url && (
            <a
              href={result.pdf_url}
              download={result.pdf_filename ?? "document.pdf"}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 self-start"
            >
              Download PDF
            </a>
          )}
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-2 pt-1">
        <Button
          variant="outline"
          size="sm"
          onClick={handleRegenerate}
          disabled={isRegenerating}
        >
          {isRegenerating ? "Regenerating…" : "Regenerate"}
        </Button>
        <Button variant="ghost" size="sm" onClick={onReset}>
          Start Over
        </Button>
      </div>
    </div>
  )
}
