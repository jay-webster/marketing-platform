"use client"

import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import {
  LayoutDashboard,
  MessageSquare,
  FileText,
  Upload,
  GitBranch,
  Users,
  LogOut,
} from "lucide-react"

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import type { AuthUser } from "@/lib/types"

const NAV_LINKS = [
  {
    href: "/",
    label: "Dashboard",
    icon: LayoutDashboard,
    roles: ["admin", "marketer", "marketing_manager"],
    exact: true,
  },
  {
    href: "/chat",
    label: "Chat",
    icon: MessageSquare,
    roles: ["admin", "marketer", "marketing_manager"],
    exact: false,
  },
  {
    href: "/content",
    label: "Content",
    icon: FileText,
    roles: ["admin", "marketer", "marketing_manager"],
    exact: false,
  },
  {
    href: "/ingestion",
    label: "Ingestion",
    icon: Upload,
    roles: ["admin", "marketer", "marketing_manager"],
    exact: false,
  },
  {
    href: "/github",
    label: "GitHub",
    icon: GitBranch,
    roles: ["admin"],
    exact: false,
  },
  {
    href: "/users",
    label: "Users",
    icon: Users,
    roles: ["admin"],
    exact: false,
  },
] as const

export function Sidebar({ user }: { user: AuthUser }) {
  const pathname = usePathname()
  const router = useRouter()

  const visibleLinks = NAV_LINKS.filter((link) =>
    (link.roles as readonly string[]).includes(user.role)
  )

  async function handleLogout() {
    await fetch("/api/auth/logout", { method: "POST" })
    router.push("/login")
  }

  return (
    <aside className="flex w-64 flex-col shrink-0 bg-slate-900 text-slate-100">
      <div className="flex items-center gap-2 px-5 py-4 border-b border-slate-700/60">
        <div className="h-6 w-6 rounded-md bg-indigo-500 flex items-center justify-center shrink-0">
          <span className="text-white text-xs font-bold">M</span>
        </div>
        <span className="font-semibold text-sm tracking-tight">Marketing Platform</span>
      </div>
      <nav className="flex-1 p-3 space-y-0.5 overflow-y-auto">
        {visibleLinks.map((link) => {
          const isActive = link.exact
            ? pathname === link.href
            : pathname === link.href || pathname.startsWith(link.href + "/")
          return (
            <Link
              key={link.href}
              href={link.href}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-indigo-600 text-white"
                  : "text-slate-400 hover:bg-slate-800 hover:text-slate-100"
              )}
            >
              <link.icon className="h-4 w-4 shrink-0" />
              {link.label}
            </Link>
          )
        })}
      </nav>
      <div className="p-3 border-t border-slate-700/60">
        <Button
          variant="ghost"
          className="w-full justify-start gap-3 text-slate-400 hover:text-slate-100 hover:bg-slate-800"
          onClick={handleLogout}
        >
          <LogOut className="h-4 w-4" />
          Sign out
        </Button>
      </div>
    </aside>
  )
}
