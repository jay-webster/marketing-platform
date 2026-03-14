"use client"

import { useIngestionPoll } from "@/hooks/useIngestionPoll"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { EmptyState } from "@/components/layout/EmptyState"
import type { JobStatus } from "@/lib/types"

const STATUS_VARIANTS: Record<
  JobStatus,
  "default" | "secondary" | "destructive" | "outline"
> = {
  pending_approval: "outline",
  queued: "outline",
  processing: "secondary",
  completed: "default",
  failed: "destructive",
  rejected: "outline",
}

const STATUS_LABELS: Record<JobStatus, string> = {
  pending_approval: "Awaiting Review",
  queued: "Queued",
  processing: "Processing",
  completed: "Complete",
  failed: "Failed",
  rejected: "Rejected",
}

const STATUS_CLASS: Partial<Record<JobStatus, string>> = {
  pending_approval: "text-amber-700 border-amber-300 bg-amber-50",
  rejected: "text-slate-500 border-slate-200 bg-slate-50",
}

export function JobTable() {
  const { jobs, isLoading } = useIngestionPoll()

  if (isLoading) {
    return (
      <div className="space-y-2">
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    )
  }

  if (jobs.length === 0) {
    return (
      <EmptyState
        title="No ingestion jobs"
        description="Upload a document above to start processing."
      />
    )
  }

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>File Name</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Created</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {jobs.map((job) => (
            <TableRow key={job.id}>
              <TableCell className="font-medium">
                {job.original_filename}
                {job.failure_reason && (
                  <p
                    className="text-xs text-destructive mt-0.5 truncate max-w-xs"
                    title={job.failure_reason}
                  >
                    {job.failure_reason}
                  </p>
                )}
              </TableCell>
              <TableCell>
                <Badge
                  variant={STATUS_VARIANTS[job.processing_status]}
                  className={STATUS_CLASS[job.processing_status]}
                >
                  {STATUS_LABELS[job.processing_status]}
                </Badge>
              </TableCell>
              <TableCell className="text-muted-foreground text-sm">
                {new Date(job.queued_at).toLocaleString()}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
