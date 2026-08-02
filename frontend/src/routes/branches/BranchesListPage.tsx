import { useQuery } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { useNavigate } from "react-router-dom";
import { apiGet } from "@/api/client";
import type { Location, Page } from "@/api/types";
import { DataTable } from "@/components/DataTable";
import { StatusBadge } from "@/components/ui/Badge";
import { PageHeader } from "@/components/ui/PageHeader";

const columns: ColumnDef<Location, any>[] = [
  { accessorKey: "location_code", header: "Code", size: 90 },
  { accessorKey: "location_name", header: "Name" },
  { accessorKey: "location_type", header: "Type", size: 110 },
  { accessorKey: "area_code", header: "Area", size: 130 },
  { accessorKey: "cluster_code", header: "Cluster", size: 130 },
  {
    accessorKey: "status",
    header: "Status",
    size: 140,
    cell: (ctx) => <StatusBadge status={ctx.getValue<string>()} />,
  },
];

export default function BranchesListPage() {
  const navigate = useNavigate();

  // 122 locations is already past SPEC §12.5's ~100-row virtualization
  // threshold, and there is no branch onboarding wizard yet (SPEC §5.2 —
  // deferred), so "New Branch" isn't offered here: creating a location
  // without the guided flow (assortment, schedule, OM) is a real gap the
  // wizard exists specifically to close, and a bare form would silently
  // skip it.
  // include_system=true: this is the one screen that should show the
  // transfers in-transit bucket alongside real branches/commissary, for
  // admin visibility — every other location picker in the app defaults to
  // excluding it (see backend/app/api/v1/locations.py's list_locations).
  const { data, isLoading } = useQuery({
    queryKey: ["locations", "all"],
    queryFn: () => apiGet<Page<Location>>("/api/v1/locations?limit=200&include_system=true"),
  });

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Branches"
        description="Every Cocopan branch — its status, area/cluster/route assignment, and the Operations Manager responsible for it. Status drives whether a branch can be ordered for and forecasted; every change here is logged to its status history, never overwritten."
      />
      <div className="flex-1 overflow-hidden">
        <DataTable
          data={data?.items ?? []}
          columns={columns}
          isLoading={isLoading}
          onRowClick={(loc) => navigate(`/branches/${loc.location_code}`)}
        />
      </div>
    </div>
  );
}
