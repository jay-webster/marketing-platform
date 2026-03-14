"use client"

import { useRef, useState } from "react"
import { Upload, X } from "lucide-react"
import { useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

const ACCEPTED = ".pdf,.docx,.pptx,.csv,.txt,.md"
const ACCEPTED_TYPES = new Set([
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  "text/csv",
  "text/plain",
  "text/markdown",
])
const MAX_BYTES = 50 * 1024 * 1024 // 50 MB

export function UploadZone({ userRole = "marketer" }: { userRole?: string }) {
  const isAdmin = userRole === "admin"
  const [isDragging, setIsDragging] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const queryClient = useQueryClient()

  function validateFile(file: File): string | null {
    if (!ACCEPTED_TYPES.has(file.type) && !ACCEPTED.split(",").some((ext) => file.name.endsWith(ext))) {
      return `Unsupported file type: ${file.name}`
    }
    if (file.size > MAX_BYTES) {
      return `File too large (max 50 MB): ${file.name}`
    }
    return null
  }

  async function uploadFile(file: File) {
    const error = validateFile(file)
    if (error) {
      setUploadError(error)
      return
    }

    setIsUploading(true)
    setUploadError(null)

    const form = new FormData()
    form.append("files", file)
    // source_folder_name is a display label for the batch; use the filename stem
    form.append("folder_name", file.name.replace(/\.[^.]+$/, ""))

    try {
      const res = await fetch(`/api/v1/ingestion/batches`, {
        method: "POST",
        body: form,
      })

      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail ?? `Upload failed (${res.status})`)
      }

      if (isAdmin) {
        toast.success(`${file.name} queued for processing`)
      } else {
        toast.success(`${file.name} submitted for admin review`)
      }
      queryClient.invalidateQueries({ queryKey: ["ingestion-batches"] })
      queryClient.invalidateQueries({ queryKey: ["pending-approvals"] })
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "Upload failed")
    } finally {
      setIsUploading(false)
    }
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    setIsDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) uploadFile(file)
  }

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (file) uploadFile(file)
    e.target.value = ""
  }

  return (
    <div>
      <div
        className={cn(
          "relative flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-10 transition-colors",
          isDragging ? "border-primary bg-primary/5" : "border-muted-foreground/25 hover:border-muted-foreground/50",
          isUploading && "opacity-60 pointer-events-none"
        )}
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true) }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
      >
        <Upload className="h-8 w-8 text-muted-foreground mb-3" />
        <p className="text-sm font-medium mb-1">
          {isUploading ? (isAdmin ? "Uploading…" : "Submitting…") : "Drag & drop a file here"}
        </p>
        <p className="text-xs text-muted-foreground mb-4">
          PDF, DOCX, PPTX, CSV, TXT, or Markdown — max 50 MB
          {!isAdmin && <span className="block mt-0.5 text-amber-600">Uploads are reviewed by an admin before processing</span>}
        </p>
        <Button
          variant="outline"
          size="sm"
          disabled={isUploading}
          onClick={() => inputRef.current?.click()}
        >
          {isAdmin ? "Browse files" : "Submit for review"}
        </Button>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED}
          className="hidden"
          onChange={handleChange}
        />
      </div>
      {uploadError && (
        <div className="flex items-center gap-2 mt-2 text-sm text-destructive">
          <X className="h-4 w-4 shrink-0" />
          <span>{uploadError}</span>
        </div>
      )}
    </div>
  )
}
