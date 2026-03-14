"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { apiGet, apiPost } from "@/lib/api"
import type { SyncStatus } from "@/lib/types"

export function useSync() {
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ["sync-status"],
    queryFn: () => apiGet<SyncStatus>("/api/v1/github/sync/status"),
    refetchInterval: (query) =>
      query.state.data?.latest_run?.outcome === "in_progress" ? 3000 : false,
  })

  const triggerSync = useMutation({
    mutationFn: () => apiPost("/api/v1/github/sync"),
    onSuccess: () => {
      // Start polling immediately
      queryClient.invalidateQueries({ queryKey: ["sync-status"] })
    },
  })

  return {
    status: data,
    isLoading,
    triggerSync,
  }
}
