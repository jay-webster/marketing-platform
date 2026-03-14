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
import type { BatchStatus } from "@/lib/types"

const STATUS_VARIANTS: Record<
  BatchStatus,
  "default" | "secondary" | "destructive" | "outline"
> = {
  in_progress: "secondary",
  completed: "default",
  completed_with_failures: "destructive",
}

const STATUS_LABELS: Record<BatchStatus, string> = {
  in_progress: "Processing",
  completed: "Complete",
  completed_with_failures: "Completed with failures",
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
        title="No submissions yet"
        description="Upload a document above to get started."
      />
    )
  }

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Folder / Name</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Documents</TableHead>
            <TableHead>Submitted</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {jobs.map((job) => (
            <TableRow key={job.batch_id}>
              <TableCell className="font-medium">
                {job.source_folder_name}
              </TableCell>
              <TableCell>
                <Badge variant={STATUS_VARIANTS[job.status]}>
                  {STATUS_LABELS[job.status]}
                </Badge>
              </TableCell>
              <TableCell className="text-muted-foreground text-sm">
                {job.completed_count}/{job.total_documents}
                {job.failed_count > 0 && (
                  <span className="text-destructive ml-1">
                    ({job.failed_count} failed)
                  </span>
                )}
              </TableCell>
              <TableCell className="text-muted-foreground text-sm">
                {new Date(job.submitted_at).toLocaleString()}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
