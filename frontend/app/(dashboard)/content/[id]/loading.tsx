import { Skeleton } from "@/components/ui/skeleton"

export default function ContentDetailLoading() {
  return (
    <div className="p-6 max-w-4xl space-y-6">
      <Skeleton className="h-8 w-24" />
      <div className="flex justify-between">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-6 w-20" />
      </div>
      <div className="grid grid-cols-2 gap-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="space-y-1">
            <Skeleton className="h-3 w-24" />
            <Skeleton className="h-5 w-32" />
          </div>
        ))}
      </div>
      <Skeleton className="h-64 w-full rounded-md" />
    </div>
  )
}
