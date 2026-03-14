import { cookies } from "next/headers"
import { requireRole } from "@/lib/dal"
import { ConnectionCard } from "@/components/github/ConnectionCard"
import type { GitHubConnection } from "@/lib/types"

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

export default async function GitHubPage() {
  await requireRole("admin")

  const cookieStore = await cookies()
  const token = cookieStore.get("auth-token")?.value

  let connection: GitHubConnection | null = null

  if (token) {
    const res = await fetch(`${API_URL}/api/v1/github/connection`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    })
    if (res.ok) {
      const json = await res.json()
      connection = json?.data ?? json
    }
    // 404 means no connection — leave as null
  }

  return (
    <div className="p-6 space-y-6 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold">GitHub Connection</h1>
        <p className="text-muted-foreground mt-1">
          Connect a repository to sync content into your knowledge base
        </p>
      </div>
      <ConnectionCard connection={connection} />
    </div>
  )
}
