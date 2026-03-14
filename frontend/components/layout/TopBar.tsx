"use client"

import { Badge } from "@/components/ui/badge"
import type { AuthUser } from "@/lib/types"

const ROLE_LABELS: Record<AuthUser["role"], string> = {
  admin: "Admin",
  marketing_manager: "Manager",
  marketer: "Marketer",
}

const ROLE_COLORS: Record<AuthUser["role"], string> = {
  admin: "bg-indigo-100 text-indigo-700 border-indigo-200",
  marketing_manager: "bg-violet-100 text-violet-700 border-violet-200",
  marketer: "bg-sky-100 text-sky-700 border-sky-200",
}

export function TopBar({ user }: { user: AuthUser }) {
  return (
    <header className="flex h-14 items-center justify-between border-b bg-white px-6 shrink-0">
      <div />
      <div className="flex items-center gap-3">
        <span className="text-sm font-medium text-slate-700">{user.display_name}</span>
        <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${ROLE_COLORS[user.role]}`}>
          {ROLE_LABELS[user.role]}
        </span>
      </div>
    </header>
  )
}
