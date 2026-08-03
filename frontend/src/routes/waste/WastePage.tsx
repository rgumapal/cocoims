import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiGet, apiPost } from "@/api/client";
import type { Item, Location, Page, ReasonCode, StockMovement, WasteEntry } from "@/api/types";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Field, Input, Select } from "@/components/ui/Field";
import { PageHeader } from "@/components/ui/PageHeader";
import { formatDateTime, todayLocalDate } from "@/lib/date";
import { formatQty } from "@/lib/format";

export default function WastePage() {
  const queryClient = useQueryClient();
  const [locationCode, setLocationCode] = useState("");
  const [itemCode, setItemCode] = useState("");
  const [businessDate, setBusinessDate] = useState(todayLocalDate);
  const [qty, setQty] = useState("");
  const [reasonCode, setReasonCode] = useState("");
  const [productionDate, setProductionDate] = useState("");
  const [error, setError] = useState<string | null>(null);
  // Accumulates across submissions for this session (newest first) — see
  // ReceivingPage's identical pattern for why this replaces a one-line
  // confirmation message.
  const [recentEntries, setRecentEntries] = useState<StockMovement[]>([]);

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

  // Once branch, item and date are all picked, check what's already been
  // reported for that exact combination — a second entry is often
  // legitimate (a different reason, a separate batch), but it should never
  // be a surprise duplicate someone didn't know was already on file.
  const existingKey =
    locationCode && itemCode && businessDate ? `${locationCode}|${itemCode}|${businessDate}` : null;
  const { data: existingEntries, isFetching: isLoadingExisting } = useQuery({
    queryKey: ["waste-entries", locationCode, itemCode, businessDate],
    queryFn: () =>
      apiGet<WasteEntry[]>(
        `/api/v1/waste?location_code=${encodeURIComponent(locationCode)}` +
          `&item_code=${encodeURIComponent(itemCode)}&business_date=${businessDate}`,
      ),
    enabled: !!existingKey,
  });

  function invalidateExisting(): void {
    void queryClient.invalidateQueries({ queryKey: ["waste-entries", locationCode, itemCode, businessDate] });
  }

  const submitMutation = useMutation({
    mutationFn: () =>
      apiPost<StockMovement>("/api/v1/waste", {
        business_date: businessDate,
        location_code: locationCode,
        item_code: itemCode,
        qty,
        reason_code: reasonCode,
        production_date: productionDate || null,
      }),
    onSuccess: (movement) => {
      setError(null);
      setRecentEntries((prev) => [movement, ...prev]);
      setQty("");
      setReasonCode("");
      setProductionDate("");
      invalidateExisting();
    },
    onError: (err) => setError(err instanceof Error ? err.message : "Could not record waste"),
  });

  const reverseMutation = useMutation({
    mutationFn: (movementId: number) => apiPost(`/api/v1/waste/${movementId}/reverse`),
    onSuccess: invalidateExisting,
    onError: (err) => setError(err instanceof Error ? err.message : "Could not reverse that entry"),
  });

  return (
    <div className="mx-auto max-w-lg p-4">
      <PageHeader
        title="Waste Log"
        description="Log stock that has to be written off — spoiled, expired, or damaged — with a required reason code so the loss is explainable, not just a number. Each entry writes a WASTE movement that reduces the branch's stock balance immediately."
      />

      <form
        onSubmit={(e) => {
          e.preventDefault();
          submitMutation.mutate();
        }}
        className="flex flex-col gap-4 p-4"
      >
        <Field label="Branch" htmlFor="w_location">
          <Select
            id="w_location"
            required
            value={locationCode}
            onChange={(e) => setLocationCode(e.target.value)}
          >
            <option value="">Select…</option>
            {locations?.items.map((l) => (
              <option key={l.location_code} value={l.location_code}>
                {l.location_code} — {l.location_name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Item" htmlFor="w_item">
          <Select
            id="w_item"
            required
            value={itemCode}
            onChange={(e) => setItemCode(e.target.value)}
          >
            <option value="">Select…</option>
            {items?.items.map((it) => (
              <option key={it.item_code} value={it.item_code}>
                {it.item_code} — {it.display_name}
              </option>
            ))}
          </Select>
        </Field>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Business date" htmlFor="w_date">
            <Input
              id="w_date"
              type="date"
              required
              value={businessDate}
              onChange={(e) => setBusinessDate(e.target.value)}
            />
          </Field>
          <Field label="Quantity wasted" htmlFor="w_qty">
            <Input
              id="w_qty"
              type="number"
              step="0.001"
              min="0.001"
              required
              value={qty}
              onChange={(e) => setQty(e.target.value)}
            />
          </Field>
        </div>

        {existingKey && (
          <div className="rounded-md border border-border bg-surface-2 p-3">
            <h2 className="mb-2 font-ui text-small font-medium text-text-2">
              Already reported for {itemCode} at {locationCode} on {businessDate}
            </h2>
            {isLoadingExisting ? (
              <p className="font-ui text-small text-text-3">Checking…</p>
            ) : !existingEntries || existingEntries.length === 0 ? (
              <p className="font-ui text-small text-text-3">Nothing logged yet — this would be the first entry.</p>
            ) : (
              <ul className="flex flex-col gap-1.5">
                {existingEntries.map((entry) => (
                  <li key={entry.movement_id} className="flex items-center justify-between gap-2">
                    <span className="font-ui text-small text-text">
                      <span className="font-data tabular-nums">{formatQty(entry.qty)}</span>{" "}
                      {wasteReasons.find((r) => r.reason_code === entry.reason_code)?.label ??
                        entry.reason_code ??
                        "—"}
                      {entry.created_by_full_name && (
                        <span className="text-text-3"> — logged by {entry.created_by_full_name}</span>
                      )}
                      <span className="text-text-3"> ({formatDateTime(entry.created_at)})</span>
                    </span>
                    {entry.is_reversed ? (
                      <Badge tone="neutral">Reversed</Badge>
                    ) : (
                      <button
                        type="button"
                        onClick={() => reverseMutation.mutate(entry.movement_id)}
                        disabled={reverseMutation.isPending}
                        className="shrink-0 font-ui text-small text-negative hover:underline disabled:opacity-50"
                      >
                        Reverse
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        <Field label="Reason" htmlFor="w_reason">
          <Select
            id="w_reason"
            required
            value={reasonCode}
            onChange={(e) => setReasonCode(e.target.value)}
          >
            <option value="">Select a reason…</option>
            {wasteReasons.map((r) => (
              <option key={r.reason_code} value={r.reason_code}>
                {r.label}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Which batch? (production date, optional)" htmlFor="w_pd">
          <Input
            id="w_pd"
            type="date"
            value={productionDate}
            onChange={(e) => setProductionDate(e.target.value)}
          />
        </Field>

        {error && <p className="font-ui text-small text-negative">{error}</p>}

        <div>
          <Button type="submit" variant="primary" disabled={submitMutation.isPending}>
            {submitMutation.isPending ? "Recording…" : "Record waste"}
          </Button>
        </div>
      </form>

      {recentEntries.length > 0 && (
        <div className="border-t border-border p-4">
          <h2 className="mb-2 font-ui text-h2 text-text">Logged this session</h2>
          <div className="overflow-hidden rounded-md border border-border">
            <table className="w-full border-collapse">
              <thead className="bg-surface-2">
                <tr>
                  <th className="px-3 py-2 text-left font-dense text-micro uppercase tracking-[0.06em] text-text-2">Item</th>
                  <th className="px-3 py-2 text-left font-dense text-micro uppercase tracking-[0.06em] text-text-2">Qty</th>
                  <th className="px-3 py-2 text-left font-dense text-micro uppercase tracking-[0.06em] text-text-2">Reason</th>
                </tr>
              </thead>
              <tbody>
                {recentEntries.map((m) => (
                  <tr key={m.movement_id} className="border-t border-border">
                    <td className="px-3 py-1.5 font-ui text-body text-text">{m.item_code}</td>
                    <td className="px-3 py-1.5 font-data text-body tabular-nums text-text">
                      {/* qty is stored signed (WASTE is negative, per
                          ledger.py's sign convention) — this recap is a
                          "what did I just enter" confirmation, not a ledger
                          view, so show what was typed, not the sign. */}
                      {m.qty.replace(/^-/, "")} {m.uom}
                    </td>
                    <td className="px-3 py-1.5 font-ui text-body text-text-2">
                      {wasteReasons.find((r) => r.reason_code === m.reason_code)?.label ??
                        m.reason_code ??
                        "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
