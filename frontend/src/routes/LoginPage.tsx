import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/auth/AuthContext";
import { signInWithGoogle } from "@/auth/firebase";
import { Button } from "@/components/ui/Button";
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
    <div className="flex h-screen items-center justify-center bg-bg p-4">
      <div className="w-full max-w-sm rounded-lg border border-border bg-surface p-6 shadow-2">
        <div className="mb-6 flex items-center gap-2">
          <span className="h-3 w-3 rounded-sm bg-accent" aria-hidden="true" />
          <span className="font-ui text-h1 text-text">Cocopan IMS</span>
        </div>

        <div className="flex flex-col gap-4">
          {error && <p className="font-ui text-small text-negative">{error}</p>}

          <Button
            type="button"
            variant="primary"
            onClick={() => void handleGoogleSignIn()}
            disabled={isGoogleSubmitting}
            className="flex w-full items-center justify-center gap-2"
          >
            <GoogleIcon />
            {isGoogleSubmitting ? "Signing in…" : "Sign in with Google"}
          </Button>
        </div>
      </div>
    </div>
  );
}
