"use client"

import Link from "next/link"
import { Button } from "@/components/ui/button"

export default function ChatError({ reset }: { error: Error; reset: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-4">
      <h2 className="text-lg font-semibold">Could not load conversation</h2>
      <p className="text-sm text-muted-foreground">
        The conversation may have been deleted or an error occurred.
      </p>
      <div className="flex gap-2">
        <Button variant="outline" asChild>
          <Link href="/chat">Back to Chat</Link>
        </Button>
        <Button onClick={reset}>Try again</Button>
      </div>
    </div>
  )
}
