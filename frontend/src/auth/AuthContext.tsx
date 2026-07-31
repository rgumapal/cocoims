import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, type ReactNode, useContext, useState } from "react";
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

  // Reactive mirror of authApi.isLoggedIn() (which just reads localStorage).
  // Gating the /me query's `enabled` on a direct localStorage read doesn't
  // work: React has no way to know localStorage changed, so nothing
  // re-renders AuthProvider after login() sets the tokens, `enabled` stays
  // stuck at its first render's value (false), and /auth/me never fires —
  // confirmed live (login POST succeeded, /me was never called, the app
  // never left the login screen). This state is the fix: login()/logout()
  // set it explicitly, which is a real state update React reacts to.
  const [hasToken, setHasToken] = useState(authApi.isLoggedIn);

  // /auth/me is the single source of truth for "who am I / what can I do"
  // (SPEC §13) — every permission check in the UI reads from this cached
  // query rather than re-deriving roles/scope client-side.
  const meQuery = useQuery({
    queryKey: ["me"],
    queryFn: () => apiGet<MeResponse>("/api/v1/auth/me"),
    enabled: hasToken,
    retry: false,
  });

  async function login(email: string, password: string): Promise<void> {
    await authApi.login(email, password);
    setHasToken(true);
    await queryClient.invalidateQueries({ queryKey: ["me"] });
  }

  async function logout(): Promise<void> {
    await authApi.logout();
    setHasToken(false);
    queryClient.clear(); // every cached query belongs to the session that just ended
  }

  function hasPermission(code: string): boolean {
    return meQuery.data?.permissions.includes(code) ?? false;
  }

  const value: AuthContextValue = {
    me: meQuery.data,
    isLoading: hasToken && meQuery.isLoading,
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
