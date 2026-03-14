"use client";

import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";
import type { AuthUser } from "@/lib/types";

export function useCurrentUser() {
  const { data: user, isLoading, error } = useQuery<AuthUser>({
    queryKey: ["me"],
    queryFn: () => apiGet<AuthUser>("/api/me"),
    staleTime: 60_000,
    retry: false,
  });

  return { user, isLoading, error };
}
