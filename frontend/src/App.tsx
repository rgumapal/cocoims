import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "@/components/AppShell";
import { RequireAuth } from "@/auth/RequireAuth";

// Route-level code splitting (CLAUDE.md PERFORMANCE & UX): each screen is
// its own chunk, so e.g. the Reference Data admin screen's JS never ships
// on first paint for someone who only ever opens Receiving.
const LoginPage = lazy(() => import("@/routes/LoginPage"));
const ItemsListPage = lazy(() => import("@/routes/items/ItemsListPage"));
const ItemDetailPage = lazy(() => import("@/routes/items/ItemDetailPage"));
const BranchesListPage = lazy(() => import("@/routes/branches/BranchesListPage"));
const BranchDetailPage = lazy(() => import("@/routes/branches/BranchDetailPage"));
const RefDataPage = lazy(() => import("@/routes/refdata/RefDataPage"));
const StockExplorerPage = lazy(() => import("@/routes/stock/StockExplorerPage"));
const CountsListPage = lazy(() => import("@/routes/counts/CountsListPage"));
const CountDetailPage = lazy(() => import("@/routes/counts/CountDetailPage"));
const ReceivingPage = lazy(() => import("@/routes/receiving/ReceivingPage"));
const SalesPage = lazy(() => import("@/routes/sales/SalesPage"));
const WastePage = lazy(() => import("@/routes/waste/WastePage"));
const UsersListPage = lazy(() => import("@/routes/users/UsersListPage"));
const UserDetailPage = lazy(() => import("@/routes/users/UserDetailPage"));

function RouteFallback() {
  // Route-transition loading state — brief by design (a lazy chunk after
  // the first load is typically cached), so a minimal placeholder is
  // enough; each screen's own data-loading skeleton (DataTable's
  // TableSkeleton) is what SPEC §12.6 rule 6 is really asking for.
  return <div className="p-4 font-ui text-body text-text-3">Loading…</div>;
}

export function App() {
  return (
    <Suspense fallback={<RouteFallback />}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />

        <Route
          element={
            <RequireAuth>
              <AppShell />
            </RequireAuth>
          }
        >
          <Route path="/" element={<Navigate to="/items" replace />} />

          <Route path="/items" element={<ItemsListPage />} />
          <Route path="/items/:itemCode" element={<ItemDetailPage />} />

          <Route path="/branches" element={<BranchesListPage />} />
          <Route path="/branches/:locationCode" element={<BranchDetailPage />} />

          <Route path="/refdata" element={<RefDataPage />} />

          <Route path="/stock" element={<StockExplorerPage />} />

          <Route path="/counts" element={<CountsListPage />} />
          <Route path="/counts/:countId" element={<CountDetailPage />} />

          <Route path="/receiving" element={<ReceivingPage />} />
          <Route path="/sales" element={<SalesPage />} />
          <Route path="/waste" element={<WastePage />} />

          <Route path="/users" element={<UsersListPage />} />
          <Route path="/users/:userId" element={<UserDetailPage />} />
        </Route>
      </Routes>
    </Suspense>
  );
}
