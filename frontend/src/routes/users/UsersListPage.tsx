import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { useNavigate } from "react-router-dom";
import { apiGet, apiPatch } from "@/api/client";
import type { User } from "@/api/types";
import { RequirePermission } from "@/auth/RequireAuth";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { DataTable } from "@/components/DataTable";
import { PageHeader } from "@/components/ui/PageHeader";

export default function UsersListPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: users, isLoading } = useQuery({
    queryKey: ["users"],
    queryFn: () => apiGet<User[]>("/api/v1/users"),
  });

  // Optimistic toggle straight from the list row (SPEC §12.6 rule 7): the
  // Active/Inactive badge flips immediately, with a rollback to the prior
  // list if the PATCH fails, rather than waiting on a refetch.
  const toggleActiveMutation = useMutation({
    mutationFn: (user: User) => apiPatch(`/api/v1/users/${user.user_id}`, { is_active: !user.is_active }),
    onMutate: async (user: User) => {
      await queryClient.cancelQueries({ queryKey: ["users"] });
      const previous = queryClient.getQueryData<User[]>(["users"]);
      queryClient.setQueryData<User[]>(["users"], (old) =>
        old?.map((u) => (u.user_id === user.user_id ? { ...u, is_active: !u.is_active } : u)),
      );
      return { previous };
    },
    onError: (_err, _user, context) => {
      if (context?.previous) queryClient.setQueryData(["users"], context.previous);
    },
    onSettled: () => void queryClient.invalidateQueries({ queryKey: ["users"] }),
  });

  const columns: ColumnDef<User, any>[] = [
    { accessorKey: "email", header: "Email" },
    { accessorKey: "full_name", header: "Name" },
    {
      accessorKey: "role_hint",
      header: "Position",
      size: 160,
      cell: (ctx) => {
        const position = ctx.getValue<string | null>();
        return position ? <span>{position}</span> : <span className="text-text-3">—</span>;
      },
    },
    {
      accessorKey: "roles",
      header: "Roles",
      size: 180,
      cell: (ctx) => {
        const roles = ctx.getValue<string[]>();
        return roles.length === 0 ? (
          <span className="text-text-3">None</span>
        ) : (
          <div className="flex flex-wrap gap-1">
            {roles.map((r) => (
              <Badge key={r}>{r}</Badge>
            ))}
          </div>
        );
      },
    },
    {
      accessorKey: "scope_summary",
      header: "Scope",
      size: 220,
      cell: (ctx) => {
        const scope = ctx.getValue<string[]>();
        return scope.length === 0 ? (
          <span className="text-negative">No scope</span>
        ) : (
          <span className="font-ui text-body text-text-2">{scope.join(", ")}</span>
        );
      },
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
    {
      id: "actions",
      header: "",
      size: 190,
      cell: (ctx) => {
        const user = ctx.row.original;
        return (
          <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
            <Button onClick={() => navigate(`/users/${user.user_id}`)}>Modify</Button>
            {/* Deliberately never "primary" here: gold is one button per
                screen (CLAUDE.md DESIGN), and this button repeats once per
                row — "danger" for the destructive direction, plain
                "secondary" (the Button default) for the reversible one. */}
            <Button
              variant={user.is_active ? "danger" : "secondary"}
              disabled={toggleActiveMutation.isPending}
              onClick={() => toggleActiveMutation.mutate(user)}
            >
              {user.is_active ? "Deactivate" : "Reactivate"}
            </Button>
          </div>
        );
      },
    },
  ];

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Users & Roles"
        description="Every account that can sign in: the position they hold, the roles that grant their permissions, and the branches those roles apply to. Authority is role × scope — a role decides what a user can do, scope decides where."
        actions={
          <RequirePermission permission="user.manage">
            <Button variant="primary" onClick={() => navigate("/users/new")}>
              New User
            </Button>
          </RequirePermission>
        }
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
