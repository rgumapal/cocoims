import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { apiDelete, apiGet, apiPatch, apiPost } from "@/api/client";
import type {
  Area,
  Cluster,
  Location,
  Page,
  Role,
  Route,
  User,
  UserDetail as UserDetailType,
} from "@/api/types";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Field, Input, Select } from "@/components/ui/Field";
import { PageHeader } from "@/components/ui/PageHeader";

const SCOPE_TYPES = ["LOCATION", "AREA", "CLUSTER", "ROUTE", "ALL"];

interface IdentityForm {
  email: string;
  full_name: string;
  role_hint: string;
  is_service: boolean;
}

const EMPTY_IDENTITY: IdentityForm = { email: "", full_name: "", role_hint: "", is_service: false };

function userToIdentityForm(user: UserDetailType): IdentityForm {
  return {
    email: user.email,
    full_name: user.full_name,
    role_hint: user.role_hint ?? "",
    is_service: user.is_service,
  };
}

export default function UserDetailPage() {
  const { userId } = useParams<{ userId: string }>();
  const isCreating = userId === "new";
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: user, isLoading } = useQuery({
    queryKey: ["user", userId],
    queryFn: () => apiGet<UserDetailType>(`/api/v1/users/${userId}`),
    enabled: !isCreating,
  });

  const { data: allRoles } = useQuery({
    queryKey: ["roles"],
    queryFn: () => apiGet<Role[]>("/api/v1/roles"),
  });

  // Only identity fields go through this form — roles and branch scope
  // (below) need a real user_id to attach to, so they're not offered until
  // the account exists (SPEC: creating an identity and granting it
  // authority are deliberately separate steps, mirroring ItemDetailPage's
  // create-then-manage-children pattern for aliases/prices).
  const [form, setForm] = useState<IdentityForm>(EMPTY_IDENTITY);
  const [error, setError] = useState<string | null>(null);
  // Shown once, right after creating a user — never persisted, never
  // refetchable, so this is the only chance to hand it to the admin.
  const [passwordSetupLink, setPasswordSetupLink] = useState<string | null>(null);

  const [syncedFor, setSyncedFor] = useState<string | null>(null);
  if (user && syncedFor !== userId) {
    setForm(userToIdentityForm(user));
    setSyncedFor(userId ?? null);
  }

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (isCreating) {
        return apiPost<User>("/api/v1/users", {
          email: form.email,
          full_name: form.full_name,
          role_hint: form.role_hint || null,
          is_service: form.is_service,
        });
      }
      // email and is_service are fixed at creation (no UserUpdate support
      // for changing them — see backend/app/api/v1/users.py); only name
      // and position are editable afterwards.
      return apiPatch<User>(`/api/v1/users/${userId}`, {
        full_name: form.full_name,
        role_hint: form.role_hint || null,
      });
    },
    onSuccess: (saved) => {
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["users"] });
      if (isCreating) {
        if (saved.password_setup_link) setPasswordSetupLink(saved.password_setup_link);
        navigate(`/users/${saved.user_id}`, { replace: true });
      } else {
        void queryClient.invalidateQueries({ queryKey: ["user", userId] });
      }
    },
    onError: (err) => setError(err instanceof Error ? err.message : "Could not save user"),
  });

  const toggleActiveMutation = useMutation({
    mutationFn: () => apiPatch(`/api/v1/users/${userId}`, { is_active: !user?.is_active }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["user", userId] }),
  });

  if (!isCreating && (isLoading || !user)) {
    return <div className="p-4 font-ui text-body text-text-3">Loading…</div>;
  }

  return (
    <div className="mx-auto max-w-2xl p-4">
      <PageHeader
        title={isCreating ? "New User" : user!.full_name}
        description={
          isCreating
            ? "Create the account first — roles and branch scope are granted once it exists."
            : undefined
        }
        actions={
          !isCreating && (
            <>
              <Badge tone={user!.is_active ? "positive" : "negative"}>
                {user!.is_active ? "Active" : "Inactive"}
              </Badge>
              <Button
                variant={user!.is_active ? "danger" : "secondary"}
                onClick={() => toggleActiveMutation.mutate()}
              >
                {user!.is_active ? "Deactivate" : "Reactivate"}
              </Button>
            </>
          )
        }
      />

      {passwordSetupLink && (
        <div className="m-4 flex flex-col gap-2 rounded-md border border-border-strong bg-surface-2 p-4">
          <p className="font-ui text-body font-medium text-text">
            Account created. Send this one-time link to the user so they can set their password —
            it won't be shown again.
          </p>
          <div className="flex items-center gap-2">
            <input
              readOnly
              value={passwordSetupLink}
              onFocus={(e) => e.currentTarget.select()}
              className="flex-1 rounded-md border border-border bg-surface px-2 py-1.5 font-data text-small text-text"
            />
            <Button
              type="button"
              onClick={() => void navigator.clipboard.writeText(passwordSetupLink)}
            >
              Copy
            </Button>
            <Button type="button" variant="secondary" onClick={() => setPasswordSetupLink(null)}>
              Dismiss
            </Button>
          </div>
        </div>
      )}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          saveMutation.mutate();
        }}
        className="flex flex-col gap-4 p-4"
      >
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Email" htmlFor="u_email">
            <Input
              id="u_email"
              type="email"
              required
              disabled={!isCreating}
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
            />
          </Field>
          <Field label="Name" htmlFor="u_name">
            <Input
              id="u_name"
              required
              value={form.full_name}
              onChange={(e) => setForm({ ...form, full_name: e.target.value })}
            />
          </Field>
          <Field label="Position" htmlFor="u_position">
            <Input
              id="u_position"
              placeholder="e.g. Operations Manager - North"
              value={form.role_hint}
              onChange={(e) => setForm({ ...form, role_hint: e.target.value })}
            />
          </Field>
        </div>
        {isCreating && (
          <label htmlFor="u_service" className="flex items-center gap-1.5 font-ui text-body text-text">
            <input
              id="u_service"
              type="checkbox"
              checked={form.is_service}
              onChange={(e) => setForm({ ...form, is_service: e.target.checked })}
            />
            Service account (no interactive login)
          </label>
        )}
        {/* Every seeded/created account is SSO-first — no password field
            here. Local dev passwords are set out-of-band (see
            backend/scripts/set_dev_passwords.py), never through this form. */}

        {error && <p className="font-ui text-small text-negative">{error}</p>}

        <div>
          <Button type="submit" variant="primary" disabled={saveMutation.isPending}>
            {saveMutation.isPending ? "Saving…" : isCreating ? "Create user" : "Save"}
          </Button>
        </div>
      </form>

      {!isCreating && user && (
        <>
          <RolesSection userId={user.user_id} currentRoles={user.roles} allRoles={allRoles ?? []} />
          <ScopesSection userId={user.user_id} scopes={user.scopes} />
        </>
      )}
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

  // Fetched once and picked from by scope type, rather than free-typed —
  // a typo'd scope_value silently grants access to nothing (deny by
  // default hides the mistake instead of erroring), so the value has to
  // come from an actual code, not a guess.
  const { data: locations } = useQuery({
    queryKey: ["locations-picker"],
    queryFn: () => apiGet<Page<Location>>("/api/v1/locations?limit=200"),
    enabled: scopeType === "LOCATION",
  });
  const { data: areas } = useQuery({
    queryKey: ["areas"],
    queryFn: () => apiGet<Area[]>("/api/v1/areas"),
    enabled: scopeType === "AREA",
  });
  const { data: clusters } = useQuery({
    queryKey: ["clusters"],
    queryFn: () => apiGet<Cluster[]>("/api/v1/clusters"),
    enabled: scopeType === "CLUSTER",
  });
  const { data: routes } = useQuery({
    queryKey: ["routes"],
    queryFn: () => apiGet<Route[]>("/api/v1/routes"),
    enabled: scopeType === "ROUTE",
  });

  const scopeValueOptions: { value: string; label: string }[] =
    scopeType === "LOCATION"
      ? (locations?.items ?? []).map((l) => ({
          value: l.location_code,
          label: `${l.location_code} — ${l.location_name}`,
        }))
      : scopeType === "AREA"
        ? (areas ?? []).map((a) => ({ value: a.area_code, label: a.label }))
        : scopeType === "CLUSTER"
          ? (clusters ?? []).map((c) => ({ value: c.cluster_code, label: c.label }))
          : scopeType === "ROUTE"
            ? (routes ?? []).map((r) => ({ value: r.route_code, label: r.label }))
            : [];

  function handleScopeTypeChange(nextType: string): void {
    setScopeType(nextType);
    setScopeValue(""); // a value picked for the old type is meaningless for the new one
  }

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
            onChange={(e) => handleScopeTypeChange(e.target.value)}
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
            <Select
              id="scope_value"
              required
              value={scopeValue}
              onChange={(e) => setScopeValue(e.target.value)}
              className="w-56"
            >
              <option value="">Select…</option>
              {scopeValueOptions.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </Select>
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
