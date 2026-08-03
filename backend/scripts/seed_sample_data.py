"""Generates a day of realistic sample Receiving -> Sales -> Transfers ->
Waste activity.

DEV/PROTOTYPE TOOL. Every row this writes lands in core.stock_movement,
which is append-only (CLAUDE.md DATA) — there is no DELETE. `--undo` can
only write *offsetting* movements to net the balances back to zero; the
original rows, and the corrections, stay in the ledger permanently. Treat
every `--execute` run as irreversible and think before running it against
a database anyone is demoing from.

Why this posts to the API instead of INSERTing directly:

- core.stock_movement has FORCE ROW LEVEL SECURITY, so even the owning role
  sees and writes nothing without app.location_scope/app.unrestricted set on
  the transaction. app.auth.deps.get_db does that for every API request.
- app.domain.ledger.write_movement enforces SPEC §4.4's signed convention
  (RECEIPT positive, SALE/WASTE negative). A hand-written INSERT can quietly
  store a backwards sign, which silently corrupts every balance and FEFO
  query downstream.
- Receiving and Sales are diff-based (see app.api.v1.receiving/sales): a POST
  reconciles against the net state already on file. Inserting rows directly
  desyncs what those screens compute from what the ledger holds.
- Transfers run a real state machine (DRAFT -> IN_TRANSIT -> RECEIVED) with
  FEFO lot allocation decided server-side (app.domain.transfer) — there is no
  shortcut that produces the same in-transit ledger leg and lot identity a
  hand-written insert would have to reimplement badly.

Going through HTTP is slower (~3 min for a full network day, mostly Cloud SQL
round trips) but it is the only path that produces data identical to what a
person clicking through the app would produce.

Usage, from backend/ with the venv active and the API running:

    python -m scripts.seed_sample_data --date 2026-08-05              # dry run
    python -m scripts.seed_sample_data --date 2026-08-05 --only-branch AGL --execute
    python -m scripts.seed_sample_data --date 2026-08-05 --execute
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import httpx
from sqlalchemy import create_engine, text

from app.auth.security import create_token
from app.core.config import settings

# ---------------------------------------------------------------------
# Generation parameters — every "x% to y%" band from the brief this
# implements, in one place so the shape of the generated day can be tuned
# without reading the generator itself.
# ---------------------------------------------------------------------

RECEIVING_BRANCH_SHARE = (0.80, 1.00)
RECEIVING_ITEM_SHARE = (0.80, 1.00)
# Real client volumes (workbook "Ave Deliveries"): ~15 units/item/day on
# average, 0-71 observed. 5 is the floor because a delivery of 1-4 units of
# a bread SKU isn't a real delivery.
RECEIVE_QTY = (5, 70)
PRODUCTION_BACKDATE_MAX_DAYS = 5

SALES_BRANCH_SHARE = (0.95, 1.00)
# Branches that sell without any recorded delivery — deliberate: it drives
# balances negative, which is a real signal (recorded sales exceeding
# recorded deliveries) that app.domain.ledger.excess_summary explicitly does
# not floor at zero.
SALES_UNRECEIVED_BRANCHES = (1, 2)
SALES_ITEM_SHARE = (0.95, 1.00)
SALES_EXTRA_ITEM_PROBABILITY = 0.10
SALES_EXTRA_ITEMS = (1, 2)
RAN_OUT_SHARE = (0.40, 0.60)
# How far short of the delivered quantity a not-sold-out item lands.
SALES_SHORTFALL = (1, 10)
UNRECEIVED_SOLD_QTY = (5, 60)

# Branch-level, not item-level, randomness: a real branch either closes
# out its waste log for the day or it doesn't — staff that skip the task
# skip all of it, they don't selectively log some items and not others.
WASTE_BRANCH_SHARE = (0.70, 1.00)

# Leftover stock (delivered > sold) does not automatically mean wasted —
# that was this generator's original assumption, and it produced an
# unrealistically high daily count (every item with even 1 unit of
# surplus became a full waste entry). A shelf_life_days=0 item genuinely
# has no other option — unsold at close means thrown out, so it stays
# close to "always." A MULTI_DAY item's surplus mostly just carries to a
# future day instead; only a minority becomes an actual waste entry today.
# This generator only ever produces one day at a time (no cross-day
# ledger state to carry that surplus *into*), so "the rest carries over"
# isn't modelled explicitly — it's simply left unlogged, which is the
# correct net effect for a single day's snapshot.
SAME_DAY_WASTE_ITEM_SHARE = (0.70, 1.00)
MULTI_DAY_WASTE_ITEM_SHARE = (0.15, 0.35)

# Only reason codes whose requires_note is FALSE. The waste endpoint
# (app.api.v1.waste.WasteRequest) has no note field at all, so a code that
# requires one would silently produce a row violating its own contract.
# Weighted toward end-of-day unsold stock, which is what a bakery actually
# throws away.
WASTE_REASONS = (
    ("UNSOLD", 50),
    ("EXPIRED", 25),
    ("STAFF_MEAL", 10),
    ("SAMPLING", 6),
    ("DAMAGED_IN_TRANSIT", 5),
    ("DONATION", 4),
)

# No real client volume exists for this yet (docs/features/TRANSFERS_V1.md
# is a new-build prototype, not something the workbook ever recorded) — 0-10
# is the user's own stated band, not derived from anything.
TRANSFER_COUNT = (0, 10)
# A transfer this small isn't worth a rider's trip; this floor matches the
# reasoning behind RECEIVE_QTY's own floor above.
TRANSFER_QTY = (3, 15)
# Never draw a source branch down to nothing — some genuine surplus has to
# remain, or the "rebalance a surplus" story the reason code tells is false.
TRANSFER_MIN_SURPLUS = 2
# Distribution across the state machine for a single day's snapshot: most
# same-day rebalances (short distances, urgent) complete same-day; the rest
# are caught mid-flight or not yet actioned, which is what a live dashboard
# should actually look like, not "everything always finishes."
TRANSFER_STATUS_WEIGHTS = (
    ("RECEIVED", 60),
    ("IN_TRANSIT", 20),
    ("DRAFT", 15),
    ("CANCELLED", 5),
)
# Only a RECEIVED transfer can carry a variance — DRAFT/IN_TRANSIT/CANCELLED
# never reach the receive step at all.
TRANSFER_VARIANCE_PROBABILITY = 0.15
TRANSFER_VARIANCE_QTY = (1, 5)
TRANSFER_REASON_SOLD_OUT = "REBALANCE_SOLD_OUT"
TRANSFER_REASON_SURPLUS = "REBALANCE_SURPLUS"
TRANSFER_VARIANCE_REASONS = (
    ("SHORT_RECEIPT", 70),
    ("DAMAGED_IN_TRANSIT", 30),
)

REQUIRED_PERMISSIONS = (
    "receiving.confirm",
    "sales.record",
    "waste.record",
    "transfer.create",
    "transfer.ship",
    "transfer.receive",
)

MANIFEST_DIR = Path(__file__).resolve().parent.parent / ".seed-runs"


@dataclass(frozen=True)
class ItemRef:
    item_code: str
    shelf_life_days: int


@dataclass
class ReceivingLine:
    item_code: str
    qty: Decimal
    production_date: dt.date


@dataclass
class BranchReceiving:
    location_code: str
    ref_doc_id: str
    lines: list[ReceivingLine]


@dataclass
class SalesLine:
    item_code: str
    qty: Decimal
    sold_out: bool


@dataclass
class BranchSales:
    location_code: str
    lines: list[SalesLine]


@dataclass
class WasteEntry:
    location_code: str
    item_code: str
    qty: Decimal
    reason_code: str
    production_date: dt.date | None


@dataclass
class TransferSeed:
    """One transfer, carried as far through DRAFT -> IN_TRANSIT -> RECEIVED
    as target_status calls for. Single-item by construction — a seed
    generator doesn't need multi-line transfers to exercise the feature
    realistically, and it keeps this dataclass (and execute()'s posting
    logic) simple rather than modelling something no other part of this
    script's output actually needs."""

    source_location_code: str
    dest_location_code: str
    item_code: str
    qty_requested: Decimal
    reason_code: str
    target_status: str  # DRAFT | IN_TRANSIT | RECEIVED | CANCELLED
    qty_shipped: Decimal | None = None
    qty_received: Decimal | None = None
    variance_reason_code: str | None = None


