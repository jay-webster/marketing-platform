"use client"

import { useState } from "react"
import { ChevronDown, ChevronUp } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import type { SourceDoc } from "@/lib/types"

export function SourceDocs({ docs }: { docs: SourceDoc[] }) {
  const [open, setOpen] = useState(false)

  if (docs.length === 0) return null

  return (
    <div className="mt-2 rounded-md border bg-muted/30 text-sm">
      <Button
        variant="ghost"
        size="sm"
        className="w-full justify-between px-3 py-2 h-auto"
        onClick={() => setOpen((v) => !v)}
      >
        <span className="text-xs text-muted-foreground">
          {docs.length} source{docs.length !== 1 ? "s" : ""}
        </span>
        {open ? (
          <ChevronUp className="h-3 w-3 text-muted-foreground" />
        ) : (
          <ChevronDown className="h-3 w-3 text-muted-foreground" />
        )}
      </Button>
      {open && (
        <div className="px-3 pb-3 space-y-2">
          <Separator />
          {docs.map((doc, i) => (
            <div key={i} className="space-y-1">
              <div className="flex items-center justify-between">
                <span className="font-medium text-xs">{doc.title}</span>
                <span className="text-xs text-muted-foreground">
                  {(doc.similarity * 100).toFixed(0)}% match
                </span>
              </div>
              <p className="text-xs text-muted-foreground line-clamp-2 font-mono">
                {doc.source_file}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
