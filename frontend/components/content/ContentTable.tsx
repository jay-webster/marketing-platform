"use client"

import { useState, useEffect, useRef } from "react"
import { useRouter, usePathname, useSearchParams } from "next/navigation"
import { useQuery } from "@tanstack/react-query"
import { apiGet } from "@/lib/api"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { EmptyState } from "@/components/layout/EmptyState"
import type { KBIndexStatus, SyncedContent } from "@/lib/types"

const PAGE_SIZE = 50

const STATUS_VARIANTS: Record<
  KBIndexStatus,
  "default" | "secondary" | "destructive" | "outline"
> = {
  indexed: "default",
  queued: "outline",
  indexing: "secondary",
  failed: "destructive",
  removed: "outline",
}

interface ContentResponse {
  data: SyncedContent[]
  total: number
}

export function ContentTable({ offset }: { offset: number }) {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()

  const [search, setSearch] = useState("")
  const [debouncedSearch, setDebouncedSearch] = useState("")
  const [folder, setFolder] = useState<string>("all")
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => setDebouncedSearch(search), 300)
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current) }
  }, [search])

  const queryParams = new URLSearchParams()
  if (debouncedSearch) queryParams.set("search", debouncedSearch)
  if (folder && folder !== "all") queryParams.set("folder", folder)
  queryParams.set("limit", String(PAGE_SIZE))
  queryParams.set("offset", String(offset))

  const { data, isLoading } = useQuery({
    queryKey: ["synced-content", debouncedSearch, folder, offset],
    queryFn: () => apiGet<ContentResponse>(`/api/v1/content?${queryParams.toString()}`),
  })

  // Derive unique folders from current result set for the filter
  const folders = Array.from(new Set((data?.data ?? []).map((d) => d.folder))).sort()

  function navigate(newOffset: number) {
    const params = new URLSearchParams(searchParams.toString())
    params.set("offset", String(newOffset))
    router.push(`${pathname}?${params.toString()}`)
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="flex gap-3">
          <Skeleton className="h-9 w-64" />
          <Skeleton className="h-9 w-44" />
        </div>
        <div className="space-y-2">
          {[1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-12 w-full" />)}
        </div>
      </div>
    )
  }

  const items = data?.data ?? []
  const total = data?.total ?? 0
  const hasPrev = offset > 0
  const hasNext = offset + PAGE_SIZE < total

  return (
    <div className="space-y-4">
      <div className="flex gap-3">
        <Input
          placeholder="Search by title or path…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />
        <Select value={folder} onValueChange={(v) => { setFolder(v); navigate(0) }}>
          <SelectTrigger className="w-[200px]">
            <SelectValue placeholder="All folders" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All folders</SelectItem>
            {folders.map((f) => (
              <SelectItem key={f} value={f}>{f}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {items.length === 0 ? (
        <EmptyState
          title="No content synced yet"
          description="Run a sync from the GitHub settings page to index your repository."
        />
      ) : (
        <>
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Title</TableHead>
                  <TableHead>Folder</TableHead>
                  <TableHead>Index Status</TableHead>
                  <TableHead>Last Synced</TableHead>
                  <TableHead className="text-right">Chunks</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell className="font-medium">
                      <span className="text-sm">{item.title ?? item.repo_path}</span>
                      {item.title && (
                        <p className="text-xs text-muted-foreground font-mono">{item.repo_path}</p>
                      )}
                    </TableCell>
                    <TableCell className="text-muted-foreground font-mono text-xs">
                      {item.folder}
                    </TableCell>
                    <TableCell>
                      <Badge variant={STATUS_VARIANTS[item.index_status]} className="capitalize">
                        {item.index_status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-muted-foreground text-sm">
                      {new Date(item.last_synced_at).toLocaleDateString()}
                    </TableCell>
                    <TableCell className="text-right text-muted-foreground text-sm">
                      {item.chunk_count ?? "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <span>
              {total === 0 ? "0" : `${offset + 1}–${Math.min(offset + PAGE_SIZE, total)}`} of {total}
            </span>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" disabled={!hasPrev} onClick={() => navigate(offset - PAGE_SIZE)}>
                Previous
              </Button>
              <Button variant="outline" size="sm" disabled={!hasNext} onClick={() => navigate(offset + PAGE_SIZE)}>
                Next
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
