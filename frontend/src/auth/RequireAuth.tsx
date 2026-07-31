import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "./AuthContext";

/** Wraps a route element; redirects to /login if not authenticated.
 * Mirrors the backend guarantee (app.auth.deps.get_db requires
 * Depends(get_current_user)) on the client side — this is a UX
 * convenience, not the security boundary; the API enforces that itself
 * regardless of what this component does. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { isLoggedIn, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) return null; // brief flash while /auth/me resolves — see App shell's skeleton for longer waits
  if (!isLoggedIn) return <Navigate to="/login" state={{ from: location }} replace />;
  return <>{children}</>;
}

/** Wraps a route element or UI section; renders nothing if the current
 * user lacks the given permission (SPEC §7.4: deny by default — this is
 * the UI-layer expression of the same rule the API enforces server-side).
 */
export function RequirePermission({
  permission,
  children,
  fallback = null,
}: {
  permission: string;
  children: ReactNode;
  fallback?: ReactNode;
}) {
  const { hasPermission } = useAuth();
  if (!hasPermission(permission)) return <>{fallback}</>;
  return <>{children}</>;
}
