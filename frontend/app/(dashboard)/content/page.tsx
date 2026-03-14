import { Suspense } from "react"
import { getUser } from "@/lib/dal"
import { ContentTable } from "@/components/content/ContentTable"
import { Skeleton } from "@/components/ui/skeleton"

export default async function ContentPage({
  searchParams,
}: {
  searchParams: Promise<{ offset?: string }>
}) {
  await getUser() // all authenticated roles can access

  const { offset: offsetStr } = await searchParams
  const offset = parseInt(offsetStr ?? "0", 10)

  return (
    <div className="p-6 space-y-4">
      <div>
        <h1 className="text-2xl font-bold">Content</h1>
        <p className="text-muted-foreground mt-1">
          Browse Markdown files synced from your connected GitHub repository
        </p>
      </div>
      <Suspense
        fallback={
          <div className="space-y-2">
            {[1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-12 w-full" />)}
          </div>
        }
      >
        <ContentTable offset={offset} />
      </Suspense>
    </div>
  )
}
