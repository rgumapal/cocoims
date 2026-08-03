/** Today's date as YYYY-MM-DD in the *browser's local* calendar day, not
 * UTC's. `new Date().toISOString()` is always UTC — for a Philippines
 * user (UTC+8), any time between midnight and 8am local is still "the
 * previous day" in UTC, so a business-date field defaulted via
 * toISOString silently opens on the wrong day during exactly the hours a
 * bakery's early shift is using it. Every "business date defaults to
 * today" field in this app should use this, not toISOString().slice(0,10).
 */
export function todayLocalDate(): string {
  const d = new Date();
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

/** `daysAgo` days before today, in the browser's local calendar — for
 * filters that default to a trailing window (e.g. Audit Logs' "last two
 * days") rather than a single day. Same local-day reasoning as
 * todayLocalDate() above. */
export function daysAgoLocalDate(daysAgo: number): string {
  const d = new Date();
  d.setDate(d.getDate() - daysAgo);
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

/** Renders an ISO timestamp (e.g. stock_movement.created_at) in the
 * browser's local time zone, for audit-trail display ("last updated at") —
 * short enough to sit inline in a dense table cell. Returns "—" for null,
 * matching this app's NULL-means-"not counted" display convention rather
 * than showing an empty cell. */
export function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}
