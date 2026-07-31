import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { apiGet, apiPatch, apiPost } from "@/api/client";
import type { Location, LocationClosure, LocationStatusHistory } from "@/api/types";
import { RequirePermission } from "@/auth/RequireAuth";
import { StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Field, Input, Select } from "@/components/ui/Field";
import { PageHeader } from "@/components/ui/PageHeader";

const LOCATION_STATUSES = [
  "PLANNED",
  "PRE_OPENING",
  "RAMP_UP",
  "ACTIVE",
  "TEMP_CLOSED",
  "RENOVATION",
  "RELOCATED",
  "CLOSED",
];

export default function BranchDetailPage() {
  const { locationCode } = useParams<{ locationCode: string }>();
  const queryClient = useQueryClient();

  const { data: location, isLoading } = useQuery({
    queryKey: ["location", locationCode],
    queryFn: () => apiGet<Location>(`/api/v1/locations/${locationCode}`),
  });

  const [form, setForm] = useState<{
    location_name: string;
    address: string;
  } | null>(null);
  const [syncedFor, setSyncedFor] = useState<string | null>(null);
  if (location && syncedFor !== location.location_code) {
    setForm({ location_name: location.location_name, address: location.address ?? "" });
    setSyncedFor(location.location_code);
  }

  const saveMutation = useMutation({
    mutationFn: () => apiPatch<Location>(`/api/v1/locations/${locationCode}`, form),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["location", locationCode] });
      void queryClient.invalidateQueries({ queryKey: ["locations"] });
    },
  });

  if (isLoading || !location || !form) {
    return <div className="p-4 font-ui text-body text-text-3">Loading…</div>;
  }

  return (
    <div className="mx-auto max-w-2xl p-4">
      <PageHeader
        title={location.location_name}
        actions={<StatusBadge status={location.status} />}
      />

      <form
        onSubmit={(e) => {
          e.preventDefault();
          saveMutation.mutate();
        }}
        className="flex flex-col gap-4 p-4"
      >
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Code" htmlFor="location_code">
            <Input id="location_code" disabled value={location.location_code} />
          </Field>
          <Field label="Type" htmlFor="location_type">
            <Input id="location_type" disabled value={location.location_type} />
          </Field>
          <Field label="Name" htmlFor="location_name">
            <Input
              id="location_name"
              required
              value={form.location_name}
              onChange={(e) => setForm({ ...form, location_name: e.target.value })}
            />
          </Field>
          <Field label="Address" htmlFor="address">
            <Input
              id="address"
              value={form.address}
              onChange={(e) => setForm({ ...form, address: e.target.value })}
            />
          </Field>
          <Field label="Area" htmlFor="area_code">
            <Input id="area_code" disabled value={location.area_code ?? "—"} />
          </Field>
          <Field label="Cluster" htmlFor="cluster_code">
            <Input id="cluster_code" disabled value={location.cluster_code ?? "—"} />
          </Field>
        </div>

        <RequirePermission permission="location.update">
          <div>
            <Button type="submit" variant="primary" disabled={saveMutation.isPending}>
              {saveMutation.isPending ? "Saving…" : "Save changes"}
            </Button>
          </div>
        </RequirePermission>
      </form>

      <StatusSection location={location} />
      <OmAssignmentSection location={location} />
      <ClosuresSection locationCode={location.location_code} />
    </div>
  );
}

function StatusSection({ location }: { location: Location }) {
  const queryClient = useQueryClient();
  const [showDialog, setShowDialog] = useState(false);
  const [toStatus, setToStatus] = useState(location.status);
  const [reasonCode, setReasonCode] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data: history } = useQuery({
    queryKey: ["location-status-history", location.location_code],
    queryFn: () =>
      apiGet<LocationStatusHistory[]>(`/api/v1/locations/${location.location_code}/status-history`),
  });

  const transitionMutation = useMutation({
    mutationFn: () =>
      apiPost(`/api/v1/locations/${location.location_code}/status`, {
        to_status: toStatus,
        reason_code: reasonCode || null,
      }),
    onSuccess: () => {
      setError(null);
      setShowDialog(false);
      void queryClient.invalidateQueries({ queryKey: ["location", location.location_code] });
      void queryClient.invalidateQueries({
        queryKey: ["location-status-history", location.location_code],
      });
    },
    onError: (err) => setError(err instanceof Error ? err.message : "Transition failed"),
  });

  return (
    <section className="border-t border-border p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-ui text-h2 text-text">Lifecycle status</h2>
        <RequirePermission permission="location.status_change">
          <Button
            onClick={() => {
              setToStatus(location.status);
              setShowDialog(true);
            }}
          >
            Change status
          </Button>
        </RequirePermission>
      </div>
      <ul className="flex flex-col gap-1">
        {history?.map((h) => (
          <li key={h.history_id} className="font-ui text-small text-text-2">
            <span className="text-text">
              {h.from_status ?? "—"} → {h.to_status}
            </span>{" "}
            from {h.effective_from}
            {h.reason_code && <span className="text-text-3"> ({h.reason_code})</span>}
          </li>
        ))}
      </ul>

      <Dialog open={showDialog} onClose={() => setShowDialog(false)} title="Change branch status">
        <div className="flex flex-col gap-3">
          <Field label="New status" htmlFor="to_status">
            <Select id="to_status" value={toStatus} onChange={(e) => setToStatus(e.target.value)}>
              {LOCATION_STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Reason code (optional)" htmlFor="reason_code">
            <Input
              id="reason_code"
              value={reasonCode}
              onChange={(e) => setReasonCode(e.target.value)}
            />
          </Field>
          {error && <p className="font-ui text-small text-negative">{error}</p>}
          <div className="flex justify-end gap-2">
            <Button onClick={() => setShowDialog(false)}>Cancel</Button>
            <Button
              variant="primary"
              disabled={transitionMutation.isPending}
              onClick={() => transitionMutation.mutate()}
            >
              Confirm
            </Button>
          </div>
        </div>
      </Dialog>
    </section>
  );
}

