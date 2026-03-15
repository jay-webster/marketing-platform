"use client"

import Link from "next/link"
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
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { EmptyState } from "@/components/layout/EmptyState"
import type { PRItem } from "@/lib/types"

interface PRListResponse {
  items: PRItem[]
  total: number
}

export function PRList() {
  const { data, isLoading } = useQuery({
    queryKey: ["pr-list"],
    queryFn: () => apiGet<PRListResponse>("/api/v1/ingestion/prs"),
    refetchInterval: 10000,
  })

  const prs = data?.items ?? []

  if (isLoading) {
    return (
      <div className="space-y-2">
        {[1, 2].map((i) => <Skeleton key={i} className="h-12 w-full" />)}
      </div>
    )
  }

  if (prs.length === 0) {
    return (
      <EmptyState
        title="No open pull requests"
        description="Approved submissions will appear here once the worker creates a GitHub PR."
      />
    )
  }

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>File Name</TableHead>
            <TableHead>Submitter</TableHead>
            <TableHead>Destination Folder</TableHead>
            <TableHead>PR</TableHead>
            <TableHead>Queued At</TableHead>
            <TableHead className="text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {prs.map((pr) => (
            <TableRow key={pr.id}>
              <TableCell className="font-medium">{pr.original_filename}</TableCell>
              <TableCell className="text-muted-foreground">{pr.submitted_by_name}</TableCell>
              <TableCell className="text-muted-foreground font-mono text-xs">{pr.destination_folder}</TableCell>
              <TableCell>
                <a
                  href={pr.github_pr_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm text-primary hover:underline"
                >
                  #{pr.github_pr_number}
                </a>
              </TableCell>
              <TableCell className="text-muted-foreground text-sm">
                {new Date(pr.queued_at).toLocaleString()}
              </TableCell>
              <TableCell className="text-right">
                <Button asChild size="sm" variant="outline">
                  <Link href={`/ingestion/pr/${pr.id}`}>Review</Link>
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
