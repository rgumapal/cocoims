import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { apiGet } from "@/api/client";
import type { DashboardSummary } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { Badge } from "@/components/ui/Badge";
import { PageHeader } from "@/components/ui/PageHeader";
import {
  BranchesIcon,
  CountsIcon,
  ItemsIcon,
  ReceivingIcon,
  RefDataIcon,
  SalesIcon,
  StockIcon,
  UsersIcon,
  WasteIcon,
} from "@/components/icons";

const CARD_CLASSES =
  "flex flex-col gap-2 rounded-lg border border-border bg-surface p-4 text-left transition-colors duration-theme hover:border-border-strong hover:bg-surface-hover";

// Rounded, comma-grouped pesos — a dashboard headline reads faster without
// cents (SalesPage itself still shows exact centavos where that precision
// matters for a single line item). null (not 0) is a real state here: no
// branch had any sales today, so there's nothing to show a peso sign next
// to (CLAUDE.md DATA: never coerce a "no data" absence into a 0).
function formatMoney(value: string | null): string {
  if (value === null) return "—";
  const n = Number(value);
  return Number.isFinite(n) ? `₱${Math.round(n).toLocaleString()}` : "—";
}

export default function DashboardPage() {
  const { hasPermission } = useAuth();

  // Cheap by design: one round trip for every card on this page, not one
  // query per widget — TanStack Query's own cache/loading/error states are
  // the "one obvious way" for server data (CLAUDE.md), so no hand-rolled
  // per-card fetching here either.
  const { data, isLoading, isError } = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => apiGet<DashboardSummary>("/api/v1/dashboard"),
  });

  return (
    <div className="flex h-full flex-col overflow-auto">
      <PageHeader
        title="Dashboard"
        description="Today's snapshot across every screen — click any card to dive in."
      />

      <div className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-2 lg:grid-cols-3">
        {isLoading && <DashboardSkeleton />}

        {isError && (
          <div className="col-span-full rounded-lg border border-border bg-surface p-4 font-ui text-body text-text-2">
            Couldn't load your dashboard summary. Try refreshing the page.
          </div>
        )}

        {data && (
          <>
            {data.receiving && (
              <StatCard to="/receiving" icon={<ReceivingIcon />} title="Receiving">
                <Stat
                  value={data.receiving.branches_reported_today}
                  label={`of ${data.receiving.active_branch_count} active branches reported`}
                />
                <SubStat
                  value={data.receiving.items_received_today}
                  label="items received"
                  badge={data.receiving.is_low ? "Low" : undefined}
                />
              </StatCard>
            )}

            {data.sales && (
              <StatCard to="/sales" icon={<SalesIcon />} title="Sales">
                <Stat value={formatMoney(data.sales.total_sales)} label="total sales today" />
                {data.sales.branches_reporting > 0 && (
                  <p className="font-data text-small tabular-nums text-text-2">
                    High: {formatMoney(data.sales.highest_branch_sales)}, Low:{" "}
                    {formatMoney(data.sales.lowest_branch_sales)}, Avg:{" "}
                    {formatMoney(data.sales.average_branch_sales)}
                  </p>
                )}
                <p className="font-ui text-micro text-text-3">
                  {data.sales.branches_reporting} branch
                  {data.sales.branches_reporting === 1 ? "" : "es"}, {data.sales.total_items_sold} item
                  {data.sales.total_items_sold === 1 ? "" : "s"} reported
                </p>
              </StatCard>
            )}

            {data.waste && (
              <StatCard to="/waste" icon={<WasteIcon />} title="Waste Log">
                <Stat value={data.waste.items_logged_today} label="items logged today" />
              </StatCard>
            )}

            {data.counts && (
              <StatCard to="/counts" icon={<CountsIcon />} title="Counts">
                <Stat value={data.counts.open_count} label="open counts" />
                <SubStat
                  value={data.counts.pending_approval_count}
                  label="awaiting approval"
                  tone={data.counts.pending_approval_count > 0 ? "attention" : undefined}
                />
              </StatCard>
            )}

            {data.stock && (
              <StatCard to="/stock" icon={<StockIcon />} title="Stock Explorer">
                <Stat
                  value={data.stock.run_outs_today}
                  label="branch/item run-outs today"
                  badge={data.stock.run_outs_today > 0 ? "Needs attention" : undefined}
                />
              </StatCard>
            )}

            {data.items && (
              <StatCard to="/items" icon={<ItemsIcon />} title="Items">
                <Stat
                  value={data.items.active_count}
                  label={`active, of ${data.items.total_count} total`}
                />
              </StatCard>
            )}

            {data.branches && (
              <StatCard to="/branches" icon={<BranchesIcon />} title="Branches">
                <Stat
                  value={data.branches.active_count}
                  label={`active, of ${data.branches.total_count} total`}
                />
              </StatCard>
            )}

            {/* Reference Data and Users & Roles carry no daily stats — the
                nav doesn't gate Reference Data behind a permission either
                (see AppShell.tsx), so it's always offered; Users & Roles
                mirrors the nav's own user.manage gate. */}
            <StatCard to="/refdata" icon={<RefDataIcon />} title="Reference Data">
              <p className="font-ui text-small text-text-2">
                Categories, units, clusters, areas, routes, and reason codes shared across the
                system.
              </p>
            </StatCard>

            {hasPermission("user.manage") && (
              <StatCard to="/users" icon={<UsersIcon />} title="Users & Roles">
                <p className="font-ui text-small text-text-2">
                  Manage accounts, roles, and branch access.
                </p>
              </StatCard>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function StatCard({
  to,
  icon,
  title,
  children,
}: {
  to: string;
  icon: ReactNode;
  title: string;
  children: ReactNode;
}) {
  return (
    <Link to={to} className={CARD_CLASSES}>
      <div className="flex items-center gap-2 text-text-2">
        {icon}
        <span className="font-ui text-h2 text-text">{title}</span>
      </div>
      {children}
    </Link>
  );
}

function Stat({
  value,
  label,
  badge,
}: {
  value: number | string;
  label: string;
  badge?: string;
}) {
  return (
    <div className="flex items-baseline gap-2">
      <span className="font-data text-h1 tabular-nums text-text">{value}</span>
      <span className="font-ui text-small text-text-2">{label}</span>
      {badge && <Badge tone="attention">{badge}</Badge>}
    </div>
  );
}

function SubStat({
  value,
  label,
  tone,
  badge,
}: {
  value: number | string;
  label: string;
  tone?: "attention";
  badge?: string;
}) {
  return (
    <div className="flex items-baseline gap-1.5">
      <span className="font-data text-body tabular-nums text-text-2">{value}</span>
      <span className="font-ui text-micro text-text-3">{label}</span>
      {(badge || tone) && <Badge tone={tone ?? "attention"}>{badge ?? "!"}</Badge>}
    </div>
  );
}

// SPEC §12.6 rule 6: never a blank screen — shaped like the grid it
// replaces, not a bare spinner.
function DashboardSkeleton() {
  return (
    <>
      {Array.from({ length: 9 }).map((_, i) => (
        <div
          key={i}
          className="animate-pulse rounded-lg border border-border bg-surface p-4"
          aria-hidden="true"
        >
          <div className="mb-3 h-5 w-24 rounded bg-surface-2" />
          <div className="h-8 w-16 rounded bg-surface-2" />
        </div>
      ))}
    </>
  );
}
