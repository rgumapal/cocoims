import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, type ReactNode, useContext } from "react";
import { apiGet } from "@/api/client";
import * as authApi from "@/api/auth";
import type { MeResponse } from "@/api/types";

interface AuthContextValue {
  me: MeResponse | undefined;
  isLoading: boolean;
  isLoggedIn: boolean;
  hasPermission: (code: string) => boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();

  // /auth/me is the single source of truth for "who am I / what can I do"
  // (SPEC §13) — every permission check in the UI reads from this cached
  // query rather than re-deriving roles/scope client-side.
  const meQuery = useQuery({
    queryKey: ["me"],
    queryFn: () => apiGet<MeResponse>("/api/v1/auth/me"),
    enabled: authApi.isLoggedIn(),
    retry: false,
  });

  async function login(email: string, password: string): Promise<void> {
    await authApi.login(email, password);
    await queryClient.invalidateQueries({ queryKey: ["me"] });
  }

  async function logout(): Promise<void> {
    await authApi.logout();
    queryClient.clear(); // every cached query belongs to the session that just ended
  }

  function hasPermission(code: string): boolean {
    return meQuery.data?.permissions.includes(code) ?? false;
  }

  const value: AuthContextValue = {
    me: meQuery.data,
    isLoading: authApi.isLoggedIn() && meQuery.isLoading,
    isLoggedIn: meQuery.data !== undefined,
    hasPermission,
    login,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
