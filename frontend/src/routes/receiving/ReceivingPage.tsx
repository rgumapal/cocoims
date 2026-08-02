import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { apiGet, apiPost } from "@/api/client";
import type { Item, Location, Page, ReceivingLine } from "@/api/types";
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
  production_date: string;
}

// item_code prefilled empty (user must pick), qty empty (must type), but
// production_date defaults to today — the common case is receiving what
// just arrived, not backdating.
const emptyLine = (): LineDraft => ({ item_code: "", qty: "", production_date: todayLocalDate() });

function linesFromServer(saved: ReceivingLine[]): LineDraft[] {
  return saved.length > 0
    ? saved.map((l) => ({
        item_code: l.item_code,
        qty: formatQty(l.qty),
        production_date: l.production_date ?? todayLocalDate(),
      }))
    : [emptyLine()];
}

export default function ReceivingPage() {
  const { me } = useAuth();
  const queryClient = useQueryClient();

  const [locationCode, setLocationCode] = useState(() =>
    !me?.unrestricted && me?.location_scope.length === 1 ? me.location_scope[0]! : "",
  );
  const [businessDate, setBusinessDate] = useState(todayLocalDate);
  const [refDocId, setRefDocId] = useState("");
  const [confirmedByName, setConfirmedByName] = useState("");
  const [lines, setLines] = useState<LineDraft[]>([emptyLine()]);
  const [error, setError] = useState<string | null>(null);
  // Locked (read-only, "already saved") whenever the loaded day already
  // has entries on file — an explicit Edit click is what unlocks it, so a
  // saved day can't be nudged into a silent, half-noticed change. A fresh
  // day with nothing on file starts unlocked (there's nothing to protect
  // yet).
  const [isEditing, setIsEditing] = useState(true);
  // Guards Save/Cancel for a moment right after Edit is clicked. Edit and
  // Save render in the exact same screen position (Edit disappears the
  // instant isEditing flips true, Save appears there instead), so a fast
  // real double-click — the first click unlocking, the second landing on
  // the now-submit button before the user even sees the table changed —
  // silently resubmits unchanged data and relocks the table. From the
  // user's side that looks exactly like "clicking Edit did nothing."
  const [saveGuardActive, setSaveGuardActive] = useState(false);
  // Tracks which (branch, date) the table currently reflects, so a
  // background refetch doesn't clobber an in-progress edit — only sync
  // when the key itself changes (same pattern as ItemDetailPage/
  // UserDetailPage's "syncedFor").
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
  // by core.v_user_effective_scope regardless of whether the underlying
  // grant was branch-, area-, cluster- or route-level (see /auth/me), so
  // no separate "is this an area or a branch" handling is needed here.
  const availableLocations = (locations?.items ?? []).filter(
    (l) => me?.unrestricted || me?.location_scope.includes(l.location_code),
  );

  const receivingKey = locationCode && businessDate ? `${locationCode}|${businessDate}` : null;
  const { data: existingLines, isFetching: isLoadingExisting } = useQuery({
    queryKey: ["receiving", locationCode, businessDate],
    queryFn: () =>
      apiGet<ReceivingLine[]>(
        `/api/v1/receiving?location_code=${encodeURIComponent(locationCode)}&business_date=${businessDate}`,
      ),
    enabled: !!receivingKey,
  });

  // useEffect, not a render-time guard: this only needs to run once per
  // (branch, date), and doing it as a side effect (after render commits)
  // rather than during render keeps it clearly separated from isEditing's
  // other trigger (the Edit button's click handler) — the syncedFor check
  // still no-ops on every background refetch of the same key, so a new
  // existingLines array reference from a refetch never re-locks a day the
  // user is actively editing.
  useEffect(() => {
    if (!receivingKey || existingLines === undefined || receivingKey === syncedFor) return;
    setLines(linesFromServer(existingLines));
    setIsEditing(existingLines.length === 0);
    setSyncedFor(receivingKey);
  }, [receivingKey, existingLines, syncedFor]);

  const saveMutation = useMutation({
    mutationFn: () =>
      apiPost<ReceivingLine[]>("/api/v1/receiving", {
        business_date: businessDate,
        location_code: locationCode,
        ref_doc_id: refDocId || null,
        confirmed_by_name: confirmedByName || null,
        lines: lines
          .filter((l) => l.item_code && l.qty)
          .map((l) => ({
            item_code: l.item_code,
            qty: l.qty,
            production_date: l.production_date || null,
          })),
      }),
    onSuccess: (saved) => {
      setError(null);
      setLines(linesFromServer(saved));
      setIsEditing(false); // saved — lock back down until Edit is clicked again
      void queryClient.invalidateQueries({ queryKey: ["receiving", locationCode, businessDate] });
    },
    onError: (err) => setError(err instanceof Error ? err.message : "Receiving failed"),
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

  return (
    <div className="mx-auto max-w-3xl p-4">
      <PageHeader
        title="Receiving"
        description="Log a delivery as soon as it arrives. Reopen an earlier date to correct it — your change is recorded as an adjustment, the original entry is never lost."
      />

      <form
        onSubmit={(e) => {
          e.preventDefault();
          saveMutation.mutate();
        }}
        className="flex flex-col gap-4 p-4"
      >
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Field label="Branch" htmlFor="r_location">
            <Select
              id="r_location"
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
          <Field label="Business date" htmlFor="r_date">
            <Input
              id="r_date"
              type="date"
              required
              value={businessDate}
              onChange={(e) => setBusinessDate(e.target.value)}
            />
          </Field>
          <Field label="DR number (optional)" htmlFor="r_ref">
            <Input
              id="r_ref"
              value={refDocId}
              onChange={(e) => setRefDocId(e.target.value)}
              disabled={isSaved}
            />
          </Field>
        </div>

        <Field label="Received by (optional, if different from your own account)" htmlFor="r_confirmed_by">
          <Input
            id="r_confirmed_by"
            placeholder="e.g. the staff member who physically received it"
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

        {receivingKey ? (
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
                  <th className="w-28 px-3 py-2 text-left font-dense text-micro uppercase tracking-[0.06em] text-text-2">
                    Qty
                  </th>
                  <th className="w-40 px-3 py-2 text-left font-dense text-micro uppercase tracking-[0.06em] text-text-2">
                    Production date
                  </th>
                  <th className="px-3 py-2 text-left font-dense text-micro uppercase tracking-[0.06em] text-text-2">
                    Confirmed by
                  </th>
                  <th className="px-3 py-2 text-left font-dense text-micro uppercase tracking-[0.06em] text-text-2">
                    Last updated by
                  </th>
                  {isEditing && <th className="w-16 px-3 py-2" />}
                </tr>
              </thead>
              <tbody>
                {lines.map((line, i) => {
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
                      <td className="px-3 py-1.5">
                        <Input
                          type="date"
                          value={line.production_date}
                          onChange={(e) => updateLine(i, { production_date: e.target.value })}
                          disabled={!isEditing}
                          className="w-full"
                        />
                      </td>
                      <td className="px-3 py-1.5 font-ui text-small text-text-2">
                        {original?.confirmed_by_name ?? "—"}
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
                {saveMutation.isPending ? "Saving…" : "Save receiving"}
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
            Select a branch and business date to view or record receiving.
          </p>
        )}
      </form>
    </div>
  );
}
