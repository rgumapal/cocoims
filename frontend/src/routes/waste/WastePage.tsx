import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiGet, apiPost } from "@/api/client";
import type { Item, Location, Page, ReasonCode, WasteEntry } from "@/api/types";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Field, Input, Select } from "@/components/ui/Field";
import { PageHeader } from "@/components/ui/PageHeader";
import { formatDateTime, todayLocalDate } from "@/lib/date";
import { formatQty } from "@/lib/format";

interface DraftLine {
  key: number; // local-only identity, never sent to the server
  item_code: string;
  qty: string;
  reason_code: string;
  production_date: string;
}

let nextDraftKey = 1;
const emptyDraft = (): DraftLine => ({
  key: nextDraftKey++,
  item_code: "",
  qty: "",
  reason_code: "",
  production_date: "",
});

export default function WastePage() {
  const queryClient = useQueryClient();
  const [locationCode, setLocationCode] = useState("");
  const [businessDate, setBusinessDate] = useState(todayLocalDate);
  const [drafts, setDrafts] = useState<DraftLine[]>([]);
  const [error, setError] = useState<string | null>(null);

  const { data: locations } = useQuery({
    queryKey: ["locations-picker"],
    queryFn: () => apiGet<Page<Location>>("/api/v1/locations?limit=200"),
  });
  const { data: items } = useQuery({
    queryKey: ["items-picker"],
    queryFn: () => apiGet<Page<Item>>("/api/v1/items?limit=200"),
  });
  const { data: reasonCodes } = useQuery({
    queryKey: ["reason-codes"],
    queryFn: () => apiGet<ReasonCode[]>("/api/v1/reason-codes"),
  });
  const wasteReasons = reasonCodes?.filter((r) => r.category === "WASTE" && r.is_active) ?? [];

  // Whole day's waste for the branch — every item already reported, in one
  // table, not a one-item-at-a-time lookup (backend/app/api/v1/waste.py's
  // GET has no item_code filter applied here).
  const existingKey = locationCode && businessDate ? `${locationCode}|${businessDate}` : null;
  const {
    data: existingEntries,
    isFetching: isLoadingExisting,
  } = useQuery({
    queryKey: ["waste-entries", locationCode, businessDate],
    queryFn: () =>
      apiGet<WasteEntry[]>(
        `/api/v1/waste?location_code=${encodeURIComponent(locationCode)}&business_date=${businessDate}`,
      ),
    enabled: !!existingKey,
  });

  function invalidateExisting(): void {
    void queryClient.invalidateQueries({ queryKey: ["waste-entries", locationCode, businessDate] });
  }

  // One POST per new line — waste has no bulk endpoint the way Receiving
  // does, and it doesn't need one: each entry is its own independent fact
  // (a specific spoiled/damaged batch), not a net quantity to reconcile in
  // a single call.
  const saveMutation = useMutation({
    mutationFn: async () => {
      const complete = drafts.filter((d) => d.item_code && d.qty && d.reason_code);
      for (const line of complete) {
        await apiPost("/api/v1/waste", {
          business_date: businessDate,
          location_code: locationCode,
          item_code: line.item_code,
          qty: line.qty,
          reason_code: line.reason_code,
          production_date: line.production_date || null,
        });
      }
    },
    onSuccess: () => {
      setError(null);
      setDrafts([]);
      invalidateExisting();
    },
    onError: (err) => setError(err instanceof Error ? err.message : "Could not save one or more entries"),
  });

  const reverseMutation = useMutation({
    mutationFn: (movementId: number) => apiPost(`/api/v1/waste/${movementId}/reverse`),
    onSuccess: invalidateExisting,
    onError: (err) => setError(err instanceof Error ? err.message : "Could not remove that entry"),
  });

  function updateDraft(key: number, patch: Partial<DraftLine>): void {
    setDrafts(drafts.map((d) => (d.key === key ? { ...d, ...patch } : d)));
  }

  function removeDraft(key: number): void {
    setDrafts(drafts.filter((d) => d.key !== key));
  }

  const hasCompleteDraft = drafts.some((d) => d.item_code && d.qty && d.reason_code);

  return (
    <div className="mx-auto max-w-3xl p-4">
      <PageHeader
        title="Waste Log"
        description="Log stock that has to be written off — spoiled, expired, or damaged — with a required reason code so the loss is explainable, not just a number. Each entry writes a WASTE movement that reduces the branch's stock balance immediately."
      />

      <div className="flex flex-col gap-4 p-4">
        <div className="grid grid-cols-2 gap-4">
          <Field label="Branch" htmlFor="w_location">
            <Select
              id="w_location"
              required
              value={locationCode}
              onChange={(e) => {
                setLocationCode(e.target.value);
                setDrafts([]);
              }}
            >
              <option value="">Select…</option>
              {locations?.items
                .filter((l) => l.is_active)
                .map((l) => (
                  <option key={l.location_code} value={l.location_code}>
                    {l.location_code} — {l.location_name}
                  </option>
                ))}
            </Select>
          </Field>
          <Field label="Business date" htmlFor="w_date">
            <Input
              id="w_date"
              type="date"
              required
              value={businessDate}
              onChange={(e) => {
                setBusinessDate(e.target.value || todayLocalDate());
                setDrafts([]);
              }}
            />
          </Field>
        </div>

        {existingKey ? (
          <div>
            <div className="mb-2 flex items-center gap-2">
              <h2 className="font-ui text-h2 text-text">Items</h2>
              {isLoadingExisting && (
                <span className="font-ui text-micro text-text-3">Loading what's on file…</span>
              )}
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
                    <th className="px-3 py-2 text-left font-dense text-micro uppercase tracking-[0.06em] text-text-2">
                      Reason
                    </th>
                    <th className="w-40 px-3 py-2 text-left font-dense text-micro uppercase tracking-[0.06em] text-text-2">
                      Batch (optional)
                    </th>
                    <th className="px-3 py-2 text-left font-dense text-micro uppercase tracking-[0.06em] text-text-2">
                      Logged by
                    </th>
                    <th className="w-24 px-3 py-2" />
                  </tr>
                </thead>
                <tbody>
                  {existingEntries?.map((entry) => (
                    <tr key={entry.movement_id} className="border-t border-border">
                      <td className="px-3 py-1.5 font-ui text-body text-text">{entry.item_code}</td>
                      <td className="px-3 py-1.5 font-data text-body tabular-nums text-text">
                        {formatQty(entry.qty)}
                      </td>
                      <td className="px-3 py-1.5 font-ui text-body text-text-2">
                        {wasteReasons.find((r) => r.reason_code === entry.reason_code)?.label ??
                          entry.reason_code ??
                          "—"}
                      </td>
                      <td className="px-3 py-1.5 font-ui text-body text-text-2">
                        {entry.production_date ?? "—"}
                      </td>
                      <td className="px-3 py-1.5 font-ui text-small text-text-2">
                        {entry.created_by_full_name ?? "—"}
                        <span className="block text-micro text-text-3">
                          {formatDateTime(entry.created_at)}
                        </span>
                      </td>
                      <td className="px-3 py-1.5 text-right">
                        {entry.is_reversed ? (
                          <Badge tone="neutral">Removed</Badge>
                        ) : (
                          <button
                            type="button"
                            onClick={() => reverseMutation.mutate(entry.movement_id)}
                            disabled={reverseMutation.isPending}
                            className="font-ui text-small text-negative hover:underline disabled:opacity-50"
                          >
                            Remove
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}

                  {drafts.map((line) => {
                    const usedElsewhere = new Set(
                      drafts.filter((d) => d.key !== line.key).map((d) => d.item_code),
                    );
                    return (
                      <tr key={line.key} className="border-t border-border bg-surface-2">
                        <td className="px-3 py-1.5">
                          <Select
                            required
                            value={line.item_code}
                            onChange={(e) => updateDraft(line.key, { item_code: e.target.value })}
                            className="w-full"
                          >
                            <option value="">Select item…</option>
                            {items?.items
                              .filter((it) => it.item_code === line.item_code || !usedElsewhere.has(it.item_code))
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
                            min="0.001"
                            required
                            value={line.qty}
                            onChange={(e) => updateDraft(line.key, { qty: e.target.value })}
                            className="w-full font-data tabular-nums"
                          />
                        </td>
                        <td className="px-3 py-1.5">
                          <Select
                            required
                            value={line.reason_code}
                            onChange={(e) => updateDraft(line.key, { reason_code: e.target.value })}
                            className="w-full"
                          >
                            <option value="">Select a reason…</option>
                            {wasteReasons.map((r) => (
                              <option key={r.reason_code} value={r.reason_code}>
                                {r.label}
                              </option>
                            ))}
                          </Select>
                        </td>
                        <td className="px-3 py-1.5">
                          <Input
                            type="date"
                            value={line.production_date}
                            onChange={(e) => updateDraft(line.key, { production_date: e.target.value })}
                            className="w-full"
                          />
                        </td>
                        <td className="px-3 py-1.5 font-ui text-small text-text-3">Not saved yet</td>
                        <td className="px-3 py-1.5 text-right">
                          <button
                            type="button"
                            onClick={() => removeDraft(line.key)}
                            className="font-ui text-small text-negative hover:underline"
                          >
                            Discard
                          </button>
                        </td>
                      </tr>
                    );
                  })}

                  {(!existingEntries || existingEntries.length === 0) && drafts.length === 0 && (
                    <tr>
                      <td colSpan={6} className="px-3 py-6 text-center font-ui text-small text-text-3">
                        Nothing logged yet for this branch and date.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            <div className="mt-2 flex items-center gap-2">
              <Button type="button" onClick={() => setDrafts([...drafts, emptyDraft()])}>
                Add Item
              </Button>
              {drafts.length > 0 && (
                <Button
                  type="button"
                  variant="primary"
                  disabled={!hasCompleteDraft || saveMutation.isPending}
                  onClick={() => saveMutation.mutate()}
                >
                  {saveMutation.isPending ? "Saving…" : "Save new items"}
                </Button>
              )}
            </div>

            {error && <p className="mt-2 font-ui text-small text-negative">{error}</p>}
          </div>
        ) : (
          <p className="font-ui text-small text-text-2">
            Select a branch and business date to view or log waste.
          </p>
        )}
      </div>
    </div>
  );
}
