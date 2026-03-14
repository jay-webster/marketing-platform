import { getUser } from "@/lib/dal";

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // Server-side auth guard: redirects to /login if not authenticated
  await getUser();

  return (
    <div className="flex h-screen">
      <main className="flex-1 overflow-auto">
        {children}
      </main>
    </div>
  );
}
