import { redirect } from "next/navigation"
import { getUser } from "@/lib/dal"
import { AdminDashboard } from "@/components/dashboard/AdminDashboard"

export default async function DashboardPage() {
  const user = await getUser()

  if (user.role !== "admin") {
    redirect("/chat")
  }

  return <AdminDashboard />
}