function OmAssignmentSection({ location }: { location: Location }) {
  const queryClient = useQueryClient();
  const [omUserId, setOmUserId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const assignMutation = useMutation({
    mutationFn: () =>
      apiPost(`/api/v1/locations/${location.location_code}/assign-om`, {
        om_user_id: Number(omUserId),
      }),
    onSuccess: () => {
      setError(null);
      setOmUserId("");
      void queryClient.invalidateQueries({ queryKey: ["location", location.location_code] });
    },
    onError: (err) => setError(err instanceof Error ? err.message : "Assignment failed"),
  });

  return (
    <section className="border-t border-border p-4">
      <h2 className="mb-3 font-ui text-h2 text-text">Operations Manager</h2>
      <p className="mb-3 font-ui text-body text-text-2">
        Currently assigned:{" "}
        <span className="font-data tabular-nums text-text">
          {location.om_user_id ?? "— none —"}
        </span>
      </p>
      <RequirePermission permission="location.assign_om">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            assignMutation.mutate();
          }}
          className="flex items-end gap-2"
        >
          <Field label="User ID" htmlFor="om_user_id">
            <Input
              id="om_user_id"
              type="number"
              required
              value={omUserId}
              onChange={(e) => setOmUserId(e.target.value)}
              className="w-32"
            />
          </Field>
          <Button type="submit" disabled={assignMutation.isPending}>
            Assign
          </Button>
        </form>
        <p className="mt-1 font-ui text-small text-text-3">
          Assigning grants branch scope immediately — no separate permission step.
        </p>
      </RequirePermission>
      {error && <p className="mt-2 font-ui text-small text-negative">{error}</p>}
    </section>
  );
}

function ClosuresSection({ locationCode }: { locationCode: string }) {
  const queryClient = useQueryClient();
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [closureType, setClosureType] = useState("HOLIDAY");

  const { data: closures } = useQuery({
    queryKey: ["location-closures", locationCode],
    queryFn: () => apiGet<LocationClosure[]>(`/api/v1/locations/${locationCode}/closures`),
  });

  const addMutation = useMutation({
    mutationFn: () =>
      apiPost<LocationClosure>(`/api/v1/locations/${locationCode}/closures`, {
        start_date: startDate,
        end_date: endDate,
        closure_type: closureType,
      }),
    onSuccess: () => {
      setStartDate("");
      setEndDate("");
      void queryClient.invalidateQueries({ queryKey: ["location-closures", locationCode] });
    },
  });

  return (
    <section className="border-t border-border p-4">
      <h2 className="mb-3 font-ui text-h2 text-text">Closures</h2>
      <p className="mb-3 font-ui text-small text-text-3">
        A closed day is excluded from the forecast reference window — an absence, not a zero.
      </p>
      <ul className="mb-3 flex flex-col gap-1">
        {closures?.map((c) => (
          <li key={c.closure_id} className="font-ui text-body text-text">
            {c.start_date}
            {c.end_date !== c.start_date ? ` – ${c.end_date}` : ""} · {c.closure_type}
          </li>
        ))}
        {closures?.length === 0 && (
          <li className="font-ui text-small text-text-3">No closures recorded.</li>
        )}
      </ul>
      <RequirePermission permission="location.closure.manage">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            addMutation.mutate();
          }}
          className="flex flex-wrap items-end gap-2"
        >
          <Field label="Start date" htmlFor="closure_start">
            <Input
              id="closure_start"
              type="date"
              required
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
            />
          </Field>
          <Field label="End date" htmlFor="closure_end">
            <Input
              id="closure_end"
              type="date"
              required
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
            />
          </Field>
          <Field label="Type" htmlFor="closure_type">
            <Select
              id="closure_type"
              value={closureType}
              onChange={(e) => setClosureType(e.target.value)}
            >
              {["HOLIDAY", "RENOVATION", "UTILITY", "WEATHER", "HOST_CLOSED", "OTHER"].map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </Select>
          </Field>
          <Button type="submit" disabled={addMutation.isPending}>
            Add closure
          </Button>
        </form>
      </RequirePermission>
    </section>
  );
}
