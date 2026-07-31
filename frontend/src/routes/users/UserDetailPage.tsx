import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { apiDelete, apiGet, apiPatch, apiPost } from "@/api/client";
import type { Role, UserDetail as UserDetailType } from "@/api/types";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Field, Input, Select } from "@/components/ui/Field";
import { PageHeader } from "@/components/ui/PageHeader";

const SCOPE_TYPES = ["LOCATION", "AREA", "CLUSTER", "ROUTE", "ALL"];

export default function UserDetailPage() {
  const { userId } = useParams<{ userId: string }>();
  const queryClient = useQueryClient();

  const { data: user, isLoading } = useQuery({
    queryKey: ["user", userId],
    queryFn: () => apiGet<UserDetailType>(`/api/v1/users/${userId}`),
  });

  const { data: allRoles } = useQuery({
    queryKey: ["roles"],
    queryFn: () => apiGet<Role[]>("/api/v1/roles"),
  });

  const toggleActiveMutation = useMutation({
    mutationFn: () => apiPatch(`/api/v1/users/${userId}`, { is_active: !user?.is_active }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["user", userId] }),
  });

  if (isLoading || !user) {
    return <div className="p-4 font-ui text-body text-text-3">Loading…</div>;
  }

  return (
    <div className="mx-auto max-w-2xl p-4">
      <PageHeader
        title={user.full_name}
        actions={
          <>
            <Badge tone={user.is_active ? "positive" : "negative"}>
              {user.is_active ? "Active" : "Inactive"}
            </Badge>
            <Button
              variant={user.is_active ? "danger" : "primary"}
              onClick={() => toggleActiveMutation.mutate()}
            >
              {user.is_active ? "Deactivate" : "Reactivate"}
            </Button>
          </>
        }
      />

      <div className="p-4 font-ui text-body text-text-2">
        <p>{user.email}</p>
        {user.is_service && <p className="text-text-3">Service account — no interactive login.</p>}
      </div>

      <RolesSection userId={user.user_id} currentRoles={user.roles} allRoles={allRoles ?? []} />
      <ScopesSection userId={user.user_id} scopes={user.scopes} />
    </div>
  );
}

function RolesSection({
  userId,
  currentRoles,
  allRoles,
}: {
  userId: number;
  currentRoles: UserDetailType["roles"];
  allRoles: Role[];
}) {
  const queryClient = useQueryClient();
  const [newRole, setNewRole] = useState("");

  const assignMutation = useMutation({
    mutationFn: () => apiPost(`/api/v1/users/${userId}/roles`, { role_code: newRole }),
    onSuccess: () => {
      setNewRole("");
      void queryClient.invalidateQueries({ queryKey: ["user", String(userId)] });
    },
  });

  const revokeMutation = useMutation({
    mutationFn: (roleCode: string) => apiDelete(`/api/v1/users/${userId}/roles/${roleCode}`),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["user", String(userId)] }),
  });

  const availableRoles = allRoles.filter(
    (r) => !currentRoles.some((cr) => cr.role_code === r.role_code),
  );

  return (
    <section className="border-t border-border p-4">
      <h2 className="mb-3 font-ui text-h2 text-text">Roles</h2>
      <ul className="mb-3 flex flex-col gap-1">
        {currentRoles.map((r) => (
          <li key={r.role_code} className="flex items-center gap-3 font-ui text-body text-text">
            <Badge>{r.role_code}</Badge>
            <button
              type="button"
              onClick={() => revokeMutation.mutate(r.role_code)}
              className="font-ui text-small text-negative hover:underline"
            >
              Revoke
            </button>
          </li>
        ))}
        {currentRoles.length === 0 && (
          <li className="font-ui text-small text-text-3">No roles assigned.</li>
        )}
      </ul>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          assignMutation.mutate();
        }}
        className="flex items-end gap-2"
      >
        <Field label="Add role" htmlFor="new_role">
          <Select
            id="new_role"
            required
            value={newRole}
            onChange={(e) => setNewRole(e.target.value)}
            className="w-56"
          >
            <option value="" disabled>
              Select a role…
            </option>
            {availableRoles.map((r) => (
              <option key={r.role_code} value={r.role_code}>
                {r.label}
              </option>
            ))}
          </Select>
        </Field>
        <Button type="submit" disabled={assignMutation.isPending || !newRole}>
          Assign
        </Button>
      </form>
    </section>
  );
}

function ScopesSection({
  userId,
  scopes,
}: {
  userId: number;
  scopes: UserDetailType["scopes"];
}) {
  const queryClient = useQueryClient();
  const [scopeType, setScopeType] = useState("AREA");
  const [scopeValue, setScopeValue] = useState("");
  const [error, setError] = useState<string | null>(null);

  const assignMutation = useMutation({
    mutationFn: () =>
      apiPost(`/api/v1/users/${userId}/scopes`, {
        scope_type: scopeType,
        scope_value: scopeType === "ALL" ? "*" : scopeValue,
      }),
    onSuccess: () => {
      setError(null);
      setScopeValue("");
      void queryClient.invalidateQueries({ queryKey: ["user", String(userId)] });
    },
    onError: (err) => setError(err instanceof Error ? err.message : "Could not add scope"),
  });

  const revokeMutation = useMutation({
    mutationFn: (scopeId: number) => apiDelete(`/api/v1/users/${userId}/scopes/${scopeId}`),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["user", String(userId)] }),
  });

  return (
    <section className="border-t border-border p-4">
      <h2 className="mb-1 font-ui text-h2 text-text">Branch scope</h2>
      <p className="mb-3 font-ui text-small text-text-3">
        A user can hold several scope grants — e.g. an Area Head covering multiple areas. Effective
        scope is the union of all of them, plus any branch where this user is the assigned OM.
      </p>
      <ul className="mb-3 flex flex-col gap-1">
        {scopes.map((s) => (
          <li key={s.scope_id} className="flex items-center gap-3 font-ui text-body text-text">
            <Badge tone={s.scope_type === "ALL" ? "attention" : "neutral"}>{s.scope_type}</Badge>
            <span className="font-data tabular-nums">{s.scope_value}</span>
            <button
              type="button"
              onClick={() => revokeMutation.mutate(s.scope_id)}
              className="font-ui text-small text-negative hover:underline"
            >
              Revoke
            </button>
          </li>
        ))}
        {scopes.length === 0 && (
          <li className="font-ui text-small text-text-3">
            No scope granted — this user sees nothing (deny by default).
          </li>
        )}
      </ul>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          assignMutation.mutate();
        }}
        className="flex flex-wrap items-end gap-2"
      >
        <Field label="Scope type" htmlFor="scope_type">
          <Select
            id="scope_type"
            value={scopeType}
            onChange={(e) => setScopeType(e.target.value)}
            className="w-36"
          >
            {SCOPE_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </Select>
        </Field>
        {scopeType !== "ALL" && (
          <Field label="Value (code)" htmlFor="scope_value">
            <Input
              id="scope_value"
              required
              placeholder={
                scopeType === "AREA" ? "e.g. AREA_QC" : scopeType === "LOCATION" ? "e.g. KLN" : "code"
              }
              value={scopeValue}
              onChange={(e) => setScopeValue(e.target.value)}
              className="w-40"
            />
          </Field>
        )}
        <Button type="submit" disabled={assignMutation.isPending}>
          Add scope
        </Button>
      </form>
      {error && <p className="mt-2 font-ui text-small text-negative">{error}</p>}
    </section>
  );
}
