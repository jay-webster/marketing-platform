"use client"

import { Sidebar } from "./Sidebar"
import { TopBar } from "./TopBar"
import type { AuthUser } from "@/lib/types"

export function DashboardShell({
  user,
  children,
}: {
  user: AuthUser
  children: React.ReactNode
}) {
  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar user={user} />
      <div className="flex flex-1 flex-col overflow-hidden">
        <TopBar user={user} />
        <main className="flex-1 overflow-auto">
          {children}
        </main>
      </div>
    </div>
  )
}