@dataclass
class SeedPlan:
    business_date: dt.date
    run_id: str
    receiving: list[BranchReceiving] = field(default_factory=list)
    sales: list[BranchSales] = field(default_factory=list)
    transfers: list[TransferSeed] = field(default_factory=list)
    waste: list[WasteEntry] = field(default_factory=list)


def _share(rng: random.Random, population: list, share: tuple[float, float]) -> list:
    """A random sample sized to a random share of the population, never empty
    when the population isn't."""
    if not population:
        return []
    fraction = rng.uniform(*share)
    count = max(1, round(len(population) * fraction))
    return rng.sample(population, min(count, len(population)))


def _pick_transfer_execution(
    rng: random.Random, qty_requested: Decimal
) -> tuple[str, Decimal | None, Decimal | None, str | None]:
    """How far a generated transfer gets carried, and with what variance if
    it's received — the one place this decision is made, since both transfer
    sources in build_plan (ran-out-driven and surplus-fallback) need it
    identically."""
    target_status = rng.choices(
        [status for status, _ in TRANSFER_STATUS_WEIGHTS],
        weights=[weight for _, weight in TRANSFER_STATUS_WEIGHTS],
        k=1,
    )[0]
    qty_shipped = qty_requested if target_status != "DRAFT" else None
    qty_received: Decimal | None = None
    variance_reason_code: str | None = None
    if target_status == "RECEIVED":
        assert qty_shipped is not None
        qty_received = qty_shipped
        if rng.random() < TRANSFER_VARIANCE_PROBABILITY:
            variance = Decimal(rng.randint(*TRANSFER_VARIANCE_QTY))
            qty_received = max(Decimal(0), qty_shipped - variance)
            variance_reason_code = rng.choices(
                [code for code, _ in TRANSFER_VARIANCE_REASONS],
                weights=[weight for _, weight in TRANSFER_VARIANCE_REASONS],
                k=1,
            )[0]
    return target_status, qty_shipped, qty_received, variance_reason_code


