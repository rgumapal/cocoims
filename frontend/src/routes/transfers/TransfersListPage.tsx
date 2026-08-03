import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { useRef, useState } from "react";
import { apiFetch, apiGet, apiPost } from "@/api/client";
import type { Item, Location, Page, ReasonCode, Transfer, TransferDetail } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { DataTable, NumericCell } from "@/components/DataTable";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Field, Input, Select } from "@/components/ui/Field";
import { PageHeader } from "@/components/ui/PageHeader";
import { todayLocalDate } from "@/lib/date";
import { formatQty } from "@/lib/format";

type Direction = "all" | "inbound" | "outbound";
type StatusFilter = "" | Transfer["status"];

const STATUS_FILTERS: { value: StatusFilter; label: string }[] = [
  { value: "", label: "All" },
  { value: "DRAFT", label: "Draft" },
  { value: "IN_TRANSIT", label: "In Transit" },
  { value: "RECEIVED", label: "Received" },
  { value: "CANCELLED", label: "Cancelled" },
];

const columns: ColumnDef<Transfer, any>[] = [
  { accessorKey: "transfer_no", header: "Transfer #", size: 120 },
  { accessorKey: "source_location_code", header: "From", size: 90 },
  { accessorKey: "dest_location_code", header: "To", size: 90 },
  {
    accessorKey: "status",
    header: "Status",
    size: 120,
    cell: (ctx) => <StatusBadge status={ctx.getValue<string>()} />,
  },
  {
    accessorKey: "created_at",
    header: "Created",
    size: 140,
    cell: (ctx) => {
      const v = ctx.getValue<string | null>();
      return v ? new Date(v).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "—";
    },
  },
];

