import { getUser } from "@/lib/dal";

export default async function DashboardPage() {
  const user = await getUser();

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold">Dashboard</h1>
      <p className="text-muted-foreground mt-2">Welcome back, {user.display_name}</p>
    </div>
  );
}
