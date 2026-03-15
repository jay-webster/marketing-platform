"use client"

import { useRef, useState } from "react"
import { Upload, X } from "lucide-react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { apiGet } from "@/lib/api"
import { Button } from "@/components/ui/button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
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
const BFF_SIZE_LIMIT = 4 * 1024 * 1024 // 4 MB

interface UploadTokenResponse { token: string; upload_url: string; expires_in: number }
interface GitHubConfig { folders: string[] }

export function UploadZone({ userRole = "marketer" }: { userRole?: string }) {
  const isAdmin = userRole === "admin"
  const [isDragging, setIsDragging] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [selectedFolder, setSelectedFolder] = useState<string>("")
  const inputRef = useRef<HTMLInputElement>(null)
  const queryClient = useQueryClient()

  const { data: configData } = useQuery({
    queryKey: ["github-config"],
    queryFn: () => apiGet<GitHubConfig>("/api/v1/github/config"),
    enabled: isAdmin,
  })
  const folders = configData?.folders ?? []

  function validateFile(file: File): string | null {
    if (!ACCEPTED_TYPES.has(file.type) && !ACCEPTED.split(",").some((ext) => file.name.endsWith(ext))) {
      return `Unsupported file type: ${file.name}`
    }
    if (file.size > MAX_BYTES) {
      return `File too large (max 50 MB): ${file.name}`
    }
    if (isAdmin && !selectedFolder) {
      return "Please select a destination folder before uploading"
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
    form.append("folder_name", file.name.replace(/\.[^.]+$/, ""))
    if (isAdmin && selectedFolder) {
      form.append("destination_folder", selectedFolder)
    }

    try {
      let uploadUrl = `/api/v1/ingestion/batches`
      const extraHeaders: Record<string, string> = {}

      if (file.size > BFF_SIZE_LIMIT) {
        const tokenData = await apiGet<UploadTokenResponse>("/api/v1/ingestion/upload-token")
        uploadUrl = tokenData.upload_url
        extraHeaders["Authorization"] = `Bearer ${tokenData.token}`
      }

      const res = await fetch(uploadUrl, {
        method: "POST",
        headers: extraHeaders,
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
      queryClient.invalidateQueries({ queryKey: ["pr-list"] })
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
    <div className="space-y-3">
      {isAdmin && (
        <div className="flex items-center gap-3">
          <Select value={selectedFolder} onValueChange={setSelectedFolder}>
            <SelectTrigger className="w-[280px]">
              <SelectValue placeholder="Select destination folder…" />
            </SelectTrigger>
            <SelectContent>
              {folders.map((f) => (
                <SelectItem key={f} value={f}>{f}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          {folders.length === 0 && (
            <p className="text-xs text-muted-foreground">
              No folders configured — add folders in GitHub settings first.
            </p>
          )}
        </div>
      )}

      <div
        className={cn(
          "relative flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-10 transition-colors",
          isDragging ? "border-primary bg-primary/5" : "border-muted-foreground/25 hover:border-muted-foreground/50",
          (isUploading || (isAdmin && !selectedFolder)) && "opacity-60 pointer-events-none"
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
          disabled={isUploading || (isAdmin && !selectedFolder)}
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
        <div className="flex items-center gap-2 text-sm text-destructive">
          <X className="h-4 w-4 shrink-0" />
          <span>{uploadError}</span>
        </div>
      )}
    </div>
  )
}
