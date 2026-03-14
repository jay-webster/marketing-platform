import { useState } from "react"
import { useQueryClient } from "@tanstack/react-query"

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

export function useDiscoverFolders() {
  const [discoveredFolders, setDiscoveredFolders] = useState<string[]>([])
  const [isDiscovering, setIsDiscovering] = useState(false)
  const [discoverError, setDiscoverError] = useState<string | null>(null)
  const queryClient = useQueryClient()

  async function discover() {
    setIsDiscovering(true)
    setDiscoverError(null)
    setDiscoveredFolders([])

    try {
      const res = await fetch(`${API_URL}/api/v1/github/config/discover-folders`, {
        credentials: "include",
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body?.detail?.message ?? "Failed to scan repository")
      }
      const json = await res.json()
      setDiscoveredFolders(json?.data?.folders ?? [])
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
