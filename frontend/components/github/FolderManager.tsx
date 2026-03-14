"use client"

import { useState } from "react"
import { toast } from "sonner"
import { Trash2 } from "lucide-react"

import { useConfigFolders, useAddFolder, useRemoveFolder } from "@/hooks/useConfigFolders"
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

const FOLDER_RE = /^[^/].*[^/]$|^[^./][^/]*[^./]$|^[a-zA-Z0-9_-]+$/
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
  const [newFolder, setNewFolder] = useState("")
  const [validationError, setValidationError] = useState<string | null>(null)

  async function handleAdd() {
    const err = validateFolder(newFolder)
    if (err) { setValidationError(err); return }
    setValidationError(null)

    try {
      const result = await addFolder.mutateAsync(newFolder)
      const outcome = result?.scaffold_outcome
      if (outcome === "success") {
        toast.success(`Folder "${newFolder}" added and scaffolded in repo`)
      } else if (outcome === "failed") {
        toast.warning(`Folder "${newFolder}" added, but repo scaffolding failed — create the folder manually if needed`)
      } else {
        toast.success(`Folder "${newFolder}" added`)
      }
      setNewFolder("")
    } catch (err) {
      toast.error((err instanceof Error && err.message) ? err.message : "Failed to add folder")
    }
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
        <CardTitle className="text-base">Configured Folders</CardTitle>
        <CardDescription>
          Folders the sync engine monitors. Adding a folder creates a{" "}
          <code className="text-xs">.gitkeep</code> in your repo.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
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
              onClick={handleAdd}
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
