import { useQuery } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { useState } from "react";
import { apiGet, apiGetFile } from "@/api/client";
import type { AuditRecord, Page } from "@/api/types";
import { DataTable } from "@/components/DataTable";
import { StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Field, Input, Select } from "@/components/ui/Field";
import { PageHeader } from "@/components/ui/PageHeader";
import { daysAgoLocalDate, formatDateTime, todayLocalDate } from "@/lib/date";

// backend/app/api/v1/audit.py: last-two-days default matches the
// Dashboard's own Audit Logs card (both read "recent" the same way).
const DEFAULT_WINDOW_DAYS = 2;

function buildParams(startDate: string, endDate: string, tableName: string): URLSearchParams {
  const params = new URLSearchParams({ start_date: startDate, end_date: endDate, limit: "200" });
  if (tableName) params.set("table_name", tableName);
  return params;
}

export default function AuditLogPage() {
  const [startDate, setStartDate] = useState(() => daysAgoLocalDate(DEFAULT_WINDOW_DAYS));
  const [endDate, setEndDate] = useState(todayLocalDate);
  const [tableName, setTableName] = useState("");
  const [detail, setDetail] = useState<AuditRecord | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const [isExporting, setIsExporting] = useState(false);

  const { data: tables } = useQuery({
    queryKey: ["audit-tables"],
    queryFn: () => apiGet<string[]>("/api/v1/audit/tables"),
  });

  const params = buildParams(startDate, endDate, tableName);
  const { data, isLoading, isError } = useQuery({
    queryKey: ["audit", startDate, endDate, tableName],
    queryFn: () => apiGet<Page<AuditRecord>>(`/api/v1/audit?${params.toString()}`),
  });

  async function handleExport(): Promise<void> {
    setExportError(null);
    setIsExporting(true);
    try {
      const exportParams = buildParams(startDate, endDate, tableName);
      exportParams.delete("limit"); // export has its own server-side cap, not the list page size
      const { blob, filename } = await apiGetFile(`/api/v1/audit/export?${exportParams.toString()}`);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setExportError(err instanceof Error ? err.message : "Could not export the audit log");
    } finally {
      setIsExporting(false);
    }
  }

  const columns: ColumnDef<AuditRecord, any>[] = [
    {
      accessorKey: "occurred_at",
      header: "When",
      size: 140,
      cell: (ctx) => formatDateTime(ctx.getValue<string>()),
    },
    { accessorKey: "table_name", header: "Table", size: 140 },
    { accessorKey: "record_pk", header: "Record", size: 140 },
    {
      accessorKey: "action",
      header: "Action",
      size: 100,
      cell: (ctx) => <StatusBadge status={ctx.getValue<string>()} />,
    },
    {
      id: "changed_by",
      header: "Changed by",
      size: 220,
      cell: (ctx) => ctx.row.original.changed_by_full_name ?? ctx.row.original.changed_by_email ?? "—",
    },
    {
      accessorKey: "changed_fields",
      header: "Fields changed",
      cell: (ctx) => ctx.getValue<string[] | null>()?.join(", ") ?? "—",
    },
  ];

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Audit Logs"
        description="Every create, update, and delete recorded against a reference or master table — who changed what, and when. Click a row to see the exact field values before and after."
        actions={
          <Button onClick={() => void handleExport()} disabled={isExporting}>
            {isExporting ? "Exporting…" : "Export CSV"}
          </Button>
        }
      />

      <div className="flex flex-wrap items-end gap-4 border-b border-border px-4 py-3">
        <Field label="Start date" htmlFor="a_start">
          <Input
            id="a_start"
            type="date"
            value={startDate}
            max={endDate}
            onChange={(e) => setStartDate(e.target.value || daysAgoLocalDate(DEFAULT_WINDOW_DAYS))}
          />
        </Field>
        <Field label="End date" htmlFor="a_end">
          <Input
            id="a_end"
            type="date"
            value={endDate}
            min={startDate}
            onChange={(e) => setEndDate(e.target.value || todayLocalDate())}
          />
        </Field>
        <Field label="Table" htmlFor="a_table">
          <Select id="a_table" value={tableName} onChange={(e) => setTableName(e.target.value)}>
            <option value="">All tables</option>
            {tables?.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </Select>
        </Field>
      </div>

      {exportError && <p className="px-4 pt-2 font-ui text-small text-negative">{exportError}</p>}

      {isError ? (
        <div className="m-4 rounded-lg border border-border bg-surface p-4 font-ui text-body text-text-2">
          Couldn't load the audit log. Try adjusting the date range.
        </div>
      ) : (
        <div className="flex-1 overflow-hidden">
          <DataTable
            data={data?.items ?? []}
            columns={columns}
            isLoading={isLoading}
            onRowClick={setDetail}
            emptyMessage="No changes recorded in this date range."
          />
        </div>
      )}

      <Dialog open={detail !== null} onClose={() => setDetail(null)} title="Change detail">
        {detail && (
          <div className="flex flex-col gap-3">
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 font-ui text-small">
              <dt className="text-text-2">When</dt>
              <dd className="text-text">{formatDateTime(detail.occurred_at)}</dd>
              <dt className="text-text-2">Table</dt>
              <dd className="text-text">
                {detail.schema_name}.{detail.table_name}
              </dd>
              <dt className="text-text-2">Record</dt>
              <dd className="text-text">{detail.record_pk}</dd>
              <dt className="text-text-2">Action</dt>
              <dd>
                <StatusBadge status={detail.action} />
              </dd>
              <dt className="text-text-2">Changed by</dt>
              <dd className="text-text">
                {detail.changed_by_full_name ?? detail.changed_by_email ?? "—"}
              </dd>
            </dl>
            <div className="flex flex-col gap-3">
              <div>
                <p className="mb-1 font-dense text-micro uppercase tracking-[0.06em] text-text-3">
                  Before
                </p>
                <pre className="max-h-40 overflow-auto rounded-md bg-surface-2 p-2 font-data text-micro text-text-2">
                  {detail.old_values ? JSON.stringify(detail.old_values, null, 2) : "—"}
                </pre>
              </div>
              <div>
                <p className="mb-1 font-dense text-micro uppercase tracking-[0.06em] text-text-3">
                  After
                </p>
                <pre className="max-h-40 overflow-auto rounded-md bg-surface-2 p-2 font-data text-micro text-text-2">
                  {detail.new_values ? JSON.stringify(detail.new_values, null, 2) : "—"}
                </pre>
              </div>
            </div>
            <div className="flex justify-end">
              <Button onClick={() => setDetail(null)}>Close</Button>
            </div>
          </div>
        )}
      </Dialog>
    </div>
  );
}
