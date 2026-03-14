"use client"

import { useState } from "react"
import { toast } from "sonner"
import { Trash2, ScanSearch, Plus } from "lucide-react"

import { useConfigFolders, useAddFolder, useRemoveFolder } from "@/hooks/useConfigFolders"
import { useDiscoverFolders } from "@/hooks/useDiscoverFolders"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"

const TRAVERSAL_RE = /\.\./

function validateFolder(value: string): string | null {
  if (!value.trim()) return "Folder path is required"
  if (value.startsWith("/") || value.endsWith("/")) return "No leading or trailing slash"
  if (TRAVERSAL_RE.test(value)) return "Path traversal (..) is not allowed"
  return null
}

export function FolderManager() {
  const { folders, isLoading } = useConfigFolders()
  const addFolder = useAddFolder()
  const removeFolder = useRemoveFolder()
  const { discoveredFolders, isDiscovering, discoverError, discover, reset } = useDiscoverFolders()
  const [newFolder, setNewFolder] = useState("")
  const [validationError, setValidationError] = useState<string | null>(null)

  // Folders found in the repo that aren't already configured
  const unconfigured = discoveredFolders.filter((f) => !folders.includes(f))

  async function handleAdd(folder: string = newFolder) {
    const err = validateFolder(folder)
    if (err) { setValidationError(err); return }
    setValidationError(null)

    try {
      const result = await addFolder.mutateAsync(folder)
      const outcome = result?.scaffold_outcome
      if (outcome === "success") {
        toast.success(`Folder "${folder}" added and scaffolded in repo`)
      } else if (outcome === "failed") {
        toast.warning(`Folder "${folder}" added, but repo scaffolding failed — create the folder manually if needed`)
      } else {
        toast.success(`Folder "${folder}" added`)
      }
      if (folder === newFolder) setNewFolder("")
    } catch (err) {
      toast.error((err instanceof Error && err.message) ? err.message : "Failed to add folder")
    }
  }

  async function handleAddAll() {
    let added = 0
    for (const folder of unconfigured) {
      try {
        await addFolder.mutateAsync(folder)
        added++
      } catch {
        toast.error(`Failed to add "${folder}"`)
      }
    }
    if (added > 0) toast.success(`Added ${added} folder${added === 1 ? "" : "s"}`)
    reset()
  }

  async function handleRemove(folder: string) {
    try {
      await removeFolder.mutateAsync(folder)
      toast.success(`Folder "${folder}" removed`)
    } catch (err) {
      toast.error((err instanceof Error && err.message) ? err.message : "Failed to remove folder")
    }
  }

  const isMutating = addFolder.isPending || removeFolder.isPending

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-2">
          <div>
            <CardTitle className="text-base">Configured Folders</CardTitle>
            <CardDescription className="mt-1">
              Folders the sync engine monitors. Adding a folder creates a{" "}
              <code className="text-xs">.gitkeep</code> in your repo.
            </CardDescription>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={discoveredFolders.length > 0 ? reset : discover}
            disabled={isDiscovering || isMutating}
            className="shrink-0"
          >
            <ScanSearch className="h-3.5 w-3.5 mr-1.5" />
            {isDiscovering ? "Scanning…" : discoveredFolders.length > 0 ? "Clear" : "Discover"}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">

        {/* Configured folders list */}
        {isLoading ? (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => <Skeleton key={i} className="h-9 w-full" />)}
          </div>
        ) : folders.length === 0 ? (
          <p className="text-sm text-muted-foreground">No folders configured yet.</p>
        ) : (
          <ul className="divide-y rounded-md border">
            {folders.map((folder) => (
              <li key={folder} className="flex items-center justify-between px-3 py-2">
                <span className="font-mono text-sm">{folder}</span>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 text-muted-foreground hover:text-destructive"
                  disabled={isMutating}
                  onClick={() => handleRemove(folder)}
                  aria-label={`Remove ${folder}`}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </li>
            ))}
          </ul>
        )}

        {/* Discover results */}
        {discoverError && (
          <p className="text-sm text-destructive">{discoverError}</p>
        )}

        {discoveredFolders.length > 0 && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                  Found in repo
                </p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Add folders below to start syncing their content.
                </p>
              </div>
              {unconfigured.length > 0 && (
                <Button
                  variant="secondary"
                  size="sm"
                  className="h-7 text-xs"
                  onClick={handleAddAll}
                  disabled={isMutating}
                >
                  Add all ({unconfigured.length})
                </Button>
              )}
            </div>
            {unconfigured.length === 0 ? (
              <p className="text-sm text-muted-foreground">All discovered folders are already configured.</p>
            ) : (
              <ul className="divide-y rounded-md border">
                {unconfigured.map((folder) => (
                  <li key={folder} className="flex items-center justify-between px-3 py-2">
                    <span className="font-mono text-sm text-muted-foreground">{folder}</span>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 text-muted-foreground hover:text-foreground"
                      disabled={isMutating}
                      onClick={() => handleAdd(folder)}
                      aria-label={`Add ${folder}`}
                    >
                      <Plus className="h-3.5 w-3.5" />
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {/* Manual add */}
        <div className="space-y-1.5">
          <div className="flex gap-2">
            <Input
              placeholder="content/new-folder"
              value={newFolder}
              onChange={(e) => { setNewFolder(e.target.value); setValidationError(null) }}
              onKeyDown={(e) => { if (e.key === "Enter") handleAdd() }}
              disabled={isMutating}
              className="font-mono text-sm"
            />
            <Button
              onClick={() => handleAdd()}
              disabled={isMutating || !newFolder.trim()}
              size="sm"
            >
              {addFolder.isPending ? "Adding…" : "Add"}
            </Button>
          </div>
          {validationError && (
            <p className="text-xs text-destructive">{validationError}</p>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
