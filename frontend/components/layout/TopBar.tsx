"use client"

import { Badge } from "@/components/ui/badge"
import type { AuthUser } from "@/lib/types"

const ROLE_LABELS: Record<AuthUser["role"], string> = {
  admin: "Admin",
  marketing_manager: "Manager",
  marketer: "Marketer",
}

export function TopBar({ user }: { user: AuthUser }) {
  return (
    <header className="flex h-14 items-center justify-between border-b bg-background px-4 shrink-0">
      <div />
      <div className="flex items-center gap-3">
        <span className="text-sm font-medium">{user.display_name}</span>
        <Badge variant="secondary">{ROLE_LABELS[user.role]}</Badge>
      </div>
    </header>
  )
}
