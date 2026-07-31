import { useQuery } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { useNavigate } from "react-router-dom";
import { apiGet } from "@/api/client";
import type { User } from "@/api/types";
import { Badge } from "@/components/ui/Badge";
import { DataTable } from "@/components/DataTable";
import { PageHeader } from "@/components/ui/PageHeader";

const columns: ColumnDef<User, any>[] = [
  { accessorKey: "email", header: "Email" },
  { accessorKey: "full_name", header: "Name" },
  {
    accessorKey: "is_service",
    header: "Type",
    size: 110,
    cell: (ctx) => (
      <Badge tone={ctx.getValue<boolean>() ? "attention" : "neutral"}>
        {ctx.getValue<boolean>() ? "Service" : "Interactive"}
      </Badge>
    ),
  },
  {
    accessorKey: "is_active",
    header: "Status",
    size: 100,
    cell: (ctx) => (
      <Badge tone={ctx.getValue<boolean>() ? "positive" : "negative"}>
        {ctx.getValue<boolean>() ? "Active" : "Inactive"}
      </Badge>
    ),
  },
  { accessorKey: "last_login_at", header: "Last login" },
];

export default function UsersListPage() {
  const navigate = useNavigate();

  const { data: users, isLoading } = useQuery({
    queryKey: ["users"],
    queryFn: () => apiGet<User[]>("/api/v1/users"),
  });

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Users & Roles"
        description="Manage accounts, roles, and branch access."
      />
      <div className="flex-1 overflow-hidden">
        <DataTable
          data={users ?? []}
          columns={columns}
          isLoading={isLoading}
          onRowClick={(u) => navigate(`/users/${u.user_id}`)}
          emptyMessage="No users yet."
        />
      </div>
    </div>
  );
}
