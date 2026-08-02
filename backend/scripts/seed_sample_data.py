"""Generates a day of realistic sample Receiving -> Sales -> Waste activity.

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
# So WASTE_BRANCH_SHARE is probabilistic (simulates branches that "missed"
# recording waste entirely) but WASTE_ITEM_SHARE stays at 100% — a branch
# that does report, reports every eligible item with stock left over.
WASTE_BRANCH_SHARE = (0.70, 1.00)
WASTE_ITEM_SHARE = (1.00, 1.00)

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

REQUIRED_PERMISSIONS = ("receiving.confirm", "sales.record", "waste.record")

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
class SeedPlan:
    business_date: dt.date
    run_id: str
    receiving: list[BranchReceiving] = field(default_factory=list)
    sales: list[BranchSales] = field(default_factory=list)
    waste: list[WasteEntry] = field(default_factory=list)


def _share(rng: random.Random, population: list, share: tuple[float, float]) -> list:
    """A random sample sized to a random share of the population, never empty
    when the population isn't."""
    if not population:
        return []
    fraction = rng.uniform(*share)
    count = max(1, round(len(population) * fraction))
    return rng.sample(population, min(count, len(population)))


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

    for branch in sorted(selling_branches):
        branch_received = received[branch]
        sellable = _share(rng, sorted(branch_received.keys()), SALES_ITEM_SHARE)

        # Occasionally a branch sells something it wasn't delivered today
        # (carryover stock, or a transfer this prototype doesn't model yet).
        unstocked = [c for c in item_by_code if c not in branch_received]
        extra: list[str] = []
        if unstocked and rng.random() < SALES_EXTRA_ITEM_PROBABILITY:
            extra = rng.sample(
                unstocked, min(rng.randint(*SALES_EXTRA_ITEMS), len(unstocked))
            )

        ran_out = set(_share(rng, sorted(sellable), RAN_OUT_SHARE))

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
        for item_code in sorted(_share(rng, sorted(eligible), WASTE_ITEM_SHARE)):
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


def summarize(plan: SeedPlan) -> str:
    received_units = sum(
        int(line.qty) for branch in plan.receiving for line in branch.lines
    )
    sold_units = sum(int(line.qty) for branch in plan.sales for line in branch.lines)
    wasted_units = sum(int(entry.qty) for entry in plan.waste)
    received_branches = {b.location_code for b in plan.receiving}
    sales_branches = {b.location_code for b in plan.sales}

    lines = [
        f"  business_date       {plan.business_date}",
        f"  run_id              {plan.run_id}",
        "",
        f"  Receiving           {len(plan.receiving):>4} branches, "
        f"{sum(len(b.lines) for b in plan.receiving):>5} lines, {received_units:>7} units",
        f"  Sales               {len(plan.sales):>4} branches, "
        f"{sum(len(b.lines) for b in plan.sales):>5} lines, {sold_units:>7} units",
        f"  Waste               {len(plan.waste):>4} entries, "
        f"{'':>5}       {wasted_units:>7} units",
        "",
        f"  Sold without a delivery today: {len(sales_branches - received_branches)} branch(es) "
        f"({', '.join(sorted(sales_branches - received_branches)) or 'none'})",
        f"  Ran-out lines:      {sum(1 for b in plan.sales for line in b.lines if line.sold_out)}",
        f"  API calls to make:  {len(plan.receiving) + len(plan.sales) + len(plan.waste)}",
    ]
    return "\n".join(lines)


def post(client: httpx.Client, path: str, payload: dict) -> None:
    response = client.post(path, json=payload)
    if response.status_code >= 400:
        raise SystemExit(
            f"\n{path} failed ({response.status_code}): {response.text}\n"
            f"payload: {json.dumps(payload, default=str)}"
        )


def execute(plan: SeedPlan, client: httpx.Client, manifest_path: Path) -> None:
    """Writes the plan in cascade order, recording progress after each branch
    so an interrupted run can be diagnosed (and the already-written portion
    identified) rather than guessed at."""
    done: dict[str, list[str]] = {"receiving": [], "sales": [], "waste": []}

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

    total = len(plan.receiving) + len(plan.sales) + len(plan.waste)
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
