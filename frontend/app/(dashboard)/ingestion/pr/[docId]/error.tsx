"use client"

import Link from "next/link"
import { Button } from "@/components/ui/button"

export default function PRReviewError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  const isNotFound = error.message?.toLowerCase().includes("not found") ||
    error.message?.toLowerCase().includes("404")
  const isForbidden = error.message?.toLowerCase().includes("forbidden") ||
    error.message?.toLowerCase().includes("403")

  if (isNotFound || isForbidden) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] gap-4">
        <h2 className="text-lg font-semibold">
          {isForbidden ? "Access Denied" : "PR Not Found"}
        </h2>
        <p className="text-sm text-muted-foreground">
          {isForbidden
            ? "You don't have permission to view this PR."
            : "This PR no longer exists or has already been processed."}
        </p>
        <Button asChild variant="outline">
          <Link href="/ingestion">Back to Ingestion</Link>
        </Button>
      </div>
    )
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-[400px] gap-4">
      <h2 className="text-lg font-semibold">Failed to load PR review</h2>
      <p className="text-sm text-muted-foreground">{error.message}</p>
      <div className="flex gap-2">
        <Button onClick={reset}>Try again</Button>
        <Button asChild variant="outline">
          <Link href="/ingestion">Back to Ingestion</Link>
        </Button>
      </div>
    </div>
  )
}
