"use client"

import { useState } from "react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { useSync } from "@/hooks/useSync"
import { useSyncRuns } from "@/hooks/useSyncRuns"
import type { SyncOutcome, SyncRun } from "@/lib/types"

const OUTCOME_VARIANT: Record<
  SyncOutcome,
  "default" | "secondary" | "destructive" | "outline"
> = {
  success: "default",
  in_progress: "secondary",
  partial: "outline",
  failed: "destructive",
  interrupted: "outline",
}

function OutcomeBadge({ outcome }: { outcome: SyncOutcome }) {
  const isInProgress = outcome === "in_progress"
  return (
    <Badge variant={OUTCOME_VARIANT[outcome]} className="capitalize">
      {isInProgress ? (
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-yellow-400 animate-pulse" />
          syncing…
        </span>
      ) : (
        outcome.replace("_", " ")
      )}
    </Badge>
  )
}

function RunRow({ run }: { run: SyncRun }) {
  return (
    <div className="flex items-center justify-between py-2 text-sm border-b last:border-0">
      <div className="flex items-center gap-3">
        <OutcomeBadge outcome={run.outcome} />
        <span className="text-muted-foreground">
          {new Date(run.started_at).toLocaleString()}
        </span>
      </div>
      <div className="flex gap-4 text-muted-foreground text-xs">
        <span>{run.files_indexed} indexed</span>
        <span>{run.files_removed} removed</span>
        <span>{run.files_unchanged} unchanged</span>
      </div>
    </div>
  )
}

export function SyncCard() {
  const { status, isLoading, triggerSync } = useSync()
  const { runs } = useSyncRuns(5)
  const [runsOpen, setRunsOpen] = useState(false)

  const latestRun = status?.latest_run
  const isInProgress = latestRun?.outcome === "in_progress"
  const isSyncing = isInProgress || triggerSync.isPending

  async function handleSync() {
    try {
      await triggerSync.mutateAsync(undefined)
      toast.success("Sync started")
    } catch {
      toast.error("Failed to trigger sync")
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">Repository Sync</CardTitle>
          {latestRun && <OutcomeBadge outcome={latestRun.outcome} />}
        </div>
        <CardDescription>
          Sync Markdown files from your connected repository into the knowledge
          base
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {!isLoading && (
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <p className="text-muted-foreground">Last synced</p>
              <p className="font-medium">
                {status?.last_synced_at
                  ? new Date(status.last_synced_at).toLocaleString()
                  : "Never"}
              </p>
            </div>
            {latestRun && (
              <div>
                <p className="text-muted-foreground">Last run</p>
                <p className="font-medium">
                  {latestRun.files_indexed} indexed &middot;{" "}
                  {latestRun.files_removed} removed &middot;{" "}
                  {latestRun.files_unchanged} unchanged
                </p>
              </div>
            )}
          </div>
        )}

        <Button onClick={handleSync} disabled={isSyncing} size="sm">
          {isSyncing ? "Syncing…" : "Sync Now"}
        </Button>

        {runs.length > 0 && (
          <div>
            <button
              className="text-sm text-muted-foreground hover:text-foreground transition-colors"
              onClick={() => setRunsOpen((o) => !o)}
            >
              {runsOpen ? "Hide" : "Show"} recent runs ({runs.length})
            </button>
            {runsOpen && (
              <div className="mt-2">
                {runs.map((run) => (
                  <RunRow key={run.id} run={run} />
                ))}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