def load_reference_data(engine) -> tuple[list[str], list[ItemRef]]:
    """Branches and items the generator is allowed to touch.

    Read-only, and the one place this script talks to the database directly
    — everything that *writes* goes through the API. The COMMISSARY is
    excluded on purpose: it bakes and dispatches, it doesn't receive
    deliveries or sell to customers.
    """
    with engine.connect() as conn:
        branches = [
            row[0]
            for row in conn.execute(
                text(
                    "SELECT location_code FROM core.location "
                    "WHERE is_active AND is_orderable AND location_type = 'BRANCH' "
                    "ORDER BY location_code"
                )
            )
        ]
        items = [
            ItemRef(item_code=row[0], shelf_life_days=row[1])
            for row in conn.execute(
                text(
                    "SELECT item_code, shelf_life_days FROM core.item "
                    "WHERE is_orderable AND lifecycle_status = 'ACTIVE' "
                    "ORDER BY item_code"
                )
            )
        ]
    return branches, items


def count_existing_movements(engine, business_date: dt.date) -> int:
    """Movements already on file for the target date.

    Needs app.unrestricted because core.stock_movement's RLS applies even to
    the owning role (FORCE ROW LEVEL SECURITY) — without it this silently
    returns 0 for a date that is in fact already populated, which is exactly
    the wrong answer for a safety check.
    """
    with engine.connect() as conn:
        conn.execute(text("SET app.unrestricted = 'on'"))
        return conn.execute(
            text("SELECT count(*) FROM core.stock_movement WHERE business_date = :d"),
            {"d": business_date},
        ).scalar_one()


