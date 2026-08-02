import { useQuery } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { useState } from "react";
import { apiGet } from "@/api/client";
import type {
  FefoBucket,
  Location,
  LocationItemStock,
  Page,
  StockBalance,
  StockMovement,
} from "@/api/types";
import { DataTable, NumericCell } from "@/components/DataTable";
import { Badge } from "@/components/ui/Badge";
import { Field, Select } from "@/components/ui/Field";
import { PageHeader } from "@/components/ui/PageHeader";
import { formatQty } from "@/lib/format";

// Every item quantity in this table is rendered through formatQty, never
// the raw Decimal string — a NUMERIC(12,3) column's stored scale is a
// storage detail, not something worth showing here.
const itemColumns: ColumnDef<LocationItemStock, any>[] = [
  {
    accessorKey: "item_code",
    header: "Item",
    size: 220,
    cell: (ctx) => (
      <div>
        <div className="font-ui text-body text-text">{ctx.row.original.item_code}</div>
        <div className="font-ui text-micro text-text-3">{ctx.row.original.display_name}</div>
      </div>
    ),
  },
  {
    accessorKey: "received_qty",
    header: "Received",
    size: 110,
    cell: (ctx) => <NumericCell value={formatQty(ctx.getValue<string>())} />,
  },
  {
    accessorKey: "deducted_qty",
    header: "Deducted",
    size: 110,
    // Shown as its true negative value (not a positive magnitude) so
    // Received + Deducted visibly equals Balance — the whole point of
    // these two columns is deriving the number next to them, not just
    // decorating it.
    cell: (ctx) => <NumericCell value={formatQty(ctx.getValue<string>())} />,
  },
  {
    accessorKey: "balance_qty",
    header: "Balance as of today",
    size: 150,
    cell: (ctx) => <NumericCell value={formatQty(ctx.getValue<string>())} />,
  },
  {
    accessorKey: "excess_pct",
    header: "Excess %",
    size: 100,
    cell: (ctx) => {
      const v = ctx.getValue<string | null>();
      return <NumericCell value={v === null ? null : `${(Number(v) * 100).toFixed(1)}%`} />;
    },
  },
  {
    accessorKey: "run_outs",
    header: "Ran outs",
    size: 100,
    cell: (ctx) => {
      const n = ctx.getValue<number>();
      // A genuine zero (CLAUDE.md DATA: never blur "zero" into "no data")
      // — run_outs is always a real count, not an absence.
      return n > 0 ? <Badge tone="attention">{n}</Badge> : <NumericCell value={0} />;
    },
  },
];

const movementColumns: ColumnDef<StockMovement, any>[] = [
  { accessorKey: "business_date", header: "Date", size: 110 },
  { accessorKey: "movement_type", header: "Type", size: 130 },
  {
    accessorKey: "qty",
    header: "Qty",
    size: 90,
    cell: (ctx) => <NumericCell value={formatQty(ctx.getValue<string>())} />,
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

  // The table shown immediately after picking a branch — every item with
  // ledger history there, balance broken into how it was derived. Set-based
  // on the backend (app.domain.ledger.location_stock_summary), not one
  // request per item.
  const { data: locationStock, isLoading: locationStockLoading } = useQuery({
    queryKey: ["stock-by-location", locationCode],
    queryFn: () =>
      apiGet<LocationItemStock[]>(`/api/v1/stock/by-location?location=${locationCode}`),
    enabled: Boolean(locationCode),
  });

  // Only fetched once a row is clicked — FEFO ageing and movement history
  // are per-item detail, not something every row needs up front.
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

  const selectedItem = locationStock?.find((row) => row.item_code === itemCode);

  function handleSelectLocation(code: string): void {
    setLocationCode(code);
    setItemCode(""); // a new branch's table has nothing selected yet
  }

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Stock Explorer"
        description="Pick a branch to see every item's stock balance, broken into what came in vs. what went out, plus Excess % and how many days it's run out. Click any item for its production-date breakdown (FEFO ageing) and full movement history. Every figure here is computed live from the movement ledger, not a cached snapshot."
      />
      <div className="flex flex-wrap items-end gap-3 border-b border-border px-4 py-3">
        <Field label="Branch" htmlFor="loc">
          <Select
            id="loc"
            value={locationCode}
            onChange={(e) => handleSelectLocation(e.target.value)}
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
      </div>

      {!locationCode ? (
        <div className="flex h-40 items-center justify-center font-ui text-body text-text-3">
          Select a branch to view its stock.
        </div>
      ) : (
        <div className="flex flex-1 flex-col overflow-auto p-4">
          <div className="h-80 border border-border">
            <DataTable
              data={locationStock ?? []}
              columns={itemColumns}
              isLoading={locationStockLoading}
              emptyMessage="No stock movements recorded for this branch yet."
              onRowClick={(row) => setItemCode(row.item_code)}
              getRowClassName={(row) =>
                row.item_code === itemCode
                  ? "border-l-2 border-l-accent bg-surface-hover"
                  : "border-l-2 border-l-transparent"
              }
            />
          </div>

          {itemCode && (
            <div className="mt-6">
              <h2 className="mb-3 font-ui text-h1 text-text">
                {itemCode}
                {selectedItem && (
                  <span className="ml-2 font-ui text-body font-normal text-text-2">
                    {selectedItem.display_name}
                  </span>
                )}
              </h2>

              <h3 className="mb-2 font-ui text-h2 text-text">FEFO ageing</h3>
              {balanceLoading ? (
                <p className="font-ui text-small text-text-3">Loading…</p>
              ) : (
                <FefoTable buckets={balance?.fefo_buckets ?? []} />
              )}

              <h3 className="mb-2 mt-6 font-ui text-h2 text-text">Movement history</h3>
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
              <NumericCell value={formatQty(b.remaining_qty)} />
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
