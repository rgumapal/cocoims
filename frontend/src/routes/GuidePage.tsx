import type { ReactNode } from "react";
import { PageHeader } from "@/components/ui/PageHeader";

// A plain-language walkthrough for a non-technical stakeholder exploring
// the app for the first time — deliberately NOT written in this repo's
// usual engineering vocabulary (no "ledger", "RLS", "movement type").
// Kept as hand-written JSX rather than a rendered Markdown file: adding a
// Markdown-parsing dependency for one static page would be the kind of
// "second way to do the same thing" CLAUDE.md's engineering standards
// argue against, when plain sections work fine. See docs/CLIENT_GUIDE.md
// for the same content as a shareable file (e.g. to email or paste
// elsewhere) — keep the two in sync by hand if either changes.

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mb-8">
      <h2 className="mb-2 font-ui text-h2 text-text">{title}</h2>
      <div className="flex flex-col gap-2 font-ui text-body text-text-2">{children}</div>
    </section>
  );
}

function Feature({
  name,
  purpose,
  howTo,
}: {
  name: string;
  purpose: string;
  howTo: string;
}) {
  return (
    <div className="rounded-md border border-border bg-surface p-3">
      <h3 className="font-ui text-body font-semibold text-text">{name}</h3>
      <p className="mt-1 font-ui text-small text-text-2">{purpose}</p>
      <p className="mt-1 font-ui text-small text-text-3">{howTo}</p>
    </div>
  );
}

export default function GuidePage() {
  return (
    <div className="mx-auto max-w-3xl p-4">
      <PageHeader
        title="Cocopan IMS — User Guide"
        description="A quick tour of what's here, what it's for, and what we'd love your feedback on. This is a working pilot, not a finished product — some things below are intentionally simple for now."
      />

      <div className="p-4">
        <Section title="What this is">
          <p>
            Cocopan IMS replaces the current Excel workbook for tracking deliveries, sales, waste,
            and stock movement across branches. Right now it covers the day-to-day record-keeping
            side: logging what happened at each branch, keeping one reliable history of stock, and
            giving admin staff a way to manage branches, items, and user access without a
            spreadsheet.
          </p>
          <p>
            It does <strong>not</strong> yet do automatic order suggestions, demand forecasting, or
            performance analytics — that's the next phase, and it depends on this data-capture
            layer being solid first. See "What's not built yet" below.
          </p>
        </Section>

        <Section title="Logging in">
          <p>
            Sign in with the Google account that was set up for you — there's no separate password
            to remember. If you don't have an account yet, ask whoever invited you to create one
            under Users &amp; Roles.
          </p>
        </Section>

        <Section title="Dashboard">
          <p>
            The landing page after login. One card per screen below, each showing today's headline
            numbers — how many branches have reported receiving, total sales, items wasted, transfers
            in transit, open counts, and any branch/item that's run out. Click any card to jump
            straight into that screen. Use the date picker at the top right to see a past day
            instead of today.
          </p>
        </Section>

        <Section title="Daily operations — the screens branch staff use every day">
          <Feature
            name="Receiving"
            purpose="Records what was delivered to a branch — how many units of each item, and which
              production batch, for a given day."
            howTo="Pick a branch and date, then enter quantities per item. If you need to correct an
              already-saved day, click Edit — your change is recorded as a correction, the original
              entry is never lost."
          />
          <Feature
            name="Sales"
            purpose="Records how many units of each item a branch actually sold that day, and flags
              anything that sold out completely."
            howTo="Same pattern as Receiving: pick a branch and date, enter quantities, mark
              sold-out items so the system knows demand may have been higher than what's recorded."
          />
          <Feature
            name="Waste Log"
            purpose="Records stock that had to be thrown away — expired, spoiled, or damaged — with a
              reason, so losses are explainable rather than just a number."
            howTo="Pick a branch, item, and date. If something was already reported for that exact
              combination, you'll see it right there before you submit anything new — including who
              logged it and when. Made a mistake? Use Reverse to correct it; the original entry stays
              on record, but its effect on stock is undone."
          />
          <Feature
            name="Transfers"
            purpose="New: moves stock from one branch to another — for example, rebalancing when one
              branch runs out and a nearby branch has extra. Stock is tracked as genuinely 'in
              transit' between the two steps, so nothing is ever double-counted or lost in transit."
            howTo="Create a transfer (source branch, destination branch, item, and quantity), then
              Ship it once it physically leaves. The receiving branch then Receives it and counts
              what actually arrived — if that's different from what was shipped, a reason is
              required. Everything shows up in one list with its current status (Draft, In Transit,
              Received, or Cancelled)."
          />
        </Section>

        <Section title="Stock visibility">
          <Feature
            name="Counts"
            purpose="Physical inventory counts — comparing what's actually on the shelf against what
              the system expects, to catch drift early."
            howTo="Open or continue a count session for a branch, enter counted quantities per item.
              A count with a large variance needs a second person's approval before it's finalized."
          />
          <Feature
            name="Stock Explorer"
            purpose="A live view of exactly how much of each item is at a branch right now, broken
              down into what came in vs. what went out, plus how many days it's run out and any
              stock currently arriving via a transfer."
            howTo="Pick a branch, then click any item for its full history — which production batch
              is oldest, and every individual delivery/sale/waste/transfer movement behind the
              current number."
          />
        </Section>

        <Section title="Catalog and administration">
          <Feature
            name="Items"
            purpose="The product catalog — every SKU, its shelf life, packaging, and pricing."
            howTo="Browse or search by name/code. Add or edit items, alternate names, and prices
              here; nothing on this screen affects stock directly."
          />
          <Feature
            name="Branches"
            purpose="Every branch, its status (open, temporarily closed, planned, etc.), and who
              manages it."
            howTo="Status changes are logged with a full history — nothing here is ever silently
              overwritten. A closed branch is automatically excluded from ordering."
          />
          <Feature
            name="Reference Data"
            purpose="The shared lists everything else draws from — categories, units of measure,
              clusters, areas, routes, and waste/transfer reason codes."
            howTo="Add, edit, or deactivate entries here. Nothing is ever hard-deleted if it's
              already been used somewhere, so history stays intact."
          />
          <Feature
            name="Users & Roles"
            purpose="Who can log in, what they're allowed to do, and which branches they can see."
            howTo="Admin-only. Create a new user here to give someone else access — it sends them a
              one-time setup link."
          />
        </Section>

        <Section title="What's not built yet">
          <p>
            This is a data-capture foundation, not the full system described in the original spec.
            Not built yet: automatic demand forecasting, suggested order quantities, the
            accuracy/bias analytics dashboards, and file-based bulk import from other systems. Those
            come next, once the numbers this phase produces are trusted.
          </p>
        </Section>

        <Section title="What feedback is most useful right now">
          <ul className="list-disc pl-5">
            <li>Does entering a delivery, sale, or waste log match how it actually happens at a branch?</li>
            <li>Is anything confusing, mislabeled, or missing that you'd expect to see?</li>
            <li>Do the numbers on the Dashboard and Stock Explorer look right against what you know?</li>
            <li>Try the new Transfers feature end to end — create, ship, receive — and tell us if the
              flow makes sense for how branches actually coordinate a rebalance.</li>
          </ul>
          <p>
            This is a shared environment still being actively built, so you may see some test data
            mixed in alongside anything real you enter — don't worry about it, just flag anything
            that looks genuinely wrong rather than just unfamiliar.
          </p>
        </Section>
      </div>
    </div>
  );
}
