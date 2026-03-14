"use client"

import { useQuery } from "@tanstack/react-query"
import { apiGet } from "@/lib/api"
import type { BatchSummary } from "@/lib/types"

function hasActiveBatches(data: BatchSummary[] | undefined): boolean {
  return (data ?? []).some((b) => b.status === "in_progress")
}

export function useIngestionPoll() {
  const { data, isLoading } = useQuery({
    queryKey: ["ingestion-batches"],
    queryFn: () => apiGet<BatchSummary[]>("/api/v1/ingestion/batches"),
    refetchInterval: (query) =>
      hasActiveBatches(query.state.data) ? 3000 : false,
  })

  return { jobs: data ?? [], isLoading }
}
