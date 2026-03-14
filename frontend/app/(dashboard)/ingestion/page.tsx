import { getUser } from "@/lib/dal"
import { UploadZone } from "@/components/ingestion/UploadZone"
import { JobTable } from "@/components/ingestion/JobTable"
import { PendingApprovalTable } from "@/components/ingestion/PendingApprovalTable"
import { PRList } from "@/components/ingestion/PRList"

export default async function IngestionPage() {
  const user = await getUser()
  const isAdmin = user.role === "admin"

  return (
    <div className="p-6 space-y-8">
      <div>
        <h1 className="text-2xl font-bold">Document Ingestion</h1>
        <p className="text-muted-foreground mt-1">
          {isAdmin
            ? "Upload documents or review submissions from your team"
            : "Submit documents to add to your knowledge base — an admin will review before processing"}
        </p>
      </div>

      {isAdmin && (
        <div>
          <h2 className="text-base font-semibold mb-3">Pending Approval</h2>
          <PendingApprovalTable />
        </div>
      )}

      {isAdmin && (
        <div>
          <h2 className="text-base font-semibold mb-3">Open Pull Requests</h2>
          <PRList />
        </div>
      )}

      <div>
        <h2 className="text-base font-semibold mb-3">
          {isAdmin ? "Upload a Document" : "Submit a Document"}
        </h2>
        <UploadZone userRole={user.role} />
      </div>

      <div>
        <h2 className="text-base font-semibold mb-3">
          {isAdmin ? "All Processing Jobs" : "My Submissions"}
        </h2>
        <JobTable />
      </div>
    </div>
  )
}
