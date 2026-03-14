"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { apiDelete, apiGet, apiPost } from "@/lib/api"

interface ConfigResponse {
  folders: string[]
}

export function useConfigFolders() {
  const { data, isLoading } = useQuery({
    queryKey: ["github-config"],
    queryFn: () => apiGet<ConfigResponse>("/api/v1/github/config"),
  })

  return {
    folders: data?.folders ?? [],
    isLoading,
  }
}

export function useAddFolder() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (folder: string) =>
      apiPost<{ folder: string; folders: string[]; scaffold_outcome: string }>(
        "/api/v1/github/config/folders",
        { folder }
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["github-config"] })
      queryClient.invalidateQueries({ queryKey: ["github-connection"] })
    },
  })
}

export function useRemoveFolder() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (folder: string) =>
      apiDelete(`/api/v1/github/config/folders/${encodeURIComponent(folder)}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["github-config"] })
      queryClient.invalidateQueries({ queryKey: ["github-connection"] })
    },
  })
}
