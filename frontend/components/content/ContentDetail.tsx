import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import type { ContentDetail as ContentDetailType, ContentItem } from "@/lib/types"

const STATUS_VARIANTS: Record<
  ContentItem["status"],
  "default" | "secondary" | "destructive" | "outline"
> = {
  processed: "default",
  pending: "outline",
  processing: "secondary",
  failed: "destructive",
}

export function ContentDetail({ item }: { item: ContentDetailType }) {
  const metaEntries = Object.entries(item.metadata ?? {})

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <h1 className="text-2xl font-bold">{item.title}</h1>
        <Badge variant={STATUS_VARIANTS[item.status]}>{item.status}</Badge>
      </div>

      <div className="grid grid-cols-2 gap-x-8 gap-y-2 text-sm">
        <div>
          <span className="text-muted-foreground">Type</span>
          <p className="font-medium mt-0.5">{item.content_type}</p>
        </div>
        <div>
          <span className="text-muted-foreground">Last Updated</span>
          <p className="font-medium mt-0.5">
            {new Date(item.updated_at).toLocaleString()}
          </p>
        </div>
        <div>
          <span className="text-muted-foreground">Source</span>
          <p className="font-medium mt-0.5 truncate">{item.source_path}</p>
        </div>
        <div>
          <span className="text-muted-foreground">Created</span>
          <p className="font-medium mt-0.5">
            {new Date(item.created_at).toLocaleString()}
          </p>
        </div>
      </div>

      {metaEntries.length > 0 && (
        <>
          <Separator />
          <div>
            <h2 className="text-sm font-semibold mb-3">Metadata</h2>
            <div className="rounded-md border divide-y text-sm">
              {metaEntries.map(([key, value]) => (
                <div key={key} className="flex px-4 py-2 gap-4">
                  <span className="w-40 shrink-0 text-muted-foreground font-mono text-xs">
                    {key}
                  </span>
                  <span className="truncate">{String(value)}</span>
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      {item.body && (
        <>
          <Separator />
          <div>
            <h2 className="text-sm font-semibold mb-3">Content</h2>
            <pre className="whitespace-pre-wrap text-sm font-mono bg-muted/30 rounded-md p-4 overflow-auto max-h-[600px]">
              {item.body}
            </pre>
          </div>
        </>
      )}
    </div>
  )
}
