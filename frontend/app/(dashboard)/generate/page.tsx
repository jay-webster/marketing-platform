"use client"

import { useState } from "react"
import { GenerationForm } from "@/components/generate/GenerationForm"
import { GenerationResult } from "@/components/generate/GenerationResult"
import { GenerationHistory } from "@/components/generate/GenerationHistory"
import { apiPost } from "@/lib/api"
import type { GenerationRequest, OutputType } from "@/lib/types"

type Tab = "generate" | "history"

export default function GeneratePage() {
  const [currentResult, setCurrentResult] = useState<GenerationRequest | null>(null)
  const [formKey, setFormKey] = useState(0)
  const [prefilledOutputType, setPrefilledOutputType] = useState<OutputType>("email")
  const [prefilledPrompt, setPrefilledPrompt] = useState("")
  const [activeTab, setActiveTab] = useState<Tab>("generate")

  function handleResult(result: GenerationRequest) {
    setCurrentResult(result)
  }

  function handleReset() {
    setCurrentResult(null)
    setFormKey((k) => k + 1)
    setPrefilledOutputType("email")
    setPrefilledPrompt("")
  }

  async function handleRegenerate() {
    if (!currentResult) return
    try {
      const data = await apiPost<GenerationRequest>("/api/v1/generate/", {
        output_type: currentResult.output_type,
        prompt: currentResult.prompt,
      })
      setCurrentResult(data)
    } catch {
      // errors surface in the GenerationResult component
    }
  }

  function handleHistorySelect(request: GenerationRequest) {
    setCurrentResult(request)
    setActiveTab("generate")
  }

  function handleHistoryRegenerate({ output_type, prompt }: { output_type: OutputType; prompt: string }) {
    setCurrentResult(null)
    setPrefilledOutputType(output_type)
    setPrefilledPrompt(prompt)
    setFormKey((k) => k + 1)
    setActiveTab("generate")
  }

  const formPanel = (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold text-gray-900">Generate Content</h1>

      {!currentResult ? (
        <GenerationForm
          key={formKey}
          onResult={handleResult}
          initialOutputType={prefilledOutputType}
          initialPrompt={prefilledPrompt}
        />
      ) : (
        <GenerationResult
          request={currentResult}
          onReset={handleReset}
          onRegenerate={handleRegenerate}
        />
      )}
    </div>
  )

  const historyPanel = (
    <div className="flex flex-col gap-3">
      <h2 className="text-lg font-semibold text-gray-900">History</h2>
      <GenerationHistory
        onSelect={handleHistorySelect}
        onRegenerate={handleHistoryRegenerate}
      />
    </div>
  )

  return (
    <div className="flex h-full overflow-hidden">
      {/* Desktop: split layout */}
      <div className="hidden md:flex flex-1 overflow-hidden">
        <main className="flex-1 overflow-y-auto p-6 border-r border-gray-200">
          <div className="max-w-2xl mx-auto">{formPanel}</div>
        </main>
        <aside className="w-80 overflow-y-auto p-4 bg-gray-50">
          {historyPanel}
        </aside>
      </div>

      {/* Mobile: tabbed layout */}
      <div className="flex flex-col flex-1 md:hidden overflow-hidden">
        <div className="flex border-b border-gray-200">
          {(["generate", "history"] as Tab[]).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`flex-1 py-3 text-sm font-medium capitalize transition-colors ${
                activeTab === tab
                  ? "border-b-2 border-gray-900 text-gray-900"
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              {tab}
            </button>
          ))}
        </div>
        <div className="flex-1 overflow-y-auto p-4">
          {activeTab === "generate" ? formPanel : historyPanel}
        </div>
      </div>
    </div>
  )
}
