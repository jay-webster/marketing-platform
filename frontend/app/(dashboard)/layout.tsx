import { getUser } from "@/lib/dal";
import { DashboardShell } from "@/components/layout/DashboardShell";

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const user = await getUser();

  return <DashboardShell user={user}>{children}</DashboardShell>;
}
