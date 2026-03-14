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
  queued: "outline",
  processing: "secondary",
  complete: "default",
  failed: "destructive",
}

const STATUS_LABELS: Record<JobStatus, string> = {
  queued: "Queued",
  processing: "Processing",
  complete: "Complete",
  failed: "Failed",
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
                {job.file_name}
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
                <Badge variant={STATUS_VARIANTS[job.status]}>
                  {STATUS_LABELS[job.status]}
                </Badge>
              </TableCell>
              <TableCell className="text-muted-foreground text-sm">
                {new Date(job.created_at).toLocaleString()}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
