import { getUser } from "@/lib/dal"
import { UploadZone } from "@/components/ingestion/UploadZone"
import { JobTable } from "@/components/ingestion/JobTable"

export default async function IngestionPage() {
  await getUser()

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Document Ingestion</h1>
        <p className="text-muted-foreground mt-1">
          Upload documents to process and add to your knowledge base
        </p>
      </div>
      <UploadZone />
      <div>
        <h2 className="text-base font-semibold mb-3">Processing Jobs</h2>
        <JobTable />
      </div>
    </div>
  )
}
