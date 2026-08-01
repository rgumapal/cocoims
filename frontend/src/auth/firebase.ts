// Google sign-in via Firebase (see backend/app/auth/router.py's
// firebase_login docstring). Firebase only handles proving "this really is
// this Google account"; the resulting ID token is exchanged once for this
// app's own JWT pair at /api/v1/auth/firebase, so every other part of the
// app (permission checks, token refresh, RLS scope) stays on the existing
// JWT machinery unchanged.
import { initializeApp } from "firebase/app";
import {
  GoogleAuthProvider,
  getAuth,
  signInWithEmailAndPassword,
  signInWithPopup,
} from "firebase/auth";

const app = initializeApp({
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
});

const auth = getAuth(app);
const googleProvider = new GoogleAuthProvider();
// Without this, Google silently reuses whichever account is already
// signed into the browser instead of showing the picker — meaning
// there's no way to sign in as a *different* email once one account has
// signed in once. Forcing the picker every time is what makes "Other
// Email" actually possible from this one button.
googleProvider.setCustomParameters({ prompt: "select_account" });

/** Opens the Google account picker, returns a Firebase ID token on success.
 * Throws (with Firebase's own error, e.g. auth/popup-closed-by-user) if
 * the user cancels — callers should catch and show a normal error, not
 * treat it as a bug. */
export async function signInWithGoogle(): Promise<string> {
  const credential = await signInWithPopup(auth, googleProvider);
  return credential.user.getIdToken();
}

/** Throws Firebase's own error (e.g. auth/wrong-password, auth/user-not-found)
 * on a bad credential — callers should catch and show a normal error, not
 * treat it as a bug. */
export async function signInWithEmailPassword(email: string, password: string): Promise<string> {
  const credential = await signInWithEmailAndPassword(auth, email, password);
  return credential.user.getIdToken();
}
