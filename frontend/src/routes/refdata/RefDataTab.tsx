import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiGet, apiPost } from "@/api/client";
import { RequirePermission } from "@/auth/RequireAuth";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Field, Input, Select } from "@/components/ui/Field";

/** One field's shape in a ref-data table's create form. */
interface FieldConfig {
  name: string;
  label: string;
  type: "text" | "number" | "checkbox" | "select";
  required?: boolean;
  options?: string[]; // for type: "select"
}

interface RefDataTabProps {
  /** URL segment — e.g. "categories" for /api/v1/categories. */
  resourcePath: string;
  /** The table's primary-key field name — e.g. "category_code". */
  pkField: string;
  pkLabel: string;
  fields: FieldConfig[];
}

type RefRow = Record<string, unknown>;

/** Mirrors the backend's register_code_table_crud (app/api/v1/refdata.py):
 * six reference tables (categories, uom, clusters, areas, routes,
 * reason-codes) share the exact same shape — a code primary key plus
 * is_active — so one generic component handles all six rather than
 * duplicating near-identical list/create/deactivate logic six times.
 */
export function RefDataTab({ resourcePath, pkField, pkLabel, fields }: RefDataTabProps) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<Record<string, string | boolean>>({});
  const [error, setError] = useState<string | null>(null);

  const { data: rows, isLoading } = useQuery({
    queryKey: ["refdata", resourcePath],
    queryFn: () => apiGet<RefRow[]>(`/api/v1/${resourcePath}`),
  });

  const createMutation = useMutation({
    mutationFn: () => apiPost<RefRow>(`/api/v1/${resourcePath}`, form),
    onSuccess: () => {
      setError(null);
      setForm({});
      void queryClient.invalidateQueries({ queryKey: ["refdata", resourcePath] });
    },
    onError: (err) => setError(err instanceof Error ? err.message : "Could not create"),
  });

  const deactivateMutation = useMutation({
    // The backend route is POST, not PATCH (app/api/v1/refdata.py's
    // register_code_table_crud registers deactivate as @router.post) —
    // confirmed live: PATCH returned 405 before this fix.
    mutationFn: (code: string) => apiPost<RefRow>(`/api/v1/${resourcePath}/${code}/deactivate`),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["refdata", resourcePath] }),
  });

  return (
    <div className="p-4">
      <table className="mb-6 w-full border-collapse">
        <thead>
          <tr className="border-b border-border">
            <th className="px-2 py-2 text-left font-dense text-micro uppercase tracking-[0.06em] text-text-2">
              {pkLabel}
            </th>
            {fields.map((f) => (
              <th
                key={f.name}
                className="px-2 py-2 text-left font-dense text-micro uppercase tracking-[0.06em] text-text-2"
              >
                {f.label}
              </th>
            ))}
            <th className="px-2 py-2 text-left font-dense text-micro uppercase tracking-[0.06em] text-text-2">
              Status
            </th>
            <RequirePermission permission="refdata.manage">
              <th className="px-2 py-2" />
            </RequirePermission>
          </tr>
        </thead>
        <tbody>
          {isLoading && (
            <tr>
              <td colSpan={fields.length + 3} className="px-2 py-3 font-ui text-body text-text-3">
                Loading…
              </td>
            </tr>
          )}
          {rows?.map((row) => (
            <tr key={String(row[pkField])} className="border-b border-border">
              <td className="px-2 py-1.5 font-data text-body text-text">{String(row[pkField])}</td>
              {fields.map((f) => (
                <td key={f.name} className="px-2 py-1.5 font-ui text-body text-text">
                  {f.type === "checkbox"
                    ? row[f.name]
                      ? "Yes"
                      : "No"
                    : String(row[f.name] ?? "—")}
                </td>
              ))}
              <td className="px-2 py-1.5">
                <Badge tone={row.is_active ? "positive" : "neutral"}>
                  {row.is_active ? "Active" : "Inactive"}
                </Badge>
              </td>
              <RequirePermission permission="refdata.manage">
                <td className="px-2 py-1.5">
                  {row.is_active ? (
                    <button
                      type="button"
                      onClick={() => deactivateMutation.mutate(String(row[pkField]))}
                      className="font-ui text-small text-negative hover:underline"
                    >
                      Deactivate
                    </button>
                  ) : null}
                </td>
              </RequirePermission>
            </tr>
          ))}
          {rows?.length === 0 && !isLoading && (
            <tr>
              <td colSpan={fields.length + 3} className="px-2 py-3 font-ui text-body text-text-3">
                No records yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <RequirePermission permission="refdata.manage">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            createMutation.mutate();
          }}
          className="flex flex-wrap items-end gap-2 border-t border-border pt-4"
        >
          <Field label={pkLabel} htmlFor={`new-${pkField}`}>
            <Input
              id={`new-${pkField}`}
              required
              value={(form[pkField] as string) ?? ""}
              onChange={(e) => setForm({ ...form, [pkField]: e.target.value })}
              className="w-40"
            />
          </Field>
          {fields.map((f) => (
            <Field key={f.name} label={f.label} htmlFor={`new-${f.name}`}>
              {f.type === "checkbox" ? (
                <input
                  id={`new-${f.name}`}
                  type="checkbox"
                  checked={(form[f.name] as boolean) ?? false}
                  onChange={(e) => setForm({ ...form, [f.name]: e.target.checked })}
                />
              ) : f.type === "select" ? (
                <Select
                  id={`new-${f.name}`}
                  required={f.required}
                  value={(form[f.name] as string) ?? ""}
                  onChange={(e) => setForm({ ...form, [f.name]: e.target.value })}
                  className="w-40"
                >
                  <option value="" disabled>
                    Select…
                  </option>
                  {f.options?.map((o) => (
                    <option key={o} value={o}>
                      {o}
                    </option>
                  ))}
                </Select>
              ) : (
                <Input
                  id={`new-${f.name}`}
                  type={f.type === "number" ? "number" : "text"}
                  required={f.required}
                  value={(form[f.name] as string) ?? ""}
                  onChange={(e) => setForm({ ...form, [f.name]: e.target.value })}
                  className="w-40"
                />
              )}
            </Field>
          ))}
          <Button type="submit" variant="primary" disabled={createMutation.isPending}>
            Add
          </Button>
        </form>
      </RequirePermission>
      {error && <p className="mt-2 font-ui text-small text-negative">{error}</p>}
    </div>
  );
}
