// Token storage and the login/refresh calls themselves. Deliberately not
// using TanStack Query here — these run *before* a query client has any
// user context to key on, and client.ts's 401-retry logic depends on
// calling refreshTokens() directly, not through the query cache.
import { API_BASE_URL } from "./config";

const ACCESS_TOKEN_KEY = "cocoims.access_token";
const REFRESH_TOKEN_KEY = "cocoims.refresh_token";

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

function setTokens(accessToken: string, refreshToken: string): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
  localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

export function isLoggedIn(): boolean {
  return getAccessToken() !== null;
}

interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

async function loginRequest(path: string, body: unknown, failureMessage: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const errBody = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(errBody?.detail ?? failureMessage);
  }
  const tokens = (await response.json()) as TokenResponse;
  setTokens(tokens.access_token, tokens.refresh_token);
}

/** Legacy bcrypt/JWT login (backend/app/auth/router.py's /login) — left in
 * place as a dormant fallback but no longer called by the UI. Firebase
 * (email+password and Google both) is now the one sign-in path; see
 * loginWithFirebase below. */
export async function login(email: string, password: string): Promise<void> {
  await loginRequest("/api/v1/auth/login", { email, password }, "Login failed");
}

/** Exchanges a Firebase ID token — obtained from either
 * auth/firebase.ts's signInWithGoogle() or signInWithEmailPassword() — for
 * this app's own JWT pair. One backend endpoint for both, since the token
 * itself already says which provider was used; see
 * backend/app/auth/router.py's firebase_login docstring for why an
 * unrecognized email is rejected rather than auto-provisioned. */
export async function loginWithFirebase(idToken: string): Promise<void> {
  await loginRequest("/api/v1/auth/firebase", { id_token: idToken }, "Sign-in failed");
}

export async function logout(): Promise<void> {
  const token = getAccessToken();
  clearTokens();
  if (token) {
    // Best-effort — see backend's /auth/logout docstring: stateless JWTs,
    // no server-side revocation in this phase, so this is advisory. Never
    // block the UI logout on it.
    await fetch(`${API_BASE_URL}/api/v1/auth/logout`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    }).catch(() => undefined);
  }
}

/** Returns the new access token on success, or null if the refresh token
 * is itself invalid/expired — callers treat null as "must log in again". */
export async function refreshTokens(): Promise<string | null> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return null;

  const response = await fetch(`${API_BASE_URL}/api/v1/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!response.ok) {
    clearTokens();
    return null;
  }
  const tokens = (await response.json()) as TokenResponse;
  setTokens(tokens.access_token, tokens.refresh_token);
  return tokens.access_token;
}
