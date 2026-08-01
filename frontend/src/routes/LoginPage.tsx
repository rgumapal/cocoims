import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/auth/AuthContext";
import { signInWithGoogle } from "@/auth/firebase";
import { GoogleIcon } from "@/components/icons";

// Email+password sign-in (signInWithEmailPassword in auth/firebase.ts,
// backend/app/auth/router.py's /api/v1/auth/firebase already handles both)
// is deliberately not wired up here for now — Google is the one sign-in
// path in the UI until there's an actual need for the other. Nothing
// backend-side changed; this is a UI-only reduction.
export default function LoginPage() {
  const { loginWithFirebase, isLoggedIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [error, setError] = useState<string | null>(null);
  const [isGoogleSubmitting, setIsGoogleSubmitting] = useState(false);

  if (isLoggedIn) {
    const from = (location.state as { from?: Location })?.from?.pathname ?? "/dashboard";
    return <Navigate to={from} replace />;
  }

  async function handleGoogleSignIn(): Promise<void> {
    setError(null);
    setIsGoogleSubmitting(true);
    try {
      const idToken = await signInWithGoogle();
      await loginWithFirebase(idToken);
      navigate("/dashboard", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Google sign-in failed");
    } finally {
      setIsGoogleSubmitting(false);
    }
  }

  return (
    <div className="flex h-screen flex-col items-center justify-center gap-3 bg-bg p-4">
      {/* Fixed brand colors, not theme-following surface/text tokens — same
          treatment as the app shell's header (see AppShell.tsx), since this
          is brand chrome, not content. */}
      <div className="w-full max-w-sm rounded-lg bg-header-bg p-6 shadow-2">
        <div className="mb-6 flex items-center gap-2">
          <span className="h-3 w-3 rounded-sm bg-header-fg" aria-hidden="true" />
          <span className="font-ui text-h1 text-header-fg">Cocopan IMS</span>
        </div>

        <div className="flex flex-col gap-4">
          {/* White background is Google's own sign-in button branding, not
              this app's token system — same deliberate exception as
              GoogleIcon's brand colors. */}
          <button
            type="button"
            onClick={() => void handleGoogleSignIn()}
            disabled={isGoogleSubmitting}
            className="flex w-full items-center justify-center gap-2 rounded-md bg-white px-3 py-1.5 font-ui text-body font-medium text-[#1c1b19] transition-colors duration-theme hover:bg-[#f5f4f2] disabled:cursor-not-allowed disabled:opacity-50"
          >
            <GoogleIcon />
            {isGoogleSubmitting ? "Signing in…" : "Sign in with Google or Other email"}
          </button>
        </div>
      </div>

      {/* Outside the card, not inside it — an error here is about the
          sign-in attempt, not part of the brand chrome above it. */}
      {error && (
        <div className="w-full max-w-sm rounded-md border border-negative bg-negative-bg px-3 py-2">
          <p className="font-ui text-small text-negative">{error}</p>
        </div>
      )}
    </div>
  );
}
