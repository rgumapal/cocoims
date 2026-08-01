import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { apiGet, apiPost } from "@/api/client";
import type { Item, Location, Page, ReasonCode, StockMovement } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Field, Input, Select } from "@/components/ui/Field";
import { PageHeader } from "@/components/ui/PageHeader";
import { todayLocalDate } from "@/lib/date";

export default function WastePage() {
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
    },
    onError: (err) => setError(err instanceof Error ? err.message : "Could not record waste"),
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
