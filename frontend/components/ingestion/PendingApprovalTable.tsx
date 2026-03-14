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
import type { PendingDocument } from "@/lib/types"

const API_PATH = "/api/v1/ingestion/pending"

export function PendingApprovalTable() {
  const queryClient = useQueryClient()
  const [actingOn, setActingOn] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ["pending-approvals"],
    queryFn: () => apiGet<PendingDocument[]>(API_PATH),
    refetchInterval: 5000,
  })

  const pending = data ?? []

  async function handleApprove(doc: PendingDocument) {
    setActingOn(doc.id)
    try {
      await apiPost(`/api/v1/ingestion/documents/${doc.id}/approve`)
      toast.success(`${doc.original_filename} approved and queued for processing`)
      queryClient.invalidateQueries({ queryKey: ["pending-approvals"] })
      queryClient.invalidateQueries({ queryKey: ["ingestion-batches"] })
    } catch {
      toast.error(`Failed to approve ${doc.original_filename}`)
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
                      onClick={() => handleApprove(doc)}
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
  )
}
