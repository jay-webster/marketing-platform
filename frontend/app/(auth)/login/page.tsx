import { redirect } from "next/navigation";
import { getSessionFromCookie } from "@/lib/session";
import { LoginForm } from "./LoginForm";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  // Redirect already-authenticated users
  const session = await getSessionFromCookie();
  if (session) {
    redirect("/");
  }

  const { next } = await searchParams;

  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/40">
      <div className="w-full max-w-md space-y-6 p-8">
        <div className="text-center">
          <h1 className="text-2xl font-bold">Marketing Platform</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Sign in to your account
          </p>
        </div>
        <LoginForm next={next} />
      </div>
    </div>
  );
}
