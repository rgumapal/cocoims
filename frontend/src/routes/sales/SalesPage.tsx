import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { apiGet, apiPost } from "@/api/client";
import type { Item, Location, Page, SalesLine } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Field, Input, Select } from "@/components/ui/Field";
import { PageHeader } from "@/components/ui/PageHeader";
import { formatDateTime, todayLocalDate } from "@/lib/date";
import { formatQty } from "@/lib/format";

interface LineDraft {
  item_code: string;
  qty: string;
  sold_out: boolean;
}

const emptyLine = (): LineDraft => ({ item_code: "", qty: "", sold_out: false });

function formatMoney(value: string | null): string {
  if (value === null) return "—";
  const n = Number(value);
  return Number.isFinite(n) ? `₱${n.toFixed(2)}` : "—";
}

function linesFromServer(saved: SalesLine[]): LineDraft[] {
  return saved.length > 0
    ? saved.map((l) => ({ item_code: l.item_code, qty: formatQty(l.qty), sold_out: l.sold_out }))
    : [emptyLine()];
}

export default function SalesPage() {
  const { me } = useAuth();
  const queryClient = useQueryClient();

  const [locationCode, setLocationCode] = useState(() =>
    !me?.unrestricted && me?.location_scope.length === 1 ? me.location_scope[0]! : "",
  );
  const [businessDate, setBusinessDate] = useState(todayLocalDate);
  const [confirmedByName, setConfirmedByName] = useState("");
  const [lines, setLines] = useState<LineDraft[]>([emptyLine()]);
  const [error, setError] = useState<string | null>(null);
  // Locked ("already saved") whenever the loaded day already has entries
  // on file — an explicit Edit click unlocks it. A fresh day with nothing
  // on file starts unlocked. Same pattern as ReceivingPage.
  const [isEditing, setIsEditing] = useState(true);
  // Guards Save/Cancel for a moment right after Edit is clicked — see
  // ReceivingPage's identical guard for why: Edit and Save render in the
  // exact same screen position, so a fast real double-click can land its
  // second click on the newly-appeared submit button, silently resubmitting
  // unchanged data and relocking the table before the user even sees it
  // unlock.
  const [saveGuardActive, setSaveGuardActive] = useState(false);
  const [syncedFor, setSyncedFor] = useState<string | null>(null);

  const { data: locations } = useQuery({
    queryKey: ["locations-picker"],
    queryFn: () => apiGet<Page<Location>>("/api/v1/locations?limit=200"),
  });
  const { data: items } = useQuery({
    queryKey: ["items-picker"],
    queryFn: () => apiGet<Page<Item>>("/api/v1/items?limit=200"),
  });

  // sys_admin (unrestricted) sees every branch; anyone else sees only
  // their effective scope — already flattened to individual branch codes
  // regardless of whether the underlying grant was branch-, area-,
  // cluster- or route-level (see /auth/me).
  const availableLocations = (locations?.items ?? []).filter(
    (l) => me?.unrestricted || me?.location_scope.includes(l.location_code),
  );

  const salesKey = locationCode && businessDate ? `${locationCode}|${businessDate}` : null;
  const { data: existingLines, isFetching: isLoadingExisting } = useQuery({
    queryKey: ["sales", locationCode, businessDate],
    queryFn: () =>
      apiGet<SalesLine[]>(
        `/api/v1/sales?location_code=${encodeURIComponent(locationCode)}&business_date=${businessDate}`,
      ),
    enabled: !!salesKey,
  });

  // useEffect, not a render-time guard — keeps the sync cleanly separate
  // from isEditing's other trigger (the Edit button's click handler); the
  // syncedFor check still no-ops on every background refetch of the same
  // key, so a new existingLines array reference never re-locks a day the
  // user is actively editing.
  useEffect(() => {
    if (!salesKey || existingLines === undefined || salesKey === syncedFor) return;
    setLines(linesFromServer(existingLines));
    setIsEditing(existingLines.length === 0);
    setSyncedFor(salesKey);
  }, [salesKey, existingLines, syncedFor]);

  const saveMutation = useMutation({
    mutationFn: () =>
      apiPost<SalesLine[]>("/api/v1/sales", {
        business_date: businessDate,
        location_code: locationCode,
        confirmed_by_name: confirmedByName || null,
        lines: lines
          .filter((l) => l.item_code && l.qty)
          .map((l) => ({ item_code: l.item_code, qty: l.qty, sold_out: l.sold_out })),
      }),
    onSuccess: (saved) => {
      setError(null);
      setLines(linesFromServer(saved));
      setIsEditing(false);
      void queryClient.invalidateQueries({ queryKey: ["sales", locationCode, businessDate] });
    },
    onError: (err) => setError(err instanceof Error ? err.message : "Could not record sales"),
  });

  function updateLine(index: number, patch: Partial<LineDraft>): void {
    setLines(lines.map((l, i) => (i === index ? { ...l, ...patch } : l)));
  }

  function removeLine(index: number): void {
    const remaining = lines.filter((_, i) => i !== index);
    setLines(remaining.length > 0 ? remaining : [emptyLine()]);
  }

  function cancelEditing(): void {
    setLines(linesFromServer(existingLines ?? []));
    setError(null);
    setIsEditing(false);
  }

  function startEditing(): void {
    setIsEditing(true);
    setSaveGuardActive(true);
    window.setTimeout(() => setSaveGuardActive(false), 400);
  }

  const usedItemCodes = new Set(lines.map((l) => l.item_code).filter(Boolean));
  const isSaved = !isEditing && (existingLines?.length ?? 0) > 0;

  // Price for display: falls back to the item master's network price
  // (items query, already loaded) so a newly-picked line prices itself
  // immediately, then prefers the branch-effective price from
  // existingLines once that's loaded — v_effective_price resolves a
  // branch override over the network price, so it's the more accurate
  // number whenever it's available.
  const priceByItem = new Map<string, string | null>();
  for (const it of items?.items ?? []) {
    if (it.network_srp !== null) priceByItem.set(it.item_code, it.network_srp);
  }
  for (const l of existingLines ?? []) {
    priceByItem.set(l.item_code, l.unit_price);
  }
  const activeLines = lines.filter((l) => l.item_code && l.qty);
  const totalItemCount = activeLines.length;
  const totalQty = activeLines.reduce((sum, l) => sum + (Number(l.qty) || 0), 0);
  const totalSales = activeLines.reduce((sum, l) => {
    const price = priceByItem.get(l.item_code);
    return price !== null && price !== undefined ? sum + (Number(l.qty) || 0) * Number(price) : sum;
  }, 0);

  return (
    <div className="mx-auto max-w-3xl p-4">
      <PageHeader
        title="Sales"
        description="Log what sold at this branch today. Reopen an earlier date to correct it — your change is recorded as an adjustment, the original entry is never lost."
      />

      <form
        onSubmit={(e) => {
          e.preventDefault();
          saveMutation.mutate();
        }}
        className="flex flex-col gap-4 p-4"
      >
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Branch" htmlFor="s_location">
            <Select
              id="s_location"
              required
              value={locationCode}
              onChange={(e) => setLocationCode(e.target.value)}
              disabled={!me?.unrestricted && availableLocations.length <= 1}
            >
              <option value="">Select…</option>
              {availableLocations.map((l) => (
                <option key={l.location_code} value={l.location_code}>
                  {l.location_code} — {l.location_name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Business date" htmlFor="s_date">
            <Input
              id="s_date"
              type="date"
              required
              value={businessDate}
              onChange={(e) => setBusinessDate(e.target.value)}
            />
          </Field>
        </div>

        <Field label="Cashier (optional, if different from your own account)" htmlFor="s_confirmed_by">
          <Input
            id="s_confirmed_by"
            placeholder="e.g. the cashier who rang these up"
            value={confirmedByName}
            onChange={(e) => setConfirmedByName(e.target.value)}
            className="max-w-sm"
            disabled={isSaved}
          />
        </Field>
        {me && (
          <p className="-mt-2 font-ui text-micro text-text-3">
            Recorded under your account ({me.full_name}) regardless of who you name above.
          </p>
        )}

        {salesKey ? (
        <>
        <div>
          <div className="mb-2 flex items-center gap-2">
            <h2 className="font-ui text-h2 text-text">Items</h2>
            {isLoadingExisting && (
              <span className="font-ui text-micro text-text-3">Loading what's on file…</span>
            )}
            {isSaved && <Badge tone="positive">Saved</Badge>}
          </div>
          <div className="overflow-hidden rounded-md border border-border">
            <table className="w-full border-collapse">
              <thead className="bg-surface-2">
                <tr>
                  <th className="px-3 py-2 text-left font-dense text-micro uppercase tracking-[0.06em] text-text-2">
                    Item
                  </th>
                  <th className="w-24 px-3 py-2 text-left font-dense text-micro uppercase tracking-[0.06em] text-text-2">
                    Qty sold
                  </th>
                  <th className="w-24 px-3 py-2 text-left font-dense text-micro uppercase tracking-[0.06em] text-text-2">
                    Price
                  </th>
                  <th className="w-28 px-3 py-2 text-left font-dense text-micro uppercase tracking-[0.06em] text-text-2">
                    Total
                  </th>
                  <th className="px-3 py-2 text-left font-dense text-micro uppercase tracking-[0.06em] text-text-2">
                    Ran out?
                  </th>
                  <th className="px-3 py-2 text-left font-dense text-micro uppercase tracking-[0.06em] text-text-2">
                    Last updated by
                  </th>
                  {isEditing && <th className="w-16 px-3 py-2" />}
                </tr>
              </thead>
              <tbody>
                {lines.map((line, i) => {
                  const priced = priceByItem.get(line.item_code);
                  const lineTotal =
                    priced !== undefined && priced !== null && line.qty
                      ? (Number(line.qty) * Number(priced)).toFixed(2)
                      : null;
                  const original = existingLines?.find((l) => l.item_code === line.item_code);
                  return (
                    <tr key={i} className="border-t border-border">
                      <td className="px-3 py-1.5">
                        <Select
                          required
                          value={line.item_code}
                          onChange={(e) => updateLine(i, { item_code: e.target.value })}
                          disabled={!isEditing}
                          className="w-full"
                        >
                          <option value="">Select…</option>
                          {items?.items
                            .filter((it) => it.item_code === line.item_code || !usedItemCodes.has(it.item_code))
                            .map((it) => (
                              <option key={it.item_code} value={it.item_code}>
                                {it.item_code} — {it.display_name}
                              </option>
                            ))}
                        </Select>
                      </td>
                      <td className="px-3 py-1.5">
                        <Input
                          type="number"
                          step="0.001"
                          min="0"
                          required
                          value={line.qty}
                          onChange={(e) => updateLine(i, { qty: e.target.value })}
                          disabled={!isEditing}
                          className="w-full font-data tabular-nums"
                        />
                      </td>
                      <td className="px-3 py-1.5 font-data text-body tabular-nums text-text-2">
                        {priced !== undefined ? formatMoney(priced) : "—"}
                      </td>
                      <td className="px-3 py-1.5 font-data text-body tabular-nums text-text">
                        {lineTotal !== null ? formatMoney(lineTotal) : "—"}
                      </td>
                      <td className="px-3 py-1.5">
                        <label className="flex items-center gap-1.5 font-ui text-body text-text">
                          <input
                            type="checkbox"
                            checked={line.sold_out}
                            onChange={(e) => updateLine(i, { sold_out: e.target.checked })}
                            disabled={!isEditing}
                          />
                          Ran out
                        </label>
                      </td>
                      <td className="px-3 py-1.5 font-ui text-small text-text-2">
                        {original ? (
                          <>
                            {original.confirmed_by_full_name ?? "—"}
                            <span className="block text-micro text-text-3">
                              {formatDateTime(original.updated_at)}
                            </span>
                          </>
                        ) : (
                          "—"
                        )}
                      </td>
                      {isEditing && (
                        <td className="px-3 py-1.5 text-right">
                          <button
                            type="button"
                            onClick={() => removeLine(i)}
                            className="font-ui text-small text-negative hover:underline"
                          >
                            Remove
                          </button>
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
              {activeLines.length > 0 && (
                <tfoot className="border-t border-border-strong bg-surface-2">
                  <tr>
                    <td className="px-3 py-2 font-ui text-small font-medium text-text">
                      {totalItemCount} item{totalItemCount === 1 ? "" : "s"}
                    </td>
                    <td className="px-3 py-2 font-data text-body font-medium tabular-nums text-text">
                      {formatQty(String(totalQty))}
                    </td>
                    <td />
                    <td className="px-3 py-2 font-data text-body font-medium tabular-nums text-text">
                      {formatMoney(totalSales.toFixed(2))}
                    </td>
                    <td colSpan={isEditing ? 3 : 2} />
                  </tr>
                </tfoot>
              )}
            </table>
          </div>
          {isEditing && (
            <Button type="button" onClick={() => setLines([...lines, emptyLine()])} className="mt-2">
              Add Item
            </Button>
          )}
        </div>

        {error && <p className="font-ui text-small text-negative">{error}</p>}

        <div className="flex items-center gap-2">
          {isSaved ? (
            <Button type="button" variant="primary" onClick={startEditing}>
              Edit
            </Button>
          ) : (
            <>
              <Button type="submit" variant="primary" disabled={saveMutation.isPending || saveGuardActive}>
                {saveMutation.isPending ? "Saving…" : "Record sales"}
              </Button>
              {(existingLines?.length ?? 0) > 0 && (
                <Button
                  type="button"
                  onClick={cancelEditing}
                  disabled={saveMutation.isPending || saveGuardActive}
                >
                  Cancel
                </Button>
              )}
            </>
          )}
        </div>
        </>
        ) : (
          <p className="font-ui text-small text-text-2">
            Select a branch and business date to view or record sales.
          </p>
        )}
      </form>
    </div>
  );
}
