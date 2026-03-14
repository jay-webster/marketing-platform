"use client"

import Link from "next/link"
import { useQuery } from "@tanstack/react-query"
import { MessageSquare, FileText, Upload } from "lucide-react"

import { apiGet } from "@/lib/api"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import type { BatchSummary, ChatSession } from "@/lib/types"

function StatCard({
  title,
  description,
  href,
  icon: Icon,
  value,
  isLoading,
}: {
  title: string
  description: string
  href: string
  icon: React.ElementType
  value: number | undefined
  isLoading: boolean
}) {
  return (
    <Link href={href}>
      <Card className="hover:bg-muted/50 transition-colors cursor-pointer">
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">{title}</CardTitle>
          <Icon className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <Skeleton className="h-8 w-16" />
          ) : (
            <div className="text-2xl font-bold">{value ?? 0}</div>
          )}
          <CardDescription className="mt-1">{description}</CardDescription>
        </CardContent>
      </Card>
    </Link>
  )
}

export function AdminDashboard() {
  const { data: kbStatus, isLoading: contentLoading } = useQuery({
    queryKey: ["kb-status"],
    queryFn: () =>
      apiGet<{ total: number; by_status: Record<string, number> }>("/api/v1/knowledge-base/status"),
  })

  const { data: jobs, isLoading: jobsLoading } = useQuery({
    queryKey: ["ingestion-count"],
    queryFn: () => apiGet<BatchSummary[]>("/api/v1/ingestion/batches"),
  })

  const { data: sessions, isLoading: sessionsLoading } = useQuery({
    queryKey: ["sessions-count"],
    queryFn: () => apiGet<ChatSession[]>("/api/v1/chat/sessions"),
  })

  const activeBatches = (jobs ?? []).filter((j) => j.status === "in_progress").length

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <p className="text-muted-foreground mt-1">Overview of your marketing platform</p>
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        <StatCard
          title="Content Items"
          description="Total documents in knowledge base"
          href="/content"
          icon={FileText}
          value={kbStatus?.total}
          isLoading={contentLoading}
        />
        <StatCard
          title="Active Jobs"
          description="Batches currently processing"
          href="/ingestion"
          icon={Upload}
          value={activeBatches}
          isLoading={jobsLoading}
        />
        <StatCard
          title="Chat Sessions"
          description="Total conversation sessions"
          href="/chat"
          icon={MessageSquare}
          value={sessions?.length}
          isLoading={sessionsLoading}
        />
      </div>
    </div>
  )
}
