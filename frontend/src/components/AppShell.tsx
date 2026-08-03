import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "@/auth/AuthContext";
import { useTheme } from "@/design/ThemeContext";
import {
  BranchesIcon,
  CountsIcon,
  DashboardIcon,
  ItemsIcon,
  ReceivingIcon,
  RefDataIcon,
  SalesIcon,
  StockIcon,
  TransfersIcon,
  UsersIcon,
  WasteIcon,
} from "@/components/icons";

// SPEC §12.5: single fixed 56px top bar, collapsible 220px left nav,
// content maximised — no nested panels.
//
// Four groups. STORE_TEAM (the narrowest role) can act on all of
// Receiving/Sales/Waste/Counts, but Counts is split from the other three
// on purpose: Receiving, Sales and Waste each *write a movement* the
// instant they're submitted — they're a transaction log of things that
// just happened. Counts is different in kind, not just in UI: it's a
// periodic physical check of what's actually on the shelf against what
// the ledger expects (core.count_line.expected_qty vs counted_qty) — a
// reconciliation, not a transaction. Grouping it under "Daily Operations"
// implied it moves stock the same way the other three do; it doesn't (see
// app/api/v1/counts.py — approving a count records a variance but doesn't
// yet write a COUNT_ADJUSTMENT movement). "Actuals" names what it actually
// is: capturing the true, physical, actual quantity. Stock Explorer/Items/
// Branches/Reference Data are read broadly (item.read, location.read) but
// edited narrowly (item.update, refdata.manage, ...), so they group as the
// shared "look things up, sometimes maintain them" catalog. Users & Roles
// is user.manage — SYS_ADMIN only, its own group of one.
// Named NavLinkItem, not NavLink, so it doesn't shadow the <NavLink>
// component imported above — same word, two different things (a plain
// data shape here vs. react-router's link component below).
interface NavLinkItem {
  to: string;
  label: string;
  icon: () => JSX.Element;
  permission?: string;
}

const NAV_GROUPS: { label: string; links: NavLinkItem[] }[] = [
  {
    label: "Daily Operations",
    links: [
      { to: "/receiving", label: "Receiving", icon: ReceivingIcon },
      { to: "/sales", label: "Sales", icon: SalesIcon },
      { to: "/waste", label: "Waste Log", icon: WasteIcon },
      { to: "/transfers", label: "Transfers", icon: TransfersIcon },
    ],
  },
  {
    // Counts and Stock Explorer are both "what is actually on the shelf" —
    // one captures it, the other reads it back.
    label: "Stocks",
    links: [
      { to: "/counts", label: "Counts", icon: CountsIcon },
      { to: "/stock", label: "Stock Explorer", icon: StockIcon },
    ],
  },
  {
    label: "Catalog",
    links: [
      { to: "/items", label: "Items", icon: ItemsIcon },
      { to: "/branches", label: "Branches", icon: BranchesIcon },
      { to: "/refdata", label: "Reference Data", icon: RefDataIcon },
    ],
  },
  {
    label: "Administration",
    links: [
      // SYS_ADMIN only (SPEC §7.3's seeded matrix) — hidden rather than
      // shown and 403'd, since a nav link to a screen you can't use is
      // exactly the kind of dead end SPEC §12.6 rule 6 argues against.
      { to: "/users", label: "Users & Roles", icon: UsersIcon, permission: "user.manage" },
    ],
  },
];

// Tailwind's `md` breakpoint (768px) — the same number drives both the
// CSS below and this JS default, so "which layout am I in" never disagrees
// between the two. Counts/Receiving/Waste are the screens store staff
// actually use on a phone (SPEC §12.7 calls Counts "mobile-first"
// explicitly), so the nav has to be usable at phone widths, not just
// shrink proportionally.
const MOBILE_BREAKPOINT_PX = 768;