def resolve_seed_user(engine) -> tuple[int, str]:
    """Picks an active human account holding every permission this script
    needs, rather than hardcoding a user_id that may not exist in another
    environment. Service accounts are excluded — they authenticate by API
    key, not by the interactive tokens minted here."""
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT u.user_id, u.email
                FROM core.app_user u
                WHERE u.is_active AND NOT u.is_service
                  AND NOT EXISTS (
                      SELECT 1 FROM unnest(CAST(:required AS text[])) AS req(code)
                      WHERE NOT EXISTS (
                          SELECT 1
                          FROM core.user_role ur
                          JOIN core.role_permission rp ON rp.role_code = ur.role_code
                          WHERE ur.user_id = u.user_id AND rp.permission_code = req.code
                      )
                  )
                ORDER BY u.user_id
                LIMIT 1
                """
            ),
            {"required": list(REQUIRED_PERMISSIONS)},
        ).one_or_none()
    if row is None:
        raise SystemExit(
            "No active non-service user holds all of "
            f"{', '.join(REQUIRED_PERMISSIONS)} — cannot mint a token to seed with."
        )
    return int(row[0]), str(row[1])


def build_plan(
    rng: random.Random,
    business_date: dt.date,
    run_id: str,
    branches: list[str],
    items: list[ItemRef],
) -> SeedPlan:
    """Builds the whole cascade in memory before anything is written.

    Sales derive from the generated receiving and waste derives from both, so
    the three phases stay internally consistent without re-reading the ledger
    between them.
    """
    plan = SeedPlan(business_date=business_date, run_id=run_id)
    item_by_code = {item.item_code: item for item in items}

    # --- Receiving -------------------------------------------------------
    receiving_branches = _share(rng, branches, RECEIVING_BRANCH_SHARE)
    received: dict[str, dict[str, ReceivingLine]] = {}

    for seq, branch in enumerate(sorted(receiving_branches), start=1):
        lines: list[ReceivingLine] = []
        for item in _share(rng, items, RECEIVING_ITEM_SHARE):
            # Backdating is capped by the item's own shelf life: a same-day
            # bread produced 5 days ago would arrive already expired, which
            # is noise rather than realism.
            max_backdate = min(PRODUCTION_BACKDATE_MAX_DAYS, item.shelf_life_days)
            production_date = business_date - dt.timedelta(days=rng.randint(0, max_backdate))
            lines.append(
                ReceivingLine(
                    item_code=item.item_code,
                    qty=Decimal(rng.randint(*RECEIVE_QTY)),
                    production_date=production_date,
                )
            )
        if not lines:
            continue
        lines.sort(key=lambda line: line.item_code)
        plan.receiving.append(
            BranchReceiving(
                location_code=branch,
                ref_doc_id=f"DR-{business_date:%Y%m%d}-{seq:04d}",
                lines=lines,
            )
        )
        received[branch] = {line.item_code: line for line in lines}

    # --- Sales -----------------------------------------------------------
    selling_branches = _share(rng, sorted(received.keys()), SALES_BRANCH_SHARE)

    # Branches with sales but no delivery on this date.
    branches_without_receiving = [b for b in branches if b not in received]
    unreceived_branches = rng.sample(
        branches_without_receiving,
        min(rng.randint(*SALES_UNRECEIVED_BRANCHES), len(branches_without_receiving)),
    )

    sold: dict[str, dict[str, SalesLine]] = {}
    # (branch, item_code) pairs that ran out today — the transfer phase
    # below picks its destinations from here, since "this branch sold out
    # of this item" is exactly the real-world trigger for a rebalance.
    ran_out_lines: list[tuple[str, str]] = []

    for branch in sorted(selling_branches):
        branch_received = received[branch]
        sellable = _share(rng, sorted(branch_received.keys()), SALES_ITEM_SHARE)

        # Occasionally a branch sells something it wasn't delivered today —
        # carryover stock, or (see the Transfers phase below) something a
        # branch-to-branch rebalance brought in.
        unstocked = [c for c in item_by_code if c not in branch_received]
        extra: list[str] = []
        if unstocked and rng.random() < SALES_EXTRA_ITEM_PROBABILITY:
            extra = rng.sample(
                unstocked, min(rng.randint(*SALES_EXTRA_ITEMS), len(unstocked))
            )

        ran_out = set(_share(rng, sorted(sellable), RAN_OUT_SHARE))
        ran_out_lines.extend((branch, item_code) for item_code in sorted(ran_out))

        sale_lines: list[SalesLine] = []
        for item_code in sorted(sellable):
            delivered = branch_received[item_code].qty
            if item_code in ran_out:
                # Ran out means the branch sold through everything it had.
                qty = delivered
            else:
                shortfall = Decimal(rng.randint(*SALES_SHORTFALL))
                # Never negative: a small delivery with a large shortfall
                # simply means nothing sold, not a negative sale.
                qty = max(Decimal(0), delivered - shortfall)
            sale_lines.append(
                SalesLine(item_code=item_code, qty=qty, sold_out=item_code in ran_out)
            )

        for item_code in sorted(extra):
            sale_lines.append(
                SalesLine(
                    item_code=item_code,
                    qty=Decimal(rng.randint(*UNRECEIVED_SOLD_QTY)),
                    sold_out=False,
                )
            )

        sale_lines = [line for line in sale_lines if line.qty > 0]
        if not sale_lines:
            continue
        plan.sales.append(BranchSales(location_code=branch, lines=sale_lines))
        sold[branch] = {line.item_code: line for line in sale_lines}

    for branch in sorted(unreceived_branches):
        chosen = rng.sample(
            sorted(item_by_code), min(rng.randint(*SALES_EXTRA_ITEMS), len(item_by_code))
        )
        unreceived_sale_lines = [
            SalesLine(
                item_code=item_code,
                qty=Decimal(rng.randint(*UNRECEIVED_SOLD_QTY)),
                sold_out=False,
            )
            for item_code in sorted(chosen)
        ]
        plan.sales.append(BranchSales(location_code=branch, lines=unreceived_sale_lines))
        sold[branch] = {line.item_code: line for line in unreceived_sale_lines}

    # --- Transfers ---------------------------------------------------------
    # Driven by ran_out_lines: a transfer's whole reason to exist is moving
    # surplus to a branch that just ran out. Source candidates are any other
    # branch that received this same item today and has more than
    # TRANSFER_MIN_SURPLUS left after its own sales — a real "who still has
    # stock" query, not a random pick. Shuffled so which ran-out lines get
    # picked (there are usually more of them than TRANSFER_COUNT wants) isn't
    # biased toward whichever branch/item sorts first.
    target_transfer_count = rng.randint(*TRANSFER_COUNT)
    shuffled_ran_out = list(ran_out_lines)
    rng.shuffle(shuffled_ran_out)

    for dest_branch, item_code in shuffled_ran_out:
        if len(plan.transfers) >= target_transfer_count:
            break
        source_candidates = [
            (branch, lines[item_code].qty - sold.get(branch, {}).get(
                item_code, SalesLine(item_code, Decimal(0), False)
            ).qty)
            for branch, lines in received.items()
            if branch != dest_branch and item_code in lines
        ]
        source_candidates = [
            (branch, surplus) for branch, surplus in source_candidates
            if surplus > TRANSFER_MIN_SURPLUS
        ]
        if not source_candidates:
            continue
        source_branch, surplus = rng.choice(source_candidates)

        qty_requested = min(surplus - 1, Decimal(rng.randint(*TRANSFER_QTY)))
        if qty_requested <= 0:
            continue

        target_status, qty_shipped, qty_received, variance_reason_code = (
            _pick_transfer_execution(rng, qty_requested)
        )

        plan.transfers.append(
            TransferSeed(
                source_location_code=source_branch,
                dest_location_code=dest_branch,
                item_code=item_code,
                qty_requested=qty_requested,
                reason_code=TRANSFER_REASON_SOLD_OUT,
                target_status=target_status,
                qty_shipped=qty_shipped,
                qty_received=qty_received,
                variance_reason_code=variance_reason_code,
            )
        )

    # If ran-out-driven candidates didn't fill the target (a quiet day with
    # few sell-outs), top up with plain surplus-to-surplus rebalances between
    # any two branches that both received the same item today — still real
    # stock movement, just prompted by "we're overstocked" rather than "they
    # ran out."
    remaining_pairs = [
        (src, dst, item_code)
        for item_code in item_by_code
        for src in received
        for dst in received
        if src != dst and item_code in received[src] and item_code in received[dst]
    ]
    rng.shuffle(remaining_pairs)
    for source_branch, dest_branch, item_code in remaining_pairs:
        if len(plan.transfers) >= target_transfer_count:
            break
        surplus = received[source_branch][item_code].qty - sold.get(
            source_branch, {}
        ).get(item_code, SalesLine(item_code, Decimal(0), False)).qty
        if surplus <= TRANSFER_MIN_SURPLUS:
            continue
        qty_requested = min(surplus - 1, Decimal(rng.randint(*TRANSFER_QTY)))
        if qty_requested <= 0:
            continue

        target_status, qty_shipped, qty_received, variance_reason_code = (
            _pick_transfer_execution(rng, qty_requested)
        )

        plan.transfers.append(
            TransferSeed(
                source_location_code=source_branch,
                dest_location_code=dest_branch,
                item_code=item_code,
                qty_requested=qty_requested,
                reason_code=TRANSFER_REASON_SURPLUS,
                target_status=target_status,
                qty_shipped=qty_shipped,
                qty_received=qty_received,
                variance_reason_code=variance_reason_code,
            )
        )

    # --- Waste -----------------------------------------------------------
    # Only what was delivered and demonstrably not sold can be wasted. An
    # item that ran out has nothing left to throw away, and an item sold
    # without a delivery has no stock to waste — both are skipped rather
    # than forced to fit the percentage bands.
    reason_codes = [code for code, _ in WASTE_REASONS]
    reason_weights = [weight for _, weight in WASTE_REASONS]

    # Only branches that both received and sold: waste is derived from the
    # gap between the two, so a branch that never reported sales has no
    # measured gap — its delivery just sits as unsold stock (high excess),
    # which is a truer picture than declaring all of it wasted.
    waste_candidates = sorted(set(received.keys()) & set(sold.keys()))
    waste_branches = _share(rng, waste_candidates, WASTE_BRANCH_SHARE)
    for branch in sorted(waste_branches):
        branch_sold = sold.get(branch, {})
        eligible = [
            item_code
            for item_code, line in received[branch].items()
            if line.qty - branch_sold.get(item_code, SalesLine(item_code, Decimal(0), False)).qty > 0
        ]
        # Same-day and multi-day items get their surplus turned into an
        # actual waste entry at very different rates — see
        # SAME_DAY_WASTE_ITEM_SHARE/MULTI_DAY_WASTE_ITEM_SHARE above.
        eligible_same_day = [c for c in eligible if item_by_code[c].shelf_life_days == 0]
        eligible_multi_day = [c for c in eligible if item_by_code[c].shelf_life_days > 0]
        wasted_today = _share(rng, sorted(eligible_same_day), SAME_DAY_WASTE_ITEM_SHARE) + _share(
            rng, sorted(eligible_multi_day), MULTI_DAY_WASTE_ITEM_SHARE
        )
        for item_code in sorted(wasted_today):
            delivered = received[branch][item_code].qty
            sold_qty = branch_sold.get(
                item_code, SalesLine(item_code, Decimal(0), False)
            ).qty
            plan.waste.append(
                WasteEntry(
                    location_code=branch,
                    item_code=item_code,
                    qty=delivered - sold_qty,
                    reason_code=rng.choices(reason_codes, weights=reason_weights, k=1)[0],
                    production_date=received[branch][item_code].production_date,
                )
            )

    return plan


def _transfer_api_calls(transfer: TransferSeed) -> int:
    """create is always one call; ship/receive/cancel each add one more,
    exactly matching how many of them execute() will actually issue for
    this transfer's target_status."""
    calls = 1
    if transfer.target_status in ("IN_TRANSIT", "RECEIVED"):
        calls += 1  # ship
    if transfer.target_status == "RECEIVED":
        calls += 1  # receive
    if transfer.target_status == "CANCELLED":
        calls += 1  # cancel
    return calls


