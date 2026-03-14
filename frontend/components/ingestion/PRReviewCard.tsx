"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import ReactMarkdown from "react-markdown"
import { toast } from "sonner"
import { ExternalLink } from "lucide-react"

import { apiPost } from "@/lib/api"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
import type { PRReviewData } from "@/lib/types"

interface Props {
  data: PRReviewData
}

export function PRReviewCard({ data }: Props) {
  const router = useRouter()
  const [selectedFolder, setSelectedFolder] = useState(data.current_folder)
  const [isMerging, setIsMerging] = useState(false)
  const [isRejecting, setIsRejecting] = useState(false)

  async function handleMerge() {
    setIsMerging(true)
    try {
      await apiPost(`/api/v1/ingestion/documents/${data.id}/pr/merge`, {
        destination_folder: selectedFolder !== data.current_folder ? selectedFolder : undefined,
      })
      toast.success("PR merged — re-sync triggered")
      router.push("/ingestion")
    } catch (err) {
      toast.error((err instanceof Error && err.message) ? err.message : "Failed to merge PR")
    } finally {
      setIsMerging(false)
    }
  }

  async function handleReject() {
    setIsRejecting(true)
    try {
      await apiPost(`/api/v1/ingestion/documents/${data.id}/pr/close`)
      toast.success("PR closed")
      router.push("/ingestion")
    } catch (err) {
      toast.error((err instanceof Error && err.message) ? err.message : "Failed to close PR")
    } finally {
      setIsRejecting(false)
    }
  }

  return (
    <div className="grid grid-cols-[1fr_2fr_280px] gap-6 items-start">
      {/* Left: metadata */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium text-muted-foreground">Submission</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div>
            <p className="text-muted-foreground">File</p>
            <p className="font-medium break-all">{data.original_filename}</p>
          </div>
          <div>
            <p className="text-muted-foreground">Current folder</p>
            <p className="font-mono text-xs">{data.current_folder}</p>
          </div>
          <div>
            <p className="text-muted-foreground">GitHub PR</p>
            <a
              href={data.github_pr_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-primary hover:underline text-xs"
            >
              #{data.github_pr_number}
              <ExternalLink className="h-3 w-3" />
            </a>
          </div>
        </CardContent>
      </Card>

      {/* Centre: markdown preview */}
      <Card className="overflow-hidden">
        <CardHeader>
          <CardTitle className="text-sm font-medium text-muted-foreground">Preview</CardTitle>
        </CardHeader>
        <CardContent className="prose prose-sm dark:prose-invert max-w-none max-h-[70vh] overflow-y-auto">
          <ReactMarkdown>{data.markdown_content}</ReactMarkdown>
        </CardContent>
      </Card>

      {/* Right: actions */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium text-muted-foreground">Actions</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1.5">
            <p className="text-sm text-muted-foreground">Destination folder</p>
            <Select value={selectedFolder} onValueChange={setSelectedFolder}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {data.configured_folders.map((f) => (
                  <SelectItem key={f} value={f}>
                    {f}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <Button
            className="w-full"
            onClick={handleMerge}
            disabled={isMerging || isRejecting}
          >
            {isMerging ? "Merging…" : "Merge PR"}
          </Button>

          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button
                variant="destructive"
                className="w-full"
                disabled={isMerging || isRejecting}
              >
                Reject
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Reject this submission?</AlertDialogTitle>
                <AlertDialogDescription>
                  This will close the GitHub PR without merging. The submitter will be notified.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction
                  onClick={handleReject}
                  className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                >
                  {isRejecting ? "Rejecting…" : "Reject"}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </CardContent>
      </Card>
    </div>
  )
}
