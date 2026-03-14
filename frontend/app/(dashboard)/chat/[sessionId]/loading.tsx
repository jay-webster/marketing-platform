import { Skeleton } from "@/components/ui/skeleton"

export default function ChatLoading() {
  return (
    <div className="flex h-full overflow-hidden">
      {/* Session list skeleton */}
      <aside className="flex w-64 flex-col border-r p-2 space-y-2">
        <Skeleton className="h-8 w-full" />
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="p-2 space-y-1">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-3 w-16" />
          </div>
        ))}
      </aside>
      {/* Chat skeleton */}
      <div className="flex-1 flex flex-col p-4 space-y-4">
        <div className="flex justify-end">
          <Skeleton className="h-16 w-64 rounded-lg" />
        </div>
        <div className="flex justify-start">
          <Skeleton className="h-24 w-80 rounded-lg" />
        </div>
        <div className="flex justify-end">
          <Skeleton className="h-12 w-48 rounded-lg" />
        </div>
      </div>
    </div>
  )
}
