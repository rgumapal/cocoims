# Cocopan IMS — User Guide

*A quick tour of what's here, what it's for, and what we'd love your feedback
on. This is a working pilot, not a finished product — some things below are
intentionally simple for now. (Also available inside the app itself — look
for "User Guide" at the bottom of the left-hand menu.)*

## Logging in

Sign in with the Google account that was set up for you — there's no
separate password to remember. If you don't have an account yet, ask
whoever invited you to create one under Users & Roles.

## Dashboard

The landing page after login. One card per screen below, each showing
today's headline numbers — how many branches have reported receiving,
total sales, items wasted, transfers in transit, open counts, and any
branch/item that's run out. Click any card to jump straight into that
screen. Use the date picker at the top right to see a past day instead of
today.

## Daily operations — the screens branch staff use every day

**Receiving** — Records what was delivered to a branch: how many units of
each item, and which production batch, for a given day. Pick a branch and
date, then enter quantities per item. If you need to correct an
already-saved day, click Edit — your change is recorded as a correction,
the original entry is never lost.

**Sales** — Records how many units of each item a branch actually sold that
day, and flags anything that sold out completely. Same pattern as
Receiving: pick a branch and date, enter quantities, mark sold-out items so
the system knows demand may have been higher than what's recorded.

**Waste Log** — Records stock that had to be thrown away — expired,
spoiled, or damaged — with a reason, so losses are explainable rather than
just a number. Pick a branch, item, and date. If something was already
reported for that exact combination, you'll see it right there before you
submit anything new — including who logged it and when. Made a mistake?
Use Reverse to correct it; the original entry stays on record, but its
effect on stock is undone.

**Transfers** *(new)* — Moves stock from one branch to another — for
example, rebalancing when one branch runs out and a nearby branch has
extra. Stock is tracked as genuinely "in transit" between the two steps, so
nothing is ever double-counted or lost in transit. Create a transfer
(source branch, destination branch, item, and quantity), then Ship it once
it physically leaves. The receiving branch then Receives it and counts
what actually arrived — if that's different from what was shipped, a
reason is required. Everything shows up in one list with its current
status (Draft, In Transit, Received, or Cancelled).

## Stock visibility

**Counts** — Physical inventory counts, comparing what's actually on the
shelf against what the system expects, to catch drift early. Open or
continue a count session for a branch, enter counted quantities per item.
A count with a large variance needs a second person's approval before it's
finalized.

**Stock Explorer** — A live view of exactly how much of each item is at a
branch right now, broken down into what came in vs. what went out, plus
how many days it's run out and any stock currently arriving via a
transfer. Pick a branch, then click any item for its full history — which
production batch is oldest, and every individual delivery/sale/waste/
transfer movement behind the current number.

## Catalog and administration

**Items** — The product catalog: every SKU, its shelf life, packaging, and
pricing. Browse or search by name/code. Add or edit items, alternate
names, and prices here; nothing on this screen affects stock directly.

**Branches** — Every branch, its status (open, temporarily closed,
planned, etc.), and who manages it. Status changes are logged with a full
history — nothing here is ever silently overwritten. A closed branch is
automatically excluded from ordering.

**Reference Data** — The shared lists everything else draws from:
categories, units of measure, clusters, areas, routes, and waste/transfer
reason codes. Add, edit, or deactivate entries here. Nothing is ever
hard-deleted if it's already been used somewhere, so history stays intact.

**Users & Roles** — Who can log in, what they're allowed to do, and which
branches they can see. Admin-only. Create a new user here to give someone
else access — it sends them a one-time setup link.

## What's not built yet

Not yet available: automatic demand forecasting, suggested order
quantities, accuracy/bias analytics dashboards, and file-based bulk
import from other systems. Those are planned for a later phase.

## What feedback is most useful right now

- Does entering a delivery, sale, or waste log match how it actually
  happens at a branch?
- Is anything confusing, mislabeled, or missing that you'd expect to see?
- Do the numbers on the Dashboard and Stock Explorer look right against
  what you know?
- Try the new Transfers feature end to end — create, ship, receive — and
  tell us if the flow makes sense for how branches actually coordinate a
  rebalance.

This is a shared environment still being actively built, so you may see
some test data mixed in alongside anything real you enter — don't worry
about it, just flag anything that looks genuinely wrong rather than just
unfamiliar.