def summarize(plan: SeedPlan) -> str:
    received_units = sum(
        int(line.qty) for branch in plan.receiving for line in branch.lines
    )
    sold_units = sum(int(line.qty) for branch in plan.sales for line in branch.lines)
    wasted_units = sum(int(entry.qty) for entry in plan.waste)
    transferred_units = sum(int(t.qty_requested) for t in plan.transfers)
    received_branches = {b.location_code for b in plan.receiving}
    sales_branches = {b.location_code for b in plan.sales}
    transfer_api_calls = sum(_transfer_api_calls(t) for t in plan.transfers)
    transfer_status_counts = {
        status: sum(1 for t in plan.transfers if t.target_status == status)
        for status, _ in TRANSFER_STATUS_WEIGHTS
    }

    lines = [
        f"  business_date       {plan.business_date}",
        f"  run_id              {plan.run_id}",
        "",
        f"  Receiving           {len(plan.receiving):>4} branches, "
        f"{sum(len(b.lines) for b in plan.receiving):>5} lines, {received_units:>7} units",
        f"  Sales               {len(plan.sales):>4} branches, "
        f"{sum(len(b.lines) for b in plan.sales):>5} lines, {sold_units:>7} units",
        f"  Transfers           {len(plan.transfers):>4} transfers, "
        f"{'':>5}       {transferred_units:>7} units "
        f"({', '.join(f'{count} {status}' for status, count in transfer_status_counts.items() if count) or 'none'})",
        f"  Waste               {len(plan.waste):>4} entries, "
        f"{'':>5}       {wasted_units:>7} units",
        "",
        f"  Sold without a delivery today: {len(sales_branches - received_branches)} branch(es) "
        f"({', '.join(sorted(sales_branches - received_branches)) or 'none'})",
        f"  Ran-out lines:      {sum(1 for b in plan.sales for line in b.lines if line.sold_out)}",
        f"  API calls to make:  "
        f"{len(plan.receiving) + len(plan.sales) + transfer_api_calls + len(plan.waste)}",
    ]
    return "\n".join(lines)


