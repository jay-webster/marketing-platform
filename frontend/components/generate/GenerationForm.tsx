"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { ImagePicker } from "./ImagePicker"
import { apiPost } from "@/lib/api"
import type { GenerationRequest, OutputType, PDFTemplate } from "@/lib/types"

const OUTPUT_TYPES: { value: OutputType; label: string }[] = [
  { value: "email", label: "Email" },
  { value: "linkedin", label: "LinkedIn Post" },
  { value: "pdf", label: "PDF" },
]

const PDF_TEMPLATES: { value: PDFTemplate; label: string }[] = [
  { value: "one_pager", label: "One-Pager" },
  { value: "campaign_brief", label: "Campaign Brief" },
]

const MAX_PROMPT = 2000
const WARN_AT = 1800

interface GenerationFormProps {
  onResult: (result: GenerationRequest) => void
  initialOutputType?: OutputType
  initialPrompt?: string
}

export function GenerationForm({
  onResult,
  initialOutputType = "email",
  initialPrompt = "",
}: GenerationFormProps) {
  const [outputType, setOutputType] = useState<OutputType>(initialOutputType)
  const [prompt, setPrompt] = useState(initialPrompt)
  const [pdfTemplate, setPdfTemplate] = useState<PDFTemplate>("one_pager")
  const [selectedImageIds, setSelectedImageIds] = useState<string[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const charCount = prompt.length
  const isOverLimit = charCount > MAX_PROMPT
  const isNearLimit = charCount >= WARN_AT && !isOverLimit

  async function handleSubmit() {
    if (!prompt.trim() || isOverLimit || isLoading) return
    setIsLoading(true)
    setError(null)

    try {
      const body: Record<string, unknown> = { output_type: outputType, prompt }
      if (outputType === "pdf") {
        body.pdf_template = pdfTemplate
        if (selectedImageIds.length > 0) body.image_ids = selectedImageIds
      }

      const data = await apiPost<GenerationRequest>("/api/v1/generate/", body)

      if (data.status === "failed" && data.failure_reason === "no_kb_content") {
        setError(
          "No relevant content found in the knowledge base for this prompt. " +
          "Try rephrasing or ensure the topic is covered in the synced documents."
        )
        return
      }

      onResult(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Generation failed. Please try again.")
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Output type selector */}
      <div>
        <label className="text-sm font-medium text-gray-700 mb-1 block">Output Type</label>
        <div className="flex gap-2">
          {OUTPUT_TYPES.map((t) => (
            <button
              key={t.value}
              onClick={() => setOutputType(t.value)}
              className={`px-4 py-2 rounded-md text-sm font-medium border transition-colors ${
                outputType === t.value
                  ? "bg-gray-900 text-white border-gray-900"
                  : "bg-white text-gray-700 border-gray-300 hover:border-gray-400"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* Prompt textarea */}
      <div>
        <label className="text-sm font-medium text-gray-700 mb-1 block">Prompt</label>
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          maxLength={MAX_PROMPT + 100}
          placeholder={
            outputType === "email"
              ? "e.g. Write a nurture email for prospects who downloaded our product one-pager"
              : outputType === "linkedin"
              ? "e.g. Announce our new Shopify integration, highlight the 5-step go-live process"
              : "e.g. Create a one-pager overview of our Q1 campaign messaging"
          }
          rows={5}
          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-gray-400 disabled:opacity-50"
          disabled={isLoading}
        />
        <div className={`text-xs mt-1 text-right ${isOverLimit ? "text-red-600" : isNearLimit ? "text-amber-600" : "text-gray-400"}`}>
          {charCount} / {MAX_PROMPT}
        </div>
      </div>

      {/* PDF-specific controls */}
      {outputType === "pdf" && (
        <>
          <div>
            <label className="text-sm font-medium text-gray-700 mb-1 block">Template</label>
            <div className="flex gap-2">
              {PDF_TEMPLATES.map((t) => (
                <button
                  key={t.value}
                  onClick={() => setPdfTemplate(t.value)}
                  className={`px-4 py-2 rounded-md text-sm font-medium border transition-colors ${
                    pdfTemplate === t.value
                      ? "bg-gray-900 text-white border-gray-900"
                      : "bg-white text-gray-700 border-gray-300 hover:border-gray-400"
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="text-sm font-medium text-gray-700 mb-2 block">
              Brand Images <span className="font-normal text-gray-500">(optional)</span>
            </label>
            <ImagePicker
              selectedIds={selectedImageIds}
              onSelectionChange={setSelectedImageIds}
            />
          </div>
        </>
      )}

      {/* Error message */}
      {error && (
        <div className="rounded-md bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <Button
        onClick={handleSubmit}
        disabled={!prompt.trim() || isOverLimit || isLoading}
        className="self-start"
      >
        {isLoading ? "Generating…" : "Generate"}
      </Button>
    </div>
  )
}
