import { requireRole } from "@/lib/dal"
import { UserTable } from "@/components/users/UserTable"

export default async function UsersPage() {
  await requireRole("admin")

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">User Management</h1>
        <p className="text-muted-foreground mt-1">
          Manage team members and pending invitations
        </p>
      </div>
      <UserTable />
    </div>
  )
}
