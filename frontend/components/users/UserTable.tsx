"use client"

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
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { InviteDialog } from "./InviteDialog"
import type { User, Invitation, UserRole } from "@/lib/types"

const ROLE_LABELS: Record<UserRole, string> = {
  admin: "Admin",
  marketing_manager: "Manager",
  marketer: "Marketer",
}

function LoadingRows() {
  return (
    <>
      {[1, 2, 3].map((i) => (
        <TableRow key={i}>
          <TableCell colSpan={5}>
            <Skeleton className="h-5 w-full" />
          </TableCell>
        </TableRow>
      ))}
    </>
  )
}

export function UserTable() {
  const { data: usersData, isLoading: usersLoading } = useQuery({
    queryKey: ["users"],
    queryFn: () => apiGet<User[]>("/api/v1/users"),
  })

  const { data: invitationsData, isLoading: invitationsLoading } = useQuery({
    queryKey: ["invitations"],
    queryFn: () => apiGet<Invitation[]>("/api/v1/users/invitations"),
  })

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h2 className="text-lg font-semibold">Team Members</h2>
        <InviteDialog />
      </div>

      <Tabs defaultValue="users">
        <TabsList>
          <TabsTrigger value="users">
            Active Users
            {usersData && (
              <span className="ml-1.5 text-xs text-muted-foreground">
                ({usersData.length})
              </span>
            )}
          </TabsTrigger>
          <TabsTrigger value="invitations">
            Pending Invitations
            {invitationsData && (
              <span className="ml-1.5 text-xs text-muted-foreground">
                ({invitationsData.filter((i) => i.status === "pending").length})
              </span>
            )}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="users">
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Email</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Joined</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {usersLoading && <LoadingRows />}
                {usersData?.map((user) => (
                  <TableRow key={user.id}>
                    <TableCell className="font-medium">
                      {user.display_name}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {user.email}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">
                        {ROLE_LABELS[user.role]}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={
                          user.status === "active" ? "default" : "secondary"
                        }
                      >
                        {user.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-muted-foreground text-sm">
                      {new Date(user.created_at).toLocaleDateString()}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </TabsContent>

        <TabsContent value="invitations">
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Email</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Expires</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {invitationsLoading && <LoadingRows />}
                {invitationsData?.map((inv) => (
                  <TableRow key={inv.id}>
                    <TableCell className="text-muted-foreground">
                      {inv.invited_email}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">
                        {ROLE_LABELS[inv.assigned_role]}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={
                          inv.status === "pending"
                            ? "secondary"
                            : inv.status === "accepted"
                            ? "default"
                            : "destructive"
                        }
                      >
                        {inv.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-muted-foreground text-sm">
                      {new Date(inv.expires_at).toLocaleDateString()}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  )
}
