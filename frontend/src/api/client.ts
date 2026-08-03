// The one data-fetching path in this app (CLAUDE.md: "one obvious way to
// do each thing... no ad hoc fetch/useEffect"). Every component that needs
// server data goes through TanStack Query, and every TanStack Query
// queryFn/mutationFn goes through apiFetch below — so auth headers, 401
// retry-once-after-refresh, and error shaping all live in one place.
import { clearTokens, getAccessToken, refreshTokens } from "./auth";
import { API_BASE_URL } from "./config";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function extractErrorMessage(response: Response): Promise<string> {
  // FastAPI's HTTPException -> {"detail": "..."}; a validation error (422)
  // -> {"detail": [{"msg": "...", ...}, ...]}. Handle both rather than
  // showing the user a raw JSON blob (SPEC §12.6 rule: never a raw error).
  const body = (await response.json().catch(() => null)) as
    | { detail?: string | { msg: string }[] }
    | null;
  if (!body?.detail) return response.statusText;
  if (typeof body.detail === "string") return body.detail;
  return body.detail.map((e) => e.msg).join("; ");
}

async function doFetch(path: string, init: RequestInit): Promise<Response> {
  const token = getAccessToken();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  return fetch(`${API_BASE_URL}${path}`, { ...init, headers });
}

/** Typed fetch wrapper for every API call. On a 401 (expired access
 * token), tries exactly one silent refresh + retry before giving up —
 * more than one would risk a loop if the refresh token is also invalid.
 */
export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response = await doFetch(path, init);

  if (response.status === 401 && getAccessToken()) {
    const newToken = await refreshTokens();
    if (newToken) {
      response = await doFetch(path, init);
    } else {
      clearTokens();
      window.location.assign("/login");
      throw new ApiError(401, "Session expired");
    }
  }

  if (!response.ok) {
    throw new ApiError(response.status, await extractErrorMessage(response));
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function apiGet<T>(path: string): Promise<T> {
  return apiFetch<T>(path, { method: "GET" });
}

export function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return apiFetch<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined });
}

export function apiPatch<T>(path: string, body: unknown): Promise<T> {
  return apiFetch<T>(path, { method: "PATCH", body: JSON.stringify(body) });
}

export function apiDelete<T>(path: string): Promise<T> {
  return apiFetch<T>(path, { method: "DELETE" });
}

/** For endpoints that return a file (e.g. CSV export) rather than JSON —
 * apiFetch always calls response.json(), which would fail on these, so
 * this is a separate path that returns the raw Blob plus the filename the
 * server suggested via Content-Disposition. Auth still goes through
 * doFetch/refreshTokens the normal way — a plain `<a href>` to the API
 * wouldn't carry the Bearer token, since auth here is a header, not a
 * cookie. */
export async function apiGetFile(path: string): Promise<{ blob: Blob; filename: string }> {
  let response = await doFetch(path, { method: "GET" });

  if (response.status === 401 && getAccessToken()) {
    const newToken = await refreshTokens();
    if (newToken) {
      response = await doFetch(path, { method: "GET" });
    } else {
      clearTokens();
      window.location.assign("/login");
      throw new ApiError(401, "Session expired");
    }
  }

  if (!response.ok) {
    throw new ApiError(response.status, await extractErrorMessage(response));
  }

  const disposition = response.headers.get("Content-Disposition") ?? "";
  const match = /filename="?([^"]+)"?/.exec(disposition);
  const filename = match?.[1] ?? "download";
  return { blob: await response.blob(), filename };
}