function useIsMobile(): boolean {
  const [isMobile, setIsMobile] = useState(
    () => window.innerWidth < MOBILE_BREAKPOINT_PX,
  );
  useEffect(() => {
    const mql = window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT_PX - 1}px)`);
    const onChange = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, []);
  return isMobile;
}

export function AppShell() {
  const isMobile = useIsMobile();
  const location = useLocation();
  // The dashboard's own cards already cover every nav destination (SPEC:
  // it's a landing page, not just another screen), so the sidebar starts
  // closed there — one less thing between login and the thing you came
  // for. Still toggleable via the menu button, just not open by default.
  const isDashboard = location.pathname === "/dashboard";
  // Three different defaults, one piece of state: open on desktop
  // (sidebar visible by default), closed on mobile (the nav starts as a
  // hidden drawer, not a full-screen takeover on load), closed on the
  // dashboard regardless of viewport.
  const [navOpen, setNavOpen] = useState(!isMobile && !isDashboard);
  const { theme, toggleTheme } = useTheme();
  const { me, logout, hasPermission } = useAuth();
  // Drop a link the current role can't act on, then drop a group left
  // with nothing in it (Administration, for anyone but SYS_ADMIN) — an
  // empty section header would be its own dead end.
  const visibleNavGroups = NAV_GROUPS.map((group) => ({
    ...group,
    links: group.links.filter((link) => !link.permission || hasPermission(link.permission)),
  })).filter((group) => group.links.length > 0);

  // Crossing the breakpoint (rotating a tablet, resizing a window) or
  // navigating to/from the dashboard should reset to that context's
  // natural default rather than preserving whatever toggle state the
  // previous one happened to be in.
  useEffect(() => {
    setNavOpen(!isMobile && !isDashboard);
  }, [isMobile, isDashboard]);

  function closeNavOnMobile(): void {
    if (isMobile) setNavOpen(false);
  }

  return (
    <div className="flex h-screen flex-col bg-bg">
      {/* Header background/text are fixed (--header-bg/--header-fg) rather
          than theme-following surface/text tokens — brand chrome, not
          content, per explicit instruction. Everything below the header
          still follows light/dark normally. */}
      <header className="flex h-14 shrink-0 items-center justify-between bg-header-bg px-3 sm:px-4">
        <div className="flex items-center gap-2 sm:gap-3">
          <button
            type="button"
            onClick={() => setNavOpen((o) => !o)}
            aria-label={navOpen ? "Close navigation" : "Open navigation"}
            className="rounded-md p-1.5 text-header-fg/80 hover:bg-black/10 hover:text-header-fg"
          >
            <MenuIcon />
          </button>
          <div className="flex items-center gap-2">
            <span className="h-3 w-3 rounded-sm bg-header-fg" aria-hidden="true" />
            <span className="font-ui text-h2 text-header-fg">Cocopan IMS</span>
          </div>
        </div>

        <div className="flex items-center gap-2 sm:gap-3">
          <button
            type="button"
            onClick={toggleTheme}
            aria-label={`Switch to ${theme === "light" ? "dark" : "light"} theme`}
            className="rounded-md p-1.5 text-header-fg/80 hover:bg-black/10 hover:text-header-fg"
          >
            {theme === "light" ? <MoonIcon /> : <SunIcon />}
          </button>
          {me && (
            <div className="flex items-center gap-2 border-l border-header-fg/25 pl-2 sm:pl-3">
              {/* Name hides below sm (~384px) — the logout action is what
                  matters at phone width, not the label next to it. */}
              <span className="hidden font-ui text-small text-header-fg/90 sm:inline">
                {me.full_name}
              </span>
              <button
                type="button"
                onClick={() => void logout()}
                className="rounded-md px-2 py-1 font-ui text-small text-header-fg/90 hover:bg-black/10 hover:text-header-fg"
              >
                Log out
              </button>
            </div>
          )}
        </div>
      </header>

      <div className="relative flex flex-1 overflow-hidden">
        {/* Mobile only: a backdrop behind the drawer that closes it on tap
            — there is no persistent push-layout at phone width, only an
            overlay, since 220px of permanent sidebar doesn't leave enough
            room for a usable form on a phone screen. */}
        {isMobile && navOpen && (
          <div
            className="absolute inset-0 z-30 bg-black/40"
            onClick={() => setNavOpen(false)}
            role="presentation"
          />
        )}

        <nav
          className={`z-40 flex shrink-0 flex-col overflow-y-auto border-r border-border bg-surface transition-transform duration-theme ${
            isMobile
              ? `absolute inset-y-0 left-0 w-[260px] ${navOpen ? "translate-x-0" : "-translate-x-full"}`
              : `static w-[220px] ${navOpen ? "" : "hidden"}`
          }`}
        >
          <div className="flex flex-1 flex-col gap-4 p-2 py-3">
            <NavLink
              to="/dashboard"
              onClick={closeNavOnMobile}
              className={({ isActive }) =>
                `flex items-center gap-2.5 rounded-md border-l-2 px-3 py-2.5 font-ui text-body ${
                  isActive
                    ? "border-l-accent bg-surface-hover text-text"
                    : "border-l-transparent text-text-2 hover:bg-surface-hover hover:text-text"
                }`
              }
            >
              <DashboardIcon />
              Dashboard
            </NavLink>
            {visibleNavGroups.map((group) => (
              <div key={group.label}>
                <h2 className="px-3 pb-1 font-dense text-micro uppercase tracking-[0.06em] text-text-3">
                  {group.label}
                </h2>
                <ul className="flex flex-col gap-0.5">
                  {group.links.map((link) => (
                    <li key={link.to}>
                      <NavLink
                        to={link.to}
                        onClick={closeNavOnMobile}
                        className={({ isActive }) =>
                          // SPEC §12.1: the active nav indicator is one of
                          // the five places gold appears — a 2px left
                          // border, not a fill (same rule as row-selection,
                          // §12.1's fourth bullet).
                          `flex items-center gap-2.5 rounded-md border-l-2 px-3 py-2.5 font-ui text-body ${
                            isActive
                              ? "border-l-accent bg-surface-hover text-text"
                              : "border-l-transparent text-text-2 hover:bg-surface-hover hover:text-text"
                          }`
                        }
                      >
                        <link.icon />
                        {link.label}
                      </NavLink>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>

          {/* mt-auto, not absolute: the nav is a flex column, so this sits
              below the links on a short list and still gets pushed to the
              bottom of the viewport, without overlapping a long one. */}
          <div className="mt-auto border-t border-border px-3 py-2.5">
            <NavLink
              to="/guide"
              className="mb-1 block font-ui text-micro text-text-3 hover:text-text-2 hover:underline"
            >
              User Guide
            </NavLink>
            <p className="font-ui text-micro text-text-3">v{__APP_VERSION__}</p>
            <p className="font-ui text-micro text-text-3">
              © {new Date().getFullYear()} RGSuite
            </p>
          </div>
        </nav>

        <main className="flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

function MenuIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M2 5h14M2 9h14M2 13h14" strokeLinecap="round" />
    </svg>
  );
}

function SunIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5">
      <circle cx="9" cy="9" r="3.5" />
      <path
        d="M9 1.5v2M9 14.5v2M16.5 9h-2M3.5 9h-2M14.3 3.7l-1.4 1.4M5.1 12.9l-1.4 1.4M14.3 14.3l-1.4-1.4M5.1 5.1L3.7 3.7"
        strokeLinecap="round"
      />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M15.5 10.8A6.5 6.5 0 1 1 7.2 2.5a5 5 0 0 0 8.3 8.3Z" strokeLinejoin="round" />
    </svg>
  );
}

