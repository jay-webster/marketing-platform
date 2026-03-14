"use client"

import { useQuery } from "@tanstack/react-query"
import { apiGet } from "@/lib/api"
import type { IngestionListResponse, IngestionJob, JobStatus } from "@/lib/types"

const ACTIVE_STATUSES: JobStatus[] = ["pending_approval", "queued", "processing"]

function hasActiveJobs(data: IngestionListResponse | undefined): boolean {
  return (data?.data ?? []).some((job) =>
    ACTIVE_STATUSES.includes(job.processing_status)
  )
}

export function useIngestionPoll() {
  const { data, isLoading } = useQuery({
    queryKey: ["ingestion-batches"],
    queryFn: () => apiGet<IngestionListResponse>("/api/v1/ingestion/batches"),
    refetchInterval: (query) =>
      hasActiveJobs(query.state.data) ? 3000 : false,
  })

  return { jobs: (data?.data ?? []) as IngestionJob[], isLoading }
}
