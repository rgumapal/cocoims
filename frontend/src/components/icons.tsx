// One icon per nav/dashboard screen — shared between AppShell's nav links
// and DashboardPage's cards so there's exactly one SVG per concept, not
// two copies that can drift (CLAUDE.md: "one obvious way to do each
// thing"). 18x18, currentColor stroke, so callers get the surrounding
// text colour for free with no separate colour prop.
export function DashboardIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2.5" y="2.5" width="6" height="6" rx="1" />
      <rect x="9.5" y="2.5" width="6" height="4" rx="1" />
      <rect x="9.5" y="8.5" width="6" height="7" rx="1" />
      <rect x="2.5" y="10.5" width="6" height="5" rx="1" />
    </svg>
  );
}

export function ReceivingIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2.5 9h3.3l1.4 2h3.6l1.4-2h3.3" />
      <path d="M2.5 9v5.5c0 .55.45 1 1 1h11c.55 0 1-.45 1-1V9" />
      <path d="M2.5 9 5 3.5h8L15.5 9" />
    </svg>
  );
}

export function SalesIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4.5 2h9v13.5l-2-1.3-1.8 1.3-1.7-1.3-1.8 1.3-1.7-1.3v-11Z" />
      <path d="M6.5 5.5h5M6.5 8.3h5M6.5 11h3" />
    </svg>
  );
}

export function WasteIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3.5 5h11" />
      <path d="M6 5V3.5c0-.55.45-1 1-1h4c.55 0 1 .45 1 1V5" />
      <path d="M4.6 5l.7 9.6c.04.5.46.9 1 .9h5.4c.54 0 .96-.4 1-.9L13.4 5" />
      <path d="M7.5 8v5M10.5 8v5" />
    </svg>
  );
}

export function CountsIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="4" y="3" width="10" height="12.5" rx="1.2" />
      <path d="M6.8 3V2.3c0-.44.36-.8.8-.8h2.8c.44 0 .8.36.8.8V3" />
      <path d="M6.3 9.2l1.6 1.6 3.2-3.6" />
    </svg>
  );
}

export function StockIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2.3 8 9 3l6.7 5" />
      <path d="M3.3 7.3v7.2c0 .5.45 1 1 1h9.4c.55 0 1-.5 1-1V7.3" />
      <path d="M7 15.5V10h4v5.5" />
    </svg>
  );
}

export function ItemsIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2.5 5.5 9 2.5l6.5 3-6.5 3-6.5-3Z" />
      <path d="M2.5 5.5v6.7L9 15.5l6.5-3.3V5.5" />
      <path d="M9 8.6v6.9" />
    </svg>
  );
}

export function BranchesIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 16s5-4.9 5-8.8A5 5 0 0 0 4 7.2C4 11.1 9 16 9 16Z" />
      <circle cx="9" cy="7.1" r="2" />
    </svg>
  );
}

export function RefDataIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2.5" y="3.5" width="13" height="11" rx="1" />
      <path d="M2.5 7.5h13" />
      <path d="M7 7.5v7" />
    </svg>
  );
}

export function UsersIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="6.7" cy="6.2" r="2.2" />
      <path d="M2.5 15c0-2.7 1.9-4.5 4.2-4.5s4.2 1.8 4.2 4.5" />
      <circle cx="12.7" cy="6.7" r="1.7" />
      <path d="M11.6 10.8c1.9.2 3.3 1.8 3.3 4.2" />
    </svg>
  );
}
