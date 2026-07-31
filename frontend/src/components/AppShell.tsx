import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "@/auth/AuthContext";
import { useTheme } from "@/design/ThemeContext";

// SPEC §12.5: single fixed 56px top bar, collapsible 220px left nav,
// content maximised — no nested panels. The spec's own mockup shows a
// two-level nav (top bar sections, sidebar sub-nav) for a screen count
// this build doesn't have yet (Orders/Exception Workbench is a later
// phase, deferred). A flat sidebar is simpler to build and explain for the
// seven screens that exist right now (YAGNI — CLAUDE.md ENGINEERING
// STANDARDS); reintroduce top-level grouping when there's enough breadth
// to need it.
const NAV_LINKS = [
  { to: "/items", label: "Items" },
  { to: "/branches", label: "Branches" },
  { to: "/refdata", label: "Reference Data" },
  { to: "/stock", label: "Stock Explorer" },
  { to: "/counts", label: "Counts" },
  { to: "/receiving", label: "Receiving" },
  { to: "/sales", label: "Sales" },
  { to: "/waste", label: "Waste Log" },
  // SYS_ADMIN only (SPEC §7.3's seeded matrix) — hidden rather than shown
  // and 403'd, since a nav link to a screen you can't use is exactly the
  // kind of dead end SPEC §12.6 rule 6 argues against.
  { to: "/users", label: "Users & Roles", permission: "user.manage" },
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
  const visibleNavLinks = NAV_LINKS.filter((link) => !link.permission || hasPermission(link.permission));

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
          <ul className="flex flex-col gap-0.5 p-2">
            {visibleNavLinks.map((link) => (
              <li key={link.to}>
                <NavLink
                  to={link.to}
                  onClick={closeNavOnMobile}
                  className={({ isActive }) =>
                    // SPEC §12.1: the active nav indicator is one of the
                    // five places gold appears — a 2px left border, not a
                    // fill (same rule as row-selection, §12.1's fourth
                    // bullet).
                    `block rounded-md border-l-2 px-3 py-2.5 font-ui text-body ${
                      isActive
                        ? "border-l-accent bg-surface-hover text-text"
                        : "border-l-transparent text-text-2 hover:bg-surface-hover hover:text-text"
                    }`
                  }
                >
                  {link.label}
                </NavLink>
              </li>
            ))}
          </ul>
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
