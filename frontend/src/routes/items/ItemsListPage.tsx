import { useQuery } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiGet } from "@/api/client";
import type { Item, Page } from "@/api/types";
import { RequirePermission } from "@/auth/RequireAuth";
import { DataTable, NumericCell } from "@/components/DataTable";
import { Button } from "@/components/ui/Button";
import { StatusBadge } from "@/components/ui/Badge";
import { Input } from "@/components/ui/Field";
import { PageHeader } from "@/components/ui/PageHeader";

const columns: ColumnDef<Item, any>[] = [
  { accessorKey: "item_code", header: "Code", size: 90 },
  { accessorKey: "display_name", header: "Name" },
  { accessorKey: "replen_policy", header: "Policy", size: 110 },
  {
    accessorKey: "shelf_life_days",
    header: "Shelf life",
    size: 100,
    cell: (ctx) => <NumericCell value={ctx.getValue<number>()} />,
  },
  {
    accessorKey: "moq",
    header: "MOQ",
    size: 90,
    cell: (ctx) => <NumericCell value={ctx.getValue<string>()} />,
  },
  {
    accessorKey: "lifecycle_status",
    header: "Status",
    size: 140,
    cell: (ctx) => <StatusBadge status={ctx.getValue<string>()} />,
  },
];

export default function ItemsListPage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  // SPEC §12.6: debounce search/filter inputs (~250ms) — never fire a
  // request per keystroke.
  const debouncedSearch = useDebouncedValue(search, 250);

  const { data, isLoading } = useQuery({
    queryKey: ["items", debouncedSearch],
    queryFn: () =>
      apiGet<Page<Item>>(
        `/api/v1/items${debouncedSearch ? `?search=${encodeURIComponent(debouncedSearch)}` : ""}`,
      ),
  });

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Items"
        description="The network item master — SKUs, pricing, and lifecycle status."
        actions={
          <RequirePermission permission="item.create">
            <Button variant="primary" onClick={() => navigate("/items/new")}>
              New Item
            </Button>
          </RequirePermission>
        }
      />
      <div className="border-b border-border px-4 py-2">
        <Input
          placeholder="Search by name or code…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />
      </div>
      <div className="flex-1 overflow-hidden">
        <DataTable
          data={data?.items ?? []}
          columns={columns}
          isLoading={isLoading}
          onRowClick={(item) => navigate(`/items/${item.item_code}`)}
          emptyMessage={
            debouncedSearch ? `No items match "${debouncedSearch}".` : "No items yet."
          }
        />
      </div>
    </div>
  );
}

// A tiny local debounce helper — this is the only place in the app that
// needs one so far; if a second screen needs the same pattern, promote it
// to src/hooks (rule of three, per CLAUDE.md YAGNI).
function useDebouncedValue(value: string, delayMs: number): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}
