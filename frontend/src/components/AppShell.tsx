import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "@/auth/AuthContext";
import { useTheme } from "@/design/ThemeContext";

// SPEC §12.5: single fixed 56px top bar, collapsible 220px left nav,
// content maximised — no nested panels.
//
// Three groups, chosen from the actual seeded permission matrix
// (core.role_permission) rather than guessed: Receiving/Sales/Waste/Counts
// are the only four screens STORE_TEAM (the narrowest role) can act on —
// the daily, store-level capture work. Stock Explorer/Items/Branches/
// Reference Data are read broadly (item.read, location.read) but edited
// narrowly (item.update, refdata.manage, ...), so they group as the shared
// "look things up, sometimes maintain them" catalog. Users & Roles is
// user.manage — SYS_ADMIN only, its own group of one.
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
      { to: "/counts", label: "Counts", icon: CountsIcon },
    ],
  },
  {
    label: "Catalog & Stock",
    links: [
      { to: "/stock", label: "Stock Explorer", icon: StockIcon },
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
  // Two different defaults, one piece of state: open on desktop (sidebar
  // visible by default), closed on mobile (the nav starts as a hidden
  // drawer, not a full-screen takeover on load).
  const [navOpen, setNavOpen] = useState(!isMobile);
  const { theme, toggleTheme } = useTheme();
  const { me, logout, hasPermission } = useAuth();
  // Drop a link the current role can't act on, then drop a group left
  // with nothing in it (Administration, for anyone but SYS_ADMIN) — an
  // empty section header would be its own dead end.
  const visibleNavGroups = NAV_GROUPS.map((group) => ({
    ...group,
    links: group.links.filter((link) => !link.permission || hasPermission(link.permission)),
  })).filter((group) => group.links.length > 0);

  // Crossing the breakpoint (rotating a tablet, resizing a window) should
  // reset to that layout's natural default rather than preserving
  // whatever the other layout's toggle state happened to be.
  useEffect(() => {
    setNavOpen(!isMobile);
  }, [isMobile]);

  function closeNavOnMobile(): void {
    if (isMobile) setNavOpen(false);
  }

  return (
    <div className="flex h-screen flex-col bg-bg">
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-surface px-3 sm:px-4">
        <div className="flex items-center gap-2 sm:gap-3">
          <button
            type="button"
            onClick={() => setNavOpen((o) => !o)}
            aria-label={navOpen ? "Close navigation" : "Open navigation"}
            className="rounded-md p-1.5 text-text-2 hover:bg-surface-hover"
          >
            <MenuIcon />
          </button>
          <div className="flex items-center gap-2">
            {/* The brand mark — one of the five places gold is allowed
                (SPEC §12.1). Nowhere else in this shell uses it. */}
            <span className="h-3 w-3 rounded-sm bg-accent" aria-hidden="true" />
            <span className="font-ui text-h2 text-text">Cocopan IMS</span>
          </div>
        </div>

        <div className="flex items-center gap-2 sm:gap-3">
          <button
            type="button"
            onClick={toggleTheme}
            aria-label={`Switch to ${theme === "light" ? "dark" : "light"} theme`}
            className="rounded-md p-1.5 text-text-2 hover:bg-surface-hover"
          >
            {theme === "light" ? <MoonIcon /> : <SunIcon />}
          </button>
          {me && (
            <div className="flex items-center gap-2 border-l border-border pl-2 sm:pl-3">
              {/* Name hides below sm (~384px) — the logout action is what
                  matters at phone width, not the label next to it. */}
              <span className="hidden font-ui text-small text-text-2 sm:inline">
                {me.full_name}
              </span>
              <button
                type="button"
                onClick={() => void logout()}
                className="rounded-md px-2 py-1 font-ui text-small text-text-2 hover:bg-surface-hover hover:text-text"
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
          className={`z-40 shrink-0 overflow-y-auto border-r border-border bg-surface transition-transform duration-theme ${
            isMobile
              ? `absolute inset-y-0 left-0 w-[260px] ${navOpen ? "translate-x-0" : "-translate-x-full"}`
              : `static w-[220px] ${navOpen ? "" : "hidden"}`
          }`}
        >
          <div className="flex flex-col gap-4 p-2 py-3">
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

// Nav icons — one per NAV_GROUPS link, same minimalist stroke style as the
// icons above (18x18, currentColor) so they pick up the NavLink's own
// active/inactive text colour for free, with no separate colour prop.
function ReceivingIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2.5 9h3.3l1.4 2h3.6l1.4-2h3.3" />
      <path d="M2.5 9v5.5c0 .55.45 1 1 1h11c.55 0 1-.45 1-1V9" />
      <path d="M2.5 9 5 3.5h8L15.5 9" />
    </svg>
  );
}

function SalesIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4.5 2h9v13.5l-2-1.3-1.8 1.3-1.7-1.3-1.8 1.3-1.7-1.3v-11Z" />
      <path d="M6.5 5.5h5M6.5 8.3h5M6.5 11h3" />
    </svg>
  );
}

function WasteIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3.5 5h11" />
      <path d="M6 5V3.5c0-.55.45-1 1-1h4c.55 0 1 .45 1 1V5" />
      <path d="M4.6 5l.7 9.6c.04.5.46.9 1 .9h5.4c.54 0 .96-.4 1-.9L13.4 5" />
      <path d="M7.5 8v5M10.5 8v5" />
    </svg>
  );
}

function CountsIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="4" y="3" width="10" height="12.5" rx="1.2" />
      <path d="M6.8 3V2.3c0-.44.36-.8.8-.8h2.8c.44 0 .8.36.8.8V3" />
      <path d="M6.3 9.2l1.6 1.6 3.2-3.6" />
    </svg>
  );
}

function StockIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2.3 8 9 3l6.7 5" />
      <path d="M3.3 7.3v7.2c0 .5.45 1 1 1h9.4c.55 0 1-.5 1-1V7.3" />
      <path d="M7 15.5V10h4v5.5" />
    </svg>
  );
}

function ItemsIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2.5 5.5 9 2.5l6.5 3-6.5 3-6.5-3Z" />
      <path d="M2.5 5.5v6.7L9 15.5l6.5-3.3V5.5" />
      <path d="M9 8.6v6.9" />
    </svg>
  );
}

function BranchesIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 16s5-4.9 5-8.8A5 5 0 0 0 4 7.2C4 11.1 9 16 9 16Z" />
      <circle cx="9" cy="7.1" r="2" />
    </svg>
  );
}

function RefDataIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2.5" y="3.5" width="13" height="11" rx="1" />
      <path d="M2.5 7.5h13" />
      <path d="M7 7.5v7" />
    </svg>
  );
}

function UsersIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="6.7" cy="6.2" r="2.2" />
      <path d="M2.5 15c0-2.7 1.9-4.5 4.2-4.5s4.2 1.8 4.2 4.5" />
      <circle cx="12.7" cy="6.7" r="1.7" />
      <path d="M11.6 10.8c1.9.2 3.3 1.8 3.3 4.2" />
    </svg>
  );
}
