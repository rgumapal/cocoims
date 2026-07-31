import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { apiGet, apiPost } from "@/api/client";
import type { Item, Location, Page, StockMovement } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Field, Input, Select } from "@/components/ui/Field";
import { PageHeader } from "@/components/ui/PageHeader";

interface LineDraft {
  item_code: string;
  qty: string;
  sold_out: boolean;
}

const emptyLine = (): LineDraft => ({ item_code: "", qty: "", sold_out: false });

export default function SalesPage() {
  const [locationCode, setLocationCode] = useState("");
  const [businessDate, setBusinessDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [lines, setLines] = useState<LineDraft[]>([emptyLine()]);
  const [error, setError] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState<StockMovement[] | null>(null);

  const { data: locations } = useQuery({
    queryKey: ["locations-picker"],
    queryFn: () => apiGet<Page<Location>>("/api/v1/locations?limit=200"),
  });
  const { data: items } = useQuery({
    queryKey: ["items-picker"],
    queryFn: () => apiGet<Page<Item>>("/api/v1/items?limit=200"),
  });

  const submitMutation = useMutation({
    mutationFn: () =>
      apiPost<StockMovement[]>("/api/v1/sales", {
        business_date: businessDate,
        location_code: locationCode,
        lines: lines
          .filter((l) => l.item_code && l.qty)
          .map((l) => ({
            item_code: l.item_code,
            qty: l.qty,
            sold_out: l.sold_out,
          })),
      }),
    onSuccess: (movements) => {
      setError(null);
      setConfirmed(movements);
      setLines([emptyLine()]);
    },
    onError: (err) => setError(err instanceof Error ? err.message : "Could not record sales"),
  });

  function updateLine(index: number, patch: Partial<LineDraft>): void {
    setLines(lines.map((l, i) => (i === index ? { ...l, ...patch } : l)));
  }

  return (
    <div className="mx-auto max-w-2xl p-4">
      <PageHeader title="Sales" />

      <form
        onSubmit={(e) => {
          e.preventDefault();
          submitMutation.mutate();
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
            >
              <option value="">Select…</option>
              {locations?.items.map((l) => (
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

        <div>
          <h2 className="mb-2 font-ui text-h2 text-text">Lines</h2>
          <div className="flex flex-col gap-2">
            {lines.map((line, i) => (
              <div key={i} className="flex flex-wrap items-end gap-2">
                <Field label="Item" htmlFor={`s_line_item_${i}`}>
                  <Select
                    id={`s_line_item_${i}`}
                    required
                    value={line.item_code}
                    onChange={(e) => updateLine(i, { item_code: e.target.value })}
                    className="w-56"
                  >
                    <option value="">Select…</option>
                    {items?.items.map((it) => (
                      <option key={it.item_code} value={it.item_code}>
                        {it.item_code} — {it.display_name}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field label="Qty sold" htmlFor={`s_line_qty_${i}`}>
                  <Input
                    id={`s_line_qty_${i}`}
                    type="number"
                    step="0.001"
                    min="0.001"
                    required
                    value={line.qty}
                    onChange={(e) => updateLine(i, { qty: e.target.value })}
                    className="w-24"
                  />
                </Field>
                <label
                  htmlFor={`s_line_soldout_${i}`}
                  className="mb-1.5 flex items-center gap-1.5 font-ui text-body text-text"
                >
                  <input
                    id={`s_line_soldout_${i}`}
                    type="checkbox"
                    checked={line.sold_out}
                    onChange={(e) => updateLine(i, { sold_out: e.target.checked })}
                  />
                  Ran out
                </label>
                {lines.length > 1 && (
                  <button
                    type="button"
                    onClick={() => setLines(lines.filter((_, idx) => idx !== i))}
                    className="mb-1.5 font-ui text-small text-negative hover:underline"
                  >
                    Remove
                  </button>
                )}
              </div>
            ))}
          </div>
          <Button type="button" onClick={() => setLines([...lines, emptyLine()])} className="mt-2">
            Add line
          </Button>
        </div>

        {error && <p className="font-ui text-small text-negative">{error}</p>}
        {confirmed && (
          <p className="font-ui text-small text-positive">
            Recorded {confirmed.length} line{confirmed.length === 1 ? "" : "s"}.
          </p>
        )}

        <div>
          <Button type="submit" variant="primary" disabled={submitMutation.isPending}>
            {submitMutation.isPending ? "Recording…" : "Record sales"}
          </Button>
        </div>
      </form>
    </div>
  );
}
