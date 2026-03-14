"use client"

import { useQuery } from "@tanstack/react-query"
import { apiGet } from "@/lib/api"
import type { SyncRun } from "@/lib/types"

interface SyncRunsResponse {
  runs: SyncRun[]
}

export function useSyncRuns(limit = 10) {
  const { data, isLoading } = useQuery({
    queryKey: ["sync-runs", limit],
    queryFn: () =>
      apiGet<SyncRunsResponse>(`/api/v1/github/sync/runs?limit=${limit}`),
  })

  return {
    runs: data?.runs ?? [],
    isLoading,
  }
}
