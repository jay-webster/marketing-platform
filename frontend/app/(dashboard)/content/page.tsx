import { Suspense } from "react"
import { getUser } from "@/lib/dal"
import { ContentFilters } from "@/components/content/ContentFilters"
import { ContentTable } from "@/components/content/ContentTable"
import { Skeleton } from "@/components/ui/skeleton"

export default async function ContentPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string; offset?: string }>
}) {
  await getUser()

  const { status, offset: offsetStr } = await searchParams
  const offset = parseInt(offsetStr ?? "0", 10)

  return (
    <div className="p-6 space-y-4">
      <div>
        <h1 className="text-2xl font-bold">Content</h1>
        <p className="text-muted-foreground mt-1">Browse synced documents in your knowledge base</p>
      </div>
      <Suspense fallback={<Skeleton className="h-10 w-[180px]" />}>
        <ContentFilters />
      </Suspense>
      <Suspense fallback={<div className="space-y-2">{[1,2,3,4,5].map(i => <Skeleton key={i} className="h-12 w-full" />)}</div>}>
        <ContentTable status={status} offset={offset} />
      </Suspense>
    </div>
  )
}