export default function TransfersListPage() {
  const { me } = useAuth();
  const queryClient = useQueryClient();

  // "Scoped by default": a single-branch user (STORE_HEAD/STORE_TEAM, the
  // common case) gets Inbound/Outbound tabs against their own branch. An
  // OM covering several branches or an unrestricted user just sees
  // everything RLS already limits them to — direction tabs don't have a
  // single obvious branch to filter against for them.
  const ownLocation = !me?.unrestricted && me?.location_scope.length === 1 ? me.location_scope[0]! : null;

  const [direction, setDirection] = useState<Direction>("all");
  const [status, setStatus] = useState<StatusFilter>("");
  const [createOpen, setCreateOpen] = useState(false);
  const [detailId, setDetailId] = useState<number | null>(null);

  const params = new URLSearchParams({ limit: "100" });
  if (status) params.set("status", status);
  if (ownLocation && direction !== "all") {
    params.set("location", ownLocation);
    params.set("direction", direction);
  }

  const { data, isLoading } = useQuery({
    queryKey: ["transfers", status, ownLocation, direction],
    queryFn: () => apiGet<Page<Transfer>>(`/api/v1/transfers?${params.toString()}`),
  });

  function refetchList(): void {
    void queryClient.invalidateQueries({ queryKey: ["transfers"] });
  }

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Transfers"
        description="Move sellable stock from one branch to another. Ship records what left; Receive records what actually arrived — the two can differ, and that's tracked, not hidden."
        actions={
          <Button variant="primary" onClick={() => setCreateOpen(true)}>
            New Transfer
          </Button>
        }
      />

      <div className="flex flex-wrap items-center gap-4 border-b border-border px-4 py-3">
        {ownLocation && (
          <div className="flex gap-1">
            {(["all", "inbound", "outbound"] as Direction[]).map((d) => (
              <button
                key={d}
                onClick={() => setDirection(d)}
                className={`rounded-md px-2.5 py-1 font-ui text-small font-medium capitalize ${
                  direction === d ? "bg-surface-2 text-text" : "text-text-2 hover:bg-surface-hover"
                }`}
              >
                {d}
              </button>
            ))}
          </div>
        )}
        <div className="flex gap-1">
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.value}
              onClick={() => setStatus(f.value)}
              className={`rounded-md px-2.5 py-1 font-ui text-small font-medium ${
                status === f.value ? "bg-surface-2 text-text" : "text-text-2 hover:bg-surface-hover"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-hidden">
        <DataTable
          data={data?.items ?? []}
          columns={columns}
          isLoading={isLoading}
          emptyMessage="No transfers yet. Click New Transfer to move stock between branches."
          onRowClick={(row) => setDetailId(row.transfer_id)}
        />
      </div>

      {createOpen && (
        <CreateTransferDialog
          defaultSource={ownLocation}
          onClose={() => setCreateOpen(false)}
          onCreated={(id) => {
            setCreateOpen(false);
            refetchList();
            setDetailId(id);
          }}
        />
      )}

      {detailId !== null && (
        <TransferDetailDialog
          transferId={detailId}
          onClose={() => setDetailId(null)}
          onChanged={refetchList}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------
// Create
// ---------------------------------------------------------------------

interface LineDraft {
  item_code: string;
  qty_requested: string;
}

function CreateTransferDialog({
  defaultSource,
  onClose,
  onCreated,
}: {
  defaultSource: string | null;
  onClose: () => void;
  onCreated: (transferId: number) => void;
}) {
  const [source, setSource] = useState(defaultSource ?? "");
  const [dest, setDest] = useState("");
  const [reasonCode, setReasonCode] = useState("");
  const [notes, setNotes] = useState("");
  const [lines, setLines] = useState<LineDraft[]>([{ item_code: "", qty_requested: "" }]);
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

  const createMutation = useMutation({
    mutationFn: () =>
      apiPost<TransferDetail>("/api/v1/transfers", {
        source_location_code: source,
        dest_location_code: dest,
        reason_code: reasonCode || null,
        notes: notes || null,
        lines: lines
          .filter((l) => l.item_code && l.qty_requested)
          .map((l) => ({ item_code: l.item_code, qty_requested: l.qty_requested })),
      }),
    onSuccess: (created) => onCreated(created.transfer_id),
    onError: (err) => setError(err instanceof Error ? err.message : "Could not create transfer"),
  });

  const usedItemCodes = new Set(lines.map((l) => l.item_code).filter(Boolean));

  return (
    <Dialog open onClose={onClose} title="New Transfer">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          createMutation.mutate();
        }}
        className="flex flex-col gap-3"
      >
        <div className="grid grid-cols-2 gap-3">
          <Field label="From" htmlFor="t_source">
            <Select
              id="t_source"
              required
              value={source}
              onChange={(e) => setSource(e.target.value)}
              disabled={!!defaultSource}
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
          <Field label="To" htmlFor="t_dest">
            <Select id="t_dest" required value={dest} onChange={(e) => setDest(e.target.value)}>
              <option value="">Select…</option>
              {locations?.items
                .filter((l) => l.is_active && l.location_code !== source)
                .map((l) => (
                  <option key={l.location_code} value={l.location_code}>
                    {l.location_code} — {l.location_name}
                  </option>
                ))}
            </Select>
          </Field>
        </div>

        <div>
          <label className="mb-1 block font-ui text-small font-medium text-text-2">Items</label>
          <div className="flex flex-col gap-2">
            {lines.map((line, i) => (
              <div key={i} className="flex gap-2">
                <Select
                  required
                  value={line.item_code}
                  onChange={(e) =>
                    setLines(lines.map((l, idx) => (idx === i ? { ...l, item_code: e.target.value } : l)))
                  }
                  className="flex-1"
                >
                  <option value="">Select item…</option>
                  {items?.items
                    .filter((it) => it.item_code === line.item_code || !usedItemCodes.has(it.item_code))
                    .map((it) => (
                      <option key={it.item_code} value={it.item_code}>
                        {it.item_code} — {it.display_name}
                      </option>
                    ))}
                </Select>
                <Input
                  type="number"
                  step="0.001"
                  min="0"
                  required
                  placeholder="Qty"
                  value={line.qty_requested}
                  onChange={(e) =>
                    setLines(lines.map((l, idx) => (idx === i ? { ...l, qty_requested: e.target.value } : l)))
                  }
                  className="w-28 font-data tabular-nums"
                />
                <button
                  type="button"
                  onClick={() =>
                    setLines(lines.length > 1 ? lines.filter((_, idx) => idx !== i) : [{ item_code: "", qty_requested: "" }])
                  }
                  className="font-ui text-small text-negative hover:underline"
                >
                  Remove
                </button>
              </div>
            ))}
          </div>
          <Button
            type="button"
            className="mt-2"
            onClick={() => setLines([...lines, { item_code: "", qty_requested: "" }])}
          >
            Add Item
          </Button>
        </div>

        <Field label="Reason (optional)" htmlFor="t_reason">
          <Select id="t_reason" value={reasonCode} onChange={(e) => setReasonCode(e.target.value)}>
            <option value="">Select…</option>
            {reasonCodes
              ?.filter((r) => r.is_active)
              .map((r) => (
                <option key={r.reason_code} value={r.reason_code}>
                  {r.label}
                </option>
              ))}
          </Select>
        </Field>
        <Field label="Notes (optional)" htmlFor="t_notes">
          <Input id="t_notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
        </Field>

        {error && <p className="font-ui text-small text-negative">{error}</p>}

        <div className="flex justify-end gap-2">
          <Button type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" disabled={createMutation.isPending}>
            {createMutation.isPending ? "Creating…" : "Create Draft"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

// ---------------------------------------------------------------------
// Detail — a dialog off the list, not its own route (docs/features/TRANSFERS_V1.md)
// ---------------------------------------------------------------------

function TransferDetailDialog({
  transferId,
  onClose,
  onChanged,
}: {
  transferId: number;
  onClose: () => void;
  onChanged: () => void;
}) {
  const { hasPermission } = useAuth();
  const [action, setAction] = useState<"ship" | "receive" | null>(null);

  const { data: transfer, isLoading, refetch } = useQuery({
    queryKey: ["transfer", transferId],
    queryFn: () => apiGet<TransferDetail>(`/api/v1/transfers/${transferId}`),
  });

  const cancelMutation = useMutation({
    mutationFn: () => apiPost<TransferDetail>(`/api/v1/transfers/${transferId}/cancel`),
    onSuccess: () => {
      void refetch();
      onChanged();
    },
  });

  return (
    <Dialog open onClose={onClose} title={transfer?.transfer_no ?? `Transfer ${transferId}`}>
      {isLoading || !transfer ? (
        <p className="font-ui text-small text-text-3">Loading…</p>
      ) : action === "ship" ? (
        <ShipForm
          transfer={transfer}
          onDone={() => {
            setAction(null);
            void refetch();
            onChanged();
          }}
          onCancel={() => setAction(null)}
        />
      ) : action === "receive" ? (
        <ReceiveForm
          transfer={transfer}
          onDone={() => {
            setAction(null);
            void refetch();
            onChanged();
          }}
          onCancel={() => setAction(null)}
        />
      ) : (
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-2">
            <StatusBadge status={transfer.status} />
            <span className="font-ui text-small text-text-2">
              {transfer.source_location_code} → {transfer.dest_location_code}
            </span>
          </div>

          {transfer.warnings.length > 0 && (
            <ul className="flex flex-col gap-1 rounded-md bg-attention-bg p-2">
              {transfer.warnings.map((w, i) => (
                <li key={i} className="font-ui text-small text-attention">
                  {w}
                </li>
              ))}
            </ul>
          )}

          {transfer.notes && <p className="font-ui text-small text-text-2">{transfer.notes}</p>}

          <table className="w-full border-collapse">
            <thead>
              <tr className="border-b border-border">
                <th className="px-2 py-1.5 text-left font-dense text-micro uppercase tracking-[0.06em] text-text-2">Item</th>
                <th className="px-2 py-1.5 text-left font-dense text-micro uppercase tracking-[0.06em] text-text-2">Requested</th>
                <th className="px-2 py-1.5 text-left font-dense text-micro uppercase tracking-[0.06em] text-text-2">Shipped</th>
                <th className="px-2 py-1.5 text-left font-dense text-micro uppercase tracking-[0.06em] text-text-2">Received</th>
                <th className="px-2 py-1.5 text-left font-dense text-micro uppercase tracking-[0.06em] text-text-2">Variance</th>
              </tr>
            </thead>
            <tbody>
              {transfer.lines.map((line) => (
                <tr key={line.item_code} className="border-b border-border">
                  <td className="px-2 py-1.5 font-ui text-body text-text">{line.item_code}</td>
                  <td className="px-2 py-1.5"><NumericCell value={formatQty(line.qty_requested)} /></td>
                  <td className="px-2 py-1.5">
                    <NumericCell value={line.qty_shipped === null ? null : formatQty(line.qty_shipped)} />
                  </td>
                  <td className="px-2 py-1.5">
                    <NumericCell value={line.qty_received === null ? null : formatQty(line.qty_received)} />
                  </td>
                  <td className="px-2 py-1.5">
                    {line.variance_qty !== null && Number(line.variance_qty) !== 0 ? (
                      <Badge tone={Number(line.variance_qty) < 0 ? "negative" : "attention"}>
                        {formatQty(line.variance_qty)}
                      </Badge>
                    ) : (
                      <NumericCell value={line.variance_qty === null ? null : formatQty(line.variance_qty)} />
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="flex justify-end gap-2">
            <Button onClick={onClose}>Close</Button>
            {transfer.status === "DRAFT" && hasPermission("transfer.cancel") && (
              <Button variant="danger" onClick={() => cancelMutation.mutate()} disabled={cancelMutation.isPending}>
                Cancel Transfer
              </Button>
            )}
            {transfer.status === "DRAFT" && hasPermission("transfer.ship") && (
              <Button variant="primary" onClick={() => setAction("ship")}>
                Ship
              </Button>
            )}
            {transfer.status === "IN_TRANSIT" && hasPermission("transfer.receive") && (
              <Button variant="primary" onClick={() => setAction("receive")}>
                Receive
              </Button>
            )}
          </div>
        </div>
      )}
    </Dialog>
  );
}

// ---------------------------------------------------------------------
// Ship — mobile-first: pick quantities, FEFO allocation is server-decided
// (SPEC "not editable" — this screen shows what was requested, not a
// lot-by-lot picker; the resulting allocation is visible afterward in the
// detail view and Stock Explorer's movement history).
// ---------------------------------------------------------------------

function ShipForm({ transfer, onDone, onCancel }: { transfer: TransferDetail; onDone: () => void; onCancel: () => void }) {
  const [qtys, setQtys] = useState<Record<string, string>>(() =>
    Object.fromEntries(transfer.lines.map((l) => [l.item_code, l.qty_requested])),
  );
  const [error, setError] = useState<string | null>(null);
  // Stable for the life of this form instance — a double-tap on bad signal
  // reuses the same key, so the retry is a true no-op replay, not a second
  // shipment (docs/features/TRANSFERS_V1.md, AC-5).
  const idempotencyKey = useRef(crypto.randomUUID());

  const shipMutation = useMutation({
    mutationFn: () =>
      apiFetch<TransferDetail>(`/api/v1/transfers/${transfer.transfer_id}/ship`, {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey.current },
        body: JSON.stringify({
          business_date: todayLocalDate(),
          lines: transfer.lines
            .filter((l) => qtys[l.item_code])
            .map((l) => ({ item_code: l.item_code, qty_shipped: qtys[l.item_code] })),
        }),
      }),
    onSuccess: onDone,
    onError: (err) => setError(err instanceof Error ? err.message : "Ship failed"),
  });

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        setError(null);
        shipMutation.mutate();
      }}
      className="flex flex-col gap-3"
    >
      <p className="font-ui text-small text-text-2">
        Confirm what's actually leaving {transfer.source_location_code}. FEFO lot allocation is handled
        automatically — the oldest stock on hand ships first.
      </p>
      {transfer.lines.map((line) => (
        <Field key={line.item_code} label={line.item_code} htmlFor={`ship_${line.item_code}`}>
          <Input
            id={`ship_${line.item_code}`}
            type="number"
            step="0.001"
            min="0"
            inputMode="decimal"
            value={qtys[line.item_code] ?? ""}
            onChange={(e) => setQtys({ ...qtys, [line.item_code]: e.target.value })}
            className="font-data tabular-nums"
          />
        </Field>
      ))}
      {error && <p className="font-ui text-small text-negative">{error}</p>}
      <div className="flex justify-end gap-2">
        <Button type="button" onClick={onCancel}>
          Back
        </Button>
        <Button type="submit" variant="primary" disabled={shipMutation.isPending}>
          {shipMutation.isPending ? "Shipping…" : "Confirm Ship"}
        </Button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------
// Receive — count fields empty by default (SPEC rule 4: never default
// received from shipped); a mismatch forces a reason before submit.
// ---------------------------------------------------------------------

function ReceiveForm({ transfer, onDone, onCancel }: { transfer: TransferDetail; onDone: () => void; onCancel: () => void }) {
  const [qtys, setQtys] = useState<Record<string, string>>({});
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const idempotencyKey = useRef(crypto.randomUUID());

  const { data: reasonCodes } = useQuery({
    queryKey: ["reason-codes"],
    queryFn: () => apiGet<ReasonCode[]>("/api/v1/reason-codes"),
  });

  const shippedLines = transfer.lines.filter((l) => l.qty_shipped !== null);

  const receiveMutation = useMutation({
    mutationFn: () =>
      apiFetch<TransferDetail>(`/api/v1/transfers/${transfer.transfer_id}/receive`, {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey.current },
        body: JSON.stringify({
          business_date: todayLocalDate(),
          lines: shippedLines
            .filter((l) => qtys[l.item_code] !== undefined && qtys[l.item_code] !== "")
            .map((l) => ({
              item_code: l.item_code,
              qty_received: qtys[l.item_code],
              variance_reason_code: reasons[l.item_code] || null,
            })),
        }),
      }),
    onSuccess: onDone,
    onError: (err) => setError(err instanceof Error ? err.message : "Receive failed"),
  });

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        setError(null);
        receiveMutation.mutate();
      }}
      className="flex flex-col gap-3"
    >
      <p className="font-ui text-small text-text-2">
        Count what actually arrived at {transfer.dest_location_code}. Leave a line blank if nothing
        from it arrived yet.
      </p>
      {shippedLines.map((line) => {
        const mismatched =
          qtys[line.item_code] !== undefined &&
          qtys[line.item_code] !== "" &&
          qtys[line.item_code] !== line.qty_shipped;
        return (
          <div key={line.item_code} className="flex flex-col gap-1">
            <Field
              label={`${line.item_code} (shipped ${formatQty(line.qty_shipped ?? "0")})`}
              htmlFor={`recv_${line.item_code}`}
            >
              <Input
                id={`recv_${line.item_code}`}
                type="number"
                step="0.001"
                min="0"
                inputMode="decimal"
                placeholder="Count received"
                value={qtys[line.item_code] ?? ""}
                onChange={(e) => setQtys({ ...qtys, [line.item_code]: e.target.value })}
                className="font-data tabular-nums"
              />
            </Field>
            {mismatched && (
              <Select
                required
                value={reasons[line.item_code] ?? ""}
                onChange={(e) => setReasons({ ...reasons, [line.item_code]: e.target.value })}
              >
                <option value="">Reason for variance…</option>
                {reasonCodes
                  ?.filter((r) => r.is_active)
                  .map((r) => (
                    <option key={r.reason_code} value={r.reason_code}>
                      {r.label}
                    </option>
                  ))}
              </Select>
            )}
          </div>
        );
      })}
      {error && <p className="font-ui text-small text-negative">{error}</p>}
      <div className="flex justify-end gap-2">
        <Button type="button" onClick={onCancel}>
          Back
        </Button>
        <Button type="submit" variant="primary" disabled={receiveMutation.isPending}>
          {receiveMutation.isPending ? "Receiving…" : "Confirm Receive"}
        </Button>
      </div>
    </form>
  );
}
