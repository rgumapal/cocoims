// Shared by client.ts and auth.ts (which can't import from each other —
// client.ts already imports from auth.ts, so this avoids a circular
// import). Empty by default: dev relies on vite.config.ts's /api proxy, so
// a plain relative path already reaches the backend. A deployed build
// (frontend and backend on different origins) sets VITE_API_BASE_URL at
// build time to the backend's real URL.
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
