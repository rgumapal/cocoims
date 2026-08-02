/** "50.000" -> "50", "50.500" -> "50.5" — a NUMERIC(12,3) column's stored
 * scale is a storage detail, not something a store clerk (or anyone
 * reading a quantity in this UI) needs to see. Use this for every item
 * quantity rendered anywhere in the app; never show the raw Decimal
 * string directly. Non-numeric input (e.g. an already-formatted string)
 * passes through unchanged rather than becoming "NaN".
 */
export function formatQty(qty: string | number): string {
  const n = Number(qty);
  return Number.isFinite(n) ? String(n) : String(qty);
}
