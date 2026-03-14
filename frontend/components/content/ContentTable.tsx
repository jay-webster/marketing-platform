"use client"

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
import { Skeleton } from "@/components/ui/skeleton"
import { EmptyState } from "@/components/layout/EmptyState"
import type { ContentListResponse, ContentItem } from "@/lib/types"

const STATUS_VARIANTS: Record<
  ContentItem["status"],
  "default" | "secondary" | "destructive" | "outline"
> = {
  processed: "default",
  pending: "outline",
  processing: "secondary",
  failed: "destructive",
}

const PAGE_SIZE = 20

export function ContentTable({
  status,
  offset,
}: {
  status?: string
  offset: number
}) {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()

  const queryParams = new URLSearchParams()
  if (status && status !== "all") queryParams.set("status", status)
  queryParams.set("limit", String(PAGE_SIZE))
  queryParams.set("offset", String(offset))

  const { data, isLoading } = useQuery({
    queryKey: ["content", status, offset],
    queryFn: () =>
      apiGet<ContentListResponse>(
        `/api/v1/ingestion/documents?${queryParams.toString()}`
      ),
  })

  function navigate(newOffset: number) {
    const params = new URLSearchParams(searchParams.toString())
    params.set("offset", String(newOffset))
    router.push(`${pathname}?${params.toString()}`)
  }

  if (isLoading) {
    return (
      <div className="space-y-2">
        {[1, 2, 3, 4, 5].map((i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    )
  }

  if (!data || data.data.length === 0) {
    return (
      <EmptyState
        title="No content found"
        description="No documents match the current filter."
      />
    )
  }

  const total = data.total
  const hasPrev = offset > 0
  const hasNext = offset + PAGE_SIZE < total

  return (
    <div className="space-y-4">
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Title</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Last Updated</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.data.map((item) => (
              <TableRow
                key={item.id}
                className="cursor-pointer hover:bg-muted/50"
                onClick={() => router.push(`/content/${item.id}`)}
              >
                <TableCell className="font-medium">{item.title}</TableCell>
                <TableCell className="text-muted-foreground text-sm">
                  {item.content_type}
                </TableCell>
                <TableCell>
                  <Badge variant={STATUS_VARIANTS[item.status]}>
                    {item.status}
                  </Badge>
                </TableCell>
                <TableCell className="text-muted-foreground text-sm">
                  {new Date(item.updated_at).toLocaleDateString()}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <div className="flex items-center justify-between text-sm text-muted-foreground">
        <span>
          {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total}
        </span>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={!hasPrev}
            onClick={() => navigate(offset - PAGE_SIZE)}
          >
            Previous
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={!hasNext}
            onClick={() => navigate(offset + PAGE_SIZE)}
          >
            Next
          </Button>
        </div>
      </div>
    </div>
  )
}
