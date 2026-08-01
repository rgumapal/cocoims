import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/auth/AuthContext";
import { signInWithEmailPassword, signInWithGoogle } from "@/auth/firebase";
import { Button } from "@/components/ui/Button";
import { Field, Input } from "@/components/ui/Field";

export default function LoginPage() {
  const { loginWithFirebase, isLoggedIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isGoogleSubmitting, setIsGoogleSubmitting] = useState(false);

  if (isLoggedIn) {
    const from = (location.state as { from?: Location })?.from?.pathname ?? "/dashboard";
    return <Navigate to={from} replace />;
  }

  // Both paths converge on the same Firebase token exchange (SPEC §16 open
  // item #11) — email+password and Google are just two ways to obtain a
  // Firebase ID token, not two different backend auth systems.
  async function handleSubmit(e: React.FormEvent): Promise<void> {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      const idToken = await signInWithEmailPassword(email, password);
      await loginWithFirebase(idToken);
      navigate("/dashboard", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setIsSubmitting(false);
    }
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
      <form
        onSubmit={(e) => void handleSubmit(e)}
        className="w-full max-w-sm rounded-lg border border-border bg-surface p-6 shadow-2"
      >
        <div className="mb-6 flex items-center gap-2">
          <span className="h-3 w-3 rounded-sm bg-accent" aria-hidden="true" />
          <span className="font-ui text-h1 text-text">Cocopan IMS</span>
        </div>

        <div className="flex flex-col gap-4">
          <Field label="Email" htmlFor="email">
            <Input
              id="email"
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </Field>
          <Field label="Password" htmlFor="password">
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </Field>

          {error && <p className="font-ui text-small text-negative">{error}</p>}

          <Button
            type="submit"
            variant="primary"
            disabled={isSubmitting || isGoogleSubmitting}
            className="w-full"
          >
            {isSubmitting ? "Signing in…" : "Sign in"}
          </Button>

          <div className="flex items-center gap-3">
            <div className="h-px flex-1 bg-border" />
            <span className="font-ui text-small text-text-3">or</span>
            <div className="h-px flex-1 bg-border" />
          </div>

          <Button
            type="button"
            onClick={() => void handleGoogleSignIn()}
            disabled={isSubmitting || isGoogleSubmitting}
            className="w-full"
          >
            {isGoogleSubmitting ? "Signing in…" : "Sign in with Google"}
          </Button>
        </div>
      </form>
    </div>
  );
}
