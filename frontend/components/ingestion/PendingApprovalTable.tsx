"use client"

import { useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { CheckCircle, XCircle } from "lucide-react"
import { toast } from "sonner"

import { apiGet, apiPost } from "@/lib/api"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { EmptyState } from "@/components/layout/EmptyState"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import type { PendingDocument } from "@/lib/types"

const PENDING_PATH = "/api/v1/ingestion/pending"
const CONFIG_PATH = "/api/v1/github/config"

interface GitHubConfig {
  folders: string[]
}

export function PendingApprovalTable() {
  const queryClient = useQueryClient()
  const [approving, setApproving] = useState<PendingDocument | null>(null)
  const [selectedFolder, setSelectedFolder] = useState<string>("")
  const [actingOn, setActingOn] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ["pending-approvals"],
    queryFn: () => apiGet<PendingDocument[]>(PENDING_PATH),
    refetchInterval: 5000,
  })

  const { data: configData } = useQuery({
    queryKey: ["github-config"],
    queryFn: () => apiGet<GitHubConfig>(CONFIG_PATH),
  })

  const pending = data ?? []
  const folders = configData?.folders ?? []

  function openApproveDialog(doc: PendingDocument) {
    setApproving(doc)
    setSelectedFolder(folders[0] ?? "")
  }

  async function handleApprove() {
    if (!approving || !selectedFolder) return
    setActingOn(approving.id)
    try {
      await apiPost(`/api/v1/ingestion/documents/${approving.id}/approve`, {
        destination_folder: selectedFolder,
      })
      toast.success(`${approving.original_filename} approved and queued for processing`)
      queryClient.invalidateQueries({ queryKey: ["pending-approvals"] })
      queryClient.invalidateQueries({ queryKey: ["ingestion-batches"] })
      queryClient.invalidateQueries({ queryKey: ["pr-list"] })
      setApproving(null)
    } catch (err) {
      toast.error((err instanceof Error && err.message) ? err.message : `Failed to approve ${approving.original_filename}`)
    } finally {
      setActingOn(null)
    }
  }

  async function handleReject(doc: PendingDocument) {
    if (!confirm(`Reject and delete "${doc.original_filename}"? This cannot be undone.`)) return
    setActingOn(doc.id)
    try {
      await apiPost(`/api/v1/ingestion/documents/${doc.id}/reject`)
      toast.success(`${doc.original_filename} rejected`)
      queryClient.invalidateQueries({ queryKey: ["pending-approvals"] })
      queryClient.invalidateQueries({ queryKey: ["ingestion-batches"] })
    } catch {
      toast.error(`Failed to reject ${doc.original_filename}`)
    } finally {
      setActingOn(null)
    }
  }

  if (isLoading) {
    return (
      <div className="space-y-2">
        {[1, 2].map((i) => <Skeleton key={i} className="h-12 w-full" />)}
      </div>
    )
  }

  if (pending.length === 0) {
    return (
      <EmptyState
        title="No pending submissions"
        description="Non-admin document uploads will appear here for review."
      />
    )
  }

  return (
    <>
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>File Name</TableHead>
              <TableHead>Submitted By</TableHead>
              <TableHead>Submitted At</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {pending.map((doc) => {
              const isActing = actingOn === doc.id
              return (
                <TableRow key={doc.id}>
                  <TableCell className="font-medium">{doc.original_filename}</TableCell>
                  <TableCell className="text-muted-foreground">{doc.submitted_by_name}</TableCell>
                  <TableCell className="text-muted-foreground text-sm">
                    {new Date(doc.queued_at).toLocaleString()}
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex items-center justify-end gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        className="text-emerald-700 border-emerald-300 hover:bg-emerald-50"
                        disabled={isActing}
                        onClick={() => openApproveDialog(doc)}
                      >
                        <CheckCircle className="h-3.5 w-3.5 mr-1.5" />
                        Approve
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        className="text-destructive border-destructive/30 hover:bg-destructive/5"
                        disabled={isActing}
                        onClick={() => handleReject(doc)}
                      >
                        <XCircle className="h-3.5 w-3.5 mr-1.5" />
                        Reject
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </div>

      <Dialog open={!!approving} onOpenChange={(open) => { if (!open) setApproving(null) }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Approve Submission</DialogTitle>
            <DialogDescription>
              Select the destination folder for{" "}
              <span className="font-medium">{approving?.original_filename}</span>. The worker will
              create a GitHub PR in this folder for your final review.
            </DialogDescription>
          </DialogHeader>

          {folders.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No folders configured. Connect a GitHub repository and configure folders first.
            </p>
          ) : (
            <Select value={selectedFolder} onValueChange={setSelectedFolder}>
              <SelectTrigger>
                <SelectValue placeholder="Select folder" />
              </SelectTrigger>
              <SelectContent>
                {folders.map((f) => (
                  <SelectItem key={f} value={f}>
                    {f}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => setApproving(null)}>
              Cancel
            </Button>
            <Button
              onClick={handleApprove}
              disabled={!selectedFolder || actingOn === approving?.id}
            >
              {actingOn === approving?.id ? "Approving…" : "Approve"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
