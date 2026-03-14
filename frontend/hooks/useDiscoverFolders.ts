"use client"

import { useState } from "react"
import { apiGet } from "@/lib/api"

interface DiscoverResponse {
  folders: string[]
}

export function useDiscoverFolders() {
  const [discoveredFolders, setDiscoveredFolders] = useState<string[]>([])
  const [isDiscovering, setIsDiscovering] = useState(false)
  const [discoverError, setDiscoverError] = useState<string | null>(null)

  async function discover() {
    setIsDiscovering(true)
    setDiscoverError(null)
    setDiscoveredFolders([])

    try {
      const data = await apiGet<DiscoverResponse>("/api/v1/github/config/discover-folders")
      setDiscoveredFolders(data?.folders ?? [])
    } catch (err) {
      setDiscoverError(err instanceof Error ? err.message : "Failed to scan repository")
    } finally {
      setIsDiscovering(false)
    }
  }

  function reset() {
    setDiscoveredFolders([])
    setDiscoverError(null)
  }

  return { discoveredFolders, isDiscovering, discoverError, discover, reset }
}
