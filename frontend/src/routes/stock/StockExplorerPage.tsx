import { useQuery } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { useState } from "react";
import { apiGet } from "@/api/client";
import type { FefoBucket, Item, Location, Page, StockBalance, StockMovement } from "@/api/types";
import { DataTable, NumericCell } from "@/components/DataTable";
import { Badge } from "@/components/ui/Badge";
import { Field, Select } from "@/components/ui/Field";
import { PageHeader } from "@/components/ui/PageHeader";

const movementColumns: ColumnDef<StockMovement, any>[] = [
  { accessorKey: "business_date", header: "Date", size: 110 },
  { accessorKey: "movement_type", header: "Type", size: 130 },
  {
    accessorKey: "qty",
    header: "Qty",
    size: 90,
    cell: (ctx) => <NumericCell value={ctx.getValue<string>()} />,
  },
  { accessorKey: "reason_code", header: "Reason", size: 140 },
  { accessorKey: "ref_doc_type", header: "Ref type", size: 100 },
  { accessorKey: "counterparty_location", header: "Counterparty", size: 120 },
];

export default function StockExplorerPage() {
  const [locationCode, setLocationCode] = useState("");
  const [itemCode, setItemCode] = useState("");

  const { data: locations } = useQuery({
    queryKey: ["locations-picker"],
    queryFn: () => apiGet<Page<Location>>("/api/v1/locations?limit=200"),
  });
  const { data: items } = useQuery({
    queryKey: ["items-picker"],
    queryFn: () => apiGet<Page<Item>>("/api/v1/items?limit=200"),
  });

  const { data: balance, isLoading: balanceLoading } = useQuery({
    queryKey: ["stock-balance", locationCode, itemCode],
    queryFn: () =>
      apiGet<StockBalance>(`/api/v1/stock?location=${locationCode}&item=${itemCode}`),
    enabled: Boolean(locationCode && itemCode),
  });

  const { data: movements, isLoading: movementsLoading } = useQuery({
    queryKey: ["stock-movements", locationCode, itemCode],
    queryFn: () =>
      apiGet<Page<StockMovement>>(
        `/api/v1/stock/movements?location=${locationCode}&item=${itemCode}&limit=100`,
      ),
    enabled: Boolean(locationCode && itemCode),
  });

  return (
    <div className="flex h-full flex-col">
      <PageHeader title="Stock Explorer" />
      <div className="flex flex-wrap items-end gap-3 border-b border-border px-4 py-3">
        <Field label="Branch" htmlFor="loc">
          <Select
            id="loc"
            value={locationCode}
            onChange={(e) => setLocationCode(e.target.value)}
            className="w-56"
          >
            <option value="">Select a branch…</option>
            {locations?.items.map((l) => (
              <option key={l.location_code} value={l.location_code}>
                {l.location_code} — {l.location_name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Item" htmlFor="item">
          <Select
            id="item"
            value={itemCode}
            onChange={(e) => setItemCode(e.target.value)}
            className="w-56"
          >
            <option value="">Select an item…</option>
            {items?.items.map((i) => (
              <option key={i.item_code} value={i.item_code}>
                {i.item_code} — {i.display_name}
              </option>
            ))}
          </Select>
        </Field>
      </div>

      {!locationCode || !itemCode ? (
        <div className="flex h-40 items-center justify-center font-ui text-body text-text-3">
          Select a branch and an item to view stock.
        </div>
      ) : (
        <div className="flex-1 overflow-auto p-4">
          <div className="mb-6 flex items-baseline gap-3">
            <span className="font-ui text-small text-text-2">Balance as of today</span>
            <span className="font-data text-display tabular-nums text-text">
              {balanceLoading ? "…" : (balance?.balance_qty ?? "0")}
            </span>
          </div>

          <h2 className="mb-2 font-ui text-h2 text-text">FEFO ageing</h2>
          <FefoTable buckets={balance?.fefo_buckets ?? []} />

          <h2 className="mb-2 mt-6 font-ui text-h2 text-text">Movement history</h2>
          <div className="h-96 border border-border">
            <DataTable
              data={movements?.items ?? []}
              columns={movementColumns}
              isLoading={movementsLoading}
              emptyMessage="No movements recorded for this branch/item yet."
            />
          </div>
        </div>
      )}
    </div>
  );
}

function FefoTable({ buckets }: { buckets: FefoBucket[] }) {
  if (buckets.length === 0) {
    return <p className="font-ui text-small text-text-3">No production batches on hand.</p>;
  }
  return (
    <table className="w-full max-w-xl border-collapse">
      <thead>
        <tr className="border-b border-border">
          <th className="px-2 py-2 text-left font-dense text-micro uppercase tracking-[0.06em] text-text-2">
            Production date
          </th>
          <th className="px-2 py-2 text-left font-dense text-micro uppercase tracking-[0.06em] text-text-2">
            Expiry
          </th>
          <th className="px-2 py-2 text-left font-dense text-micro uppercase tracking-[0.06em] text-text-2">
            Remaining
          </th>
          <th className="px-2 py-2 text-left font-dense text-micro uppercase tracking-[0.06em] text-text-2">
            Days left
          </th>
        </tr>
      </thead>
      <tbody>
        {buckets.map((b) => (
          <tr key={b.production_date} className="border-b border-border">
            <td className="px-2 py-1.5 font-data text-body text-text">{b.production_date}</td>
            <td className="px-2 py-1.5 font-data text-body text-text">{b.expiry_date ?? "—"}</td>
            <td className="px-2 py-1.5">
              <NumericCell value={b.remaining_qty} />
            </td>
            <td className="px-2 py-1.5">
              {b.days_remaining === null ? (
                "—"
              ) : (
                <Badge tone={b.days_remaining <= 0 ? "negative" : b.days_remaining <= 1 ? "attention" : "positive"}>
                  {b.days_remaining} day{b.days_remaining === 1 ? "" : "s"}
                </Badge>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
