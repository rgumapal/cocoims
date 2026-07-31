import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiGet, apiPost } from "@/api/client";
import type { CountSession, Location, Page } from "@/api/types";
import { DataTable } from "@/components/DataTable";
import { StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Field, Select } from "@/components/ui/Field";
import { PageHeader } from "@/components/ui/PageHeader";

const COUNT_TYPES = ["DAILY_EI", "CYCLE", "FULL"];

const columns: ColumnDef<CountSession, any>[] = [
  { accessorKey: "count_id", header: "ID", size: 70 },
  { accessorKey: "location_code", header: "Branch", size: 100 },
  { accessorKey: "count_type", header: "Type", size: 110 },
  { accessorKey: "business_date", header: "Date", size: 110 },
  {
    accessorKey: "status",
    header: "Status",
    size: 130,
    cell: (ctx) => <StatusBadge status={ctx.getValue<string>()} />,
  },
];

export default function CountsListPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [showDialog, setShowDialog] = useState(false);
  const [locationCode, setLocationCode] = useState("");
  const [countType, setCountType] = useState("CYCLE");
  const [businessDate, setBusinessDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [error, setError] = useState<string | null>(null);

  const { data: sessions, isLoading } = useQuery({
    queryKey: ["counts"],
    queryFn: () => apiGet<Page<CountSession>>("/api/v1/counts?limit=100"),
  });

  const { data: locations } = useQuery({
    queryKey: ["locations-picker"],
    queryFn: () => apiGet<Page<Location>>("/api/v1/locations?limit=200"),
  });

  const openMutation = useMutation({
    mutationFn: () =>
      apiPost<CountSession>("/api/v1/counts", {
        location_code: locationCode,
        count_type: countType,
        business_date: businessDate,
      }),
    onSuccess: (session) => {
      setError(null);
      setShowDialog(false);
      void queryClient.invalidateQueries({ queryKey: ["counts"] });
      navigate(`/counts/${session.count_id}`);
    },
    onError: (err) => setError(err instanceof Error ? err.message : "Could not open count"),
  });

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Counts"
        actions={
          <Button variant="primary" onClick={() => setShowDialog(true)}>
            Open Count
          </Button>
        }
      />
      <div className="flex-1 overflow-hidden">
        <DataTable
          data={sessions?.items ?? []}
          columns={columns}
          isLoading={isLoading}
          onRowClick={(s) => navigate(`/counts/${s.count_id}`)}
          emptyMessage="No counts yet. Open one to get started."
        />
      </div>

      <Dialog open={showDialog} onClose={() => setShowDialog(false)} title="Open a new count">
        <div className="flex flex-col gap-3">
          <Field label="Branch" htmlFor="count_location">
            <Select
              id="count_location"
              required
              value={locationCode}
              onChange={(e) => setLocationCode(e.target.value)}
            >
              <option value="">Select a branch…</option>
              {locations?.items.map((l) => (
                <option key={l.location_code} value={l.location_code}>
                  {l.location_code} — {l.location_name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Count type" htmlFor="count_type">
            <Select id="count_type" value={countType} onChange={(e) => setCountType(e.target.value)}>
              {COUNT_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Business date" htmlFor="count_date">
            <input
              id="count_date"
              type="date"
              required
              value={businessDate}
              onChange={(e) => setBusinessDate(e.target.value)}
              className="rounded-md border border-border-strong bg-surface px-2.5 py-1.5 font-ui text-body text-text outline-none focus:border-accent"
            />
          </Field>
          {error && <p className="font-ui text-small text-negative">{error}</p>}
          <div className="flex justify-end gap-2">
            <Button onClick={() => setShowDialog(false)}>Cancel</Button>
            <Button
              variant="primary"
              disabled={openMutation.isPending || !locationCode}
              onClick={() => openMutation.mutate()}
            >
              Open
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