def post(client: httpx.Client, path: str, payload: dict | None = None, **kwargs: object) -> dict:
    """Returns the parsed response body — most callers (receiving/sales/
    waste) don't need it, but the transfer cascade below does: it has to
    read back transfer_id from the create response before it can ship,
    receive or cancel that same transfer."""
    response = client.post(path, json=payload, **kwargs)  # type: ignore[arg-type]
    if response.status_code >= 400:
        raise SystemExit(
            f"\n{path} failed ({response.status_code}): {response.text}\n"
            f"payload: {json.dumps(payload, default=str)}"
        )
    return response.json()  # type: ignore[no-any-return]


def execute(plan: SeedPlan, client: httpx.Client, manifest_path: Path) -> None:
    """Writes the plan in cascade order, recording progress after each branch
    so an interrupted run can be diagnosed (and the already-written portion
    identified) rather than guessed at."""
    done: dict[str, list[str]] = {"receiving": [], "sales": [], "transfers": [], "waste": []}

    def checkpoint() -> None:
        manifest_path.write_text(
            json.dumps(
                {
                    "run_id": plan.run_id,
                    "business_date": str(plan.business_date),
                    "completed": done,
                },
                indent=2,
            )
        )

    transfer_api_calls = sum(_transfer_api_calls(t) for t in plan.transfers)
    total = len(plan.receiving) + len(plan.sales) + transfer_api_calls + len(plan.waste)
    step = 0

    for branch in plan.receiving:
        post(
            client,
            "/api/v1/receiving",
            {
                "business_date": str(plan.business_date),
                "location_code": branch.location_code,
                "ref_doc_id": branch.ref_doc_id,
                "confirmed_by_name": f"SAMPLE DATA {plan.run_id}",
                "lines": [
                    {
                        "item_code": line.item_code,
                        "qty": str(line.qty),
                        "production_date": str(line.production_date),
                    }
                    for line in branch.lines
                ],
            },
        )
        done["receiving"].append(branch.location_code)
        step += 1
        print(f"\r  [{step}/{total}] receiving {branch.location_code}   ", end="", flush=True)
    checkpoint()

    for sales_branch in plan.sales:
        post(
            client,
            "/api/v1/sales",
            {
                "business_date": str(plan.business_date),
                "location_code": sales_branch.location_code,
                "confirmed_by_name": f"SAMPLE DATA {plan.run_id}",
                "lines": [
                    {
                        "item_code": line.item_code,
                        "qty": str(line.qty),
                        "sold_out": line.sold_out,
                    }
                    for line in sales_branch.lines
                ],
            },
        )
        done["sales"].append(sales_branch.location_code)
        step += 1
        print(f"\r  [{step}/{total}] sales {sales_branch.location_code}   ", end="", flush=True)
    checkpoint()

    for i, transfer in enumerate(plan.transfers):
        created = post(
            client,
            "/api/v1/transfers",
            {
                "source_location_code": transfer.source_location_code,
                "dest_location_code": transfer.dest_location_code,
                "reason_code": transfer.reason_code,
                "notes": f"SAMPLE DATA {plan.run_id}",
                "lines": [{"item_code": transfer.item_code, "qty_requested": str(transfer.qty_requested)}],
            },
        )
        transfer_id = created["transfer_id"]

        if transfer.target_status == "CANCELLED":
            post(client, f"/api/v1/transfers/{transfer_id}/cancel")
        elif transfer.qty_shipped is not None:
            post(
                client,
                f"/api/v1/transfers/{transfer_id}/ship",
                {
                    "business_date": str(plan.business_date),
                    "lines": [{"item_code": transfer.item_code, "qty_shipped": str(transfer.qty_shipped)}],
                },
                headers={"Idempotency-Key": f"seed-{plan.run_id}-{i}-ship"},
            )
            if transfer.target_status == "RECEIVED":
                assert transfer.qty_received is not None
                post(
                    client,
                    f"/api/v1/transfers/{transfer_id}/receive",
                    {
                        "business_date": str(plan.business_date),
                        "lines": [
                            {
                                "item_code": transfer.item_code,
                                "qty_received": str(transfer.qty_received),
                                "variance_reason_code": transfer.variance_reason_code,
                            }
                        ],
                    },
                    headers={"Idempotency-Key": f"seed-{plan.run_id}-{i}-receive"},
                )

        done["transfers"].append(
            f"{transfer.source_location_code}->{transfer.dest_location_code}/{transfer.item_code}"
            f" ({transfer.target_status})"
        )
        step += _transfer_api_calls(transfer)
        print(
            f"\r  [{step}/{total}] transfer {transfer.source_location_code}->{transfer.dest_location_code}   ",
            end="",
            flush=True,
        )
    checkpoint()

    for entry in plan.waste:
        post(
            client,
            "/api/v1/waste",
            {
                "business_date": str(plan.business_date),
                "location_code": entry.location_code,
                "item_code": entry.item_code,
                "qty": str(entry.qty),
                "reason_code": entry.reason_code,
                "production_date": str(entry.production_date) if entry.production_date else None,
            },
        )
        done["waste"].append(f"{entry.location_code}/{entry.item_code}")
        step += 1
        if step % 25 == 0 or step == total:
            print(f"\r  [{step}/{total}] waste {entry.location_code}   ", end="", flush=True)
    checkpoint()
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Populate one business date with sample Receiving/Sales/Waste activity."
    )
    parser.add_argument("--date", required=True, help="Business date to populate (YYYY-MM-DD).")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually write. Without this the script only prints what it would do.",
    )
    parser.add_argument(
        "--seed", type=int, default=None, help="RNG seed, for a reproducible plan."
    )
    parser.add_argument(
        "--only-branch",
        default=None,
        help="Restrict to a single branch code — use this for the first live run.",
    )
    parser.add_argument(
        "--allow-existing",
        action="store_true",
        help="Proceed even if the date already has movements on file.",
    )
    parser.add_argument("--api-url", default="http://127.0.0.1:8010")
    parser.add_argument(
        "--token", default=None, help="Access token to use instead of minting one."
    )
    args = parser.parse_args()

    business_date = dt.date.fromisoformat(args.date)
    run_id = uuid.uuid4().hex[:8]
    seed = args.seed if args.seed is not None else random.randrange(2**32)
    rng = random.Random(seed)

    engine = create_engine(settings.database_url)
    branches, items = load_reference_data(engine)
    if args.only_branch:
        if args.only_branch not in branches:
            raise SystemExit(f"{args.only_branch} is not an active, orderable branch.")
        branches = [args.only_branch]
    if not branches or not items:
        raise SystemExit("No active branches or items to generate against.")

    plan = build_plan(rng, business_date, run_id, branches, items)

    print(f"\nCocopan IMS — sample data for {business_date}")
    print(f"Source: {len(branches)} active branches, {len(items)} active items (rng seed {seed})\n")
    print(summarize(plan))

    existing = count_existing_movements(engine, business_date)
    if existing:
        print(f"\n  ! {business_date} already has {existing} movement(s) on file.")
        if not args.allow_existing:
            print(
                "    Receiving/Sales are diff-based: re-posting a branch/date that already\n"
                "    has data rewrites it to this plan's quantities via correction rows,\n"
                "    rather than adding to it. Pass --allow-existing if that's intended."
            )
            if args.execute:
                raise SystemExit(1)

    if not args.execute:
        print("\nDry run — nothing written. Re-run with --execute to apply.\n")
        return

    user_id, email = resolve_seed_user(engine)
    token = args.token or create_token(user_id, "access", dt.timedelta(hours=2))

    MANIFEST_DIR.mkdir(exist_ok=True)
    manifest_path = MANIFEST_DIR / f"{business_date:%Y%m%d}-{run_id}.json"

    print(f"\nWriting as {email} (user_id {user_id}) -> {args.api_url}")
    print(f"Manifest: {manifest_path}\n")

    with httpx.Client(
        base_url=args.api_url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
    ) as client:
        health = client.get("/health")
        if health.status_code != 200:
            raise SystemExit(f"API not healthy at {args.api_url}: {health.status_code}")
        me = client.get("/api/v1/auth/me")
        if me.status_code != 200:
            raise SystemExit(f"Token rejected: {me.status_code} {me.text}")
        granted = set(me.json()["permissions"])
        missing = [p for p in REQUIRED_PERMISSIONS if p not in granted]
        if missing:
            raise SystemExit(f"{email} is missing permission(s): {', '.join(missing)}")

        execute(plan, client, manifest_path)

    print(f"\nDone. {business_date} populated. Tagged 'SAMPLE DATA {run_id}'.\n")


if __name__ == "__main__":
    main()
