"use client"

import Link from "next/link"
import { Button } from "@/components/ui/button"

export default function ContentDetailError({
  reset,
}: {
  error: Error
  reset: () => void
}) {
  return (
    <div className="flex flex-col items-center justify-center min-h-[400px] gap-4">
      <h2 className="text-lg font-semibold">Failed to load content</h2>
      <p className="text-sm text-muted-foreground">
        This document could not be loaded.
      </p>
      <div className="flex gap-2">
        <Button variant="outline" asChild>
          <Link href="/content">Back to Content</Link>
        </Button>
        <Button onClick={reset}>Try again</Button>
      </div>
    </div>
  )
}
