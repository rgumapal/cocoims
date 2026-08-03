"""Post-login landing page summary — SPEC §12.5's "single content plane"
starts here: one aggregate read per screen the nav exposes, so a user sees
what needs attention before clicking into any one of them.

Every count is scoped by RLS exactly like any other query in this app —
nothing here re-implements branch scoping. core.stock_movement's own
location_code plus the session's app.location_scope/app.unrestricted
(set by app.auth.deps.get_db) already restrict what a non-unrestricted
user's aggregates can see; a store-scoped user's "items received today"
is already just their own branch's, for free.

A section is omitted (null), not zeroed out, for a user who lacks the
permission that domain's own list endpoint requires (CLAUDE.md ACCESS:
deny by default) — Receiving/Sales/Waste/Stock all read core.stock_movement,
so they share stock.py's "order.read" gate; Counts shares counts.py's
"count.submit"; Transfers shares transfers.py's "transfer.read"; Items and
Branches share their own list endpoints' gates.
"""
import datetime as dt
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.api.v1.locations import SYSTEM_LOCATION_TYPES
from app.auth.deps import get_current_user, get_db, get_user_permissions
from app.models import AppUser, CountSession, Item, Location, SoldOutEvent, StockMovement, Transfer

router = APIRouter(prefix="/api/v1", tags=["dashboard"])

# No forecast/replenishment engine exists yet (deferred per CLAUDE.md
# SCOPE), so "low" here is a plain historical comparison, not a demand
# forecast: today's count vs. the trailing 7-day daily average, flagged
# below LOW_RECEIVING_THRESHOLD_RATIO of that average. A simple, honest
# heuristic — replace with the real forecast baseline once SPEC §8 exists.
LOW_RECEIVING_THRESHOLD_RATIO = 0.7
TRAILING_WINDOW_DAYS = 7


class ReceivingSummary(BaseModel):
    branches_reported_today: int
    active_branch_count: int
    items_received_today: int
    is_low: bool  # items_received_today vs. its trailing 7-day average


class SalesSummary(BaseModel):
    total_sales: Decimal  # network-wide sales value today, priced items only
    # None only when no branch had any sales today (nothing to compare).
    highest_branch_sales: Decimal | None
    lowest_branch_sales: Decimal | None
    average_branch_sales: Decimal | None
    total_items_sold: int
    branches_reporting: int  # branches with >0 sales today — 0-sales branches excluded


class WasteSummary(BaseModel):
    items_logged_today: int
    branches_logged_today: int


class CountsSummary(BaseModel):
    open_count: int
    pending_approval_count: int


class StockSummary(BaseModel):
    run_outs_today: int


class TransfersSummary(BaseModel):
    in_transit_count: int  # shipped, waiting on the destination to receive
    draft_count: int  # created, waiting on the source to ship


class ItemsSummary(BaseModel):
    active_count: int
    total_count: int


class BranchesSummary(BaseModel):
    active_count: int
    total_count: int


class DashboardOut(BaseModel):
    receiving: ReceivingSummary | None
    sales: SalesSummary | None
    waste: WasteSummary | None
    counts: CountsSummary | None
    stock: StockSummary | None
    transfers: TransfersSummary | None
    items: ItemsSummary | None
    branches: BranchesSummary | None


def _distinct_items_moved(session: Session, movement_type: str, business_date: dt.date) -> int:
    return session.execute(
        select(func.count(func.distinct(StockMovement.item_code))).where(
            StockMovement.movement_type == movement_type,
            StockMovement.business_date == business_date,
        )
    ).scalar_one()


def _total_qty_moved(
    session: Session, movement_type: str, business_date: dt.date, *, negate: bool = False
) -> int:
    """Total units moved, not the count of distinct SKUs — "500 items
    received" means 500 units arrived, not "5 different products showed
    up." negate=True for movement types stored negative (SALE, WASTE)."""
    total = session.execute(
        select(func.coalesce(func.sum(StockMovement.qty), 0)).where(
            StockMovement.movement_type == movement_type,
            StockMovement.business_date == business_date,
        )
    ).scalar_one()
    signed = -total if negate else total
    return int(signed)


def _distinct_branches_moved(session: Session, movement_type: str, business_date: dt.date) -> int:
    return session.execute(
        select(func.count(func.distinct(StockMovement.location_code))).where(
            StockMovement.movement_type == movement_type,
            StockMovement.business_date == business_date,
        )
    ).scalar_one()


def _receiving_summary(session: Session, today: dt.date) -> ReceivingSummary:
    items_received_today = _total_qty_moved(session, "RECEIPT", today)

    daily_counts = (
        select(
            StockMovement.business_date,
            func.sum(StockMovement.qty).label("daily_count"),
        )
        .where(
            StockMovement.movement_type == "RECEIPT",
            StockMovement.business_date >= today - dt.timedelta(days=TRAILING_WINDOW_DAYS),
            StockMovement.business_date < today,
        )
        .group_by(StockMovement.business_date)
        .subquery()
    )
    trailing_avg = session.execute(select(func.avg(daily_counts.c.daily_count))).scalar_one()
    # No trailing history yet (e.g. a fresh deployment) means nothing to
    # compare against — never flag "low" from an absence of data.
    is_low = trailing_avg is not None and items_received_today < float(
        trailing_avg
    ) * LOW_RECEIVING_THRESHOLD_RATIO

    # RLS scopes this the same way as every other query here: a branch-
    # scoped user's distinct-location count over their own visible rows
    # tops out at their own branch(es), never another's.
    branches_reported_today = session.execute(
        select(func.count(func.distinct(StockMovement.location_code))).where(
            StockMovement.movement_type == "RECEIPT", StockMovement.business_date == today
        )
    ).scalar_one()
    active_branch_count = session.execute(
        select(func.count()).select_from(Location).where(Location.is_active.is_(True))
    ).scalar_one()

    return ReceivingSummary(
        branches_reported_today=branches_reported_today,
        active_branch_count=active_branch_count,
        items_received_today=items_received_today,
        is_low=is_low,
    )


def _sales_summary(session: Session, today: dt.date) -> SalesSummary:
    """Total sales value and its spread across branches — the Dashboard
    Sales widget's headline metric. Priced through core.v_effective_price
    (migration 0002's branch-override-over-network resolution), the same
    source app.api.v1.sales itself displays. A single set-based query: the
    CTE nets each branch's sales value and drops any branch that sold
    nothing today (HAVING > 0) — a branch that didn't report isn't a $0
    sales day, it's not a data point, and would otherwise drag "lowest" and
    "average" toward zero for a reason that has nothing to do with sales
    performance. RLS on core.stock_movement (via get_db's session-scoped
    app.location_scope) already restricts this to what the caller can see,
    same as every other query in this module.
    """
    row = session.execute(
        text("""
            WITH branch_sales AS (
                SELECT sm.location_code, SUM(-sm.qty * vep.srp) AS total
                FROM core.stock_movement sm
                JOIN core.v_effective_price vep
                  ON vep.location_code = sm.location_code
                 AND vep.item_code = sm.item_code
                 AND vep.srp IS NOT NULL
                WHERE sm.movement_type = 'SALE'
                  AND sm.business_date = :today
                GROUP BY sm.location_code
                HAVING SUM(-sm.qty * vep.srp) > 0
            )
            SELECT
                COALESCE(SUM(total), 0) AS total_sales,
                MAX(total) AS highest_branch_sales,
                MIN(total) AS lowest_branch_sales,
                AVG(total) AS average_branch_sales,
                COUNT(*) AS branches_reporting
            FROM branch_sales
        """),
        {"today": today},
    ).one()

    return SalesSummary(
        total_sales=Decimal(row.total_sales),
        highest_branch_sales=Decimal(row.highest_branch_sales) if row.highest_branch_sales is not None else None,
        lowest_branch_sales=Decimal(row.lowest_branch_sales) if row.lowest_branch_sales is not None else None,
        average_branch_sales=Decimal(row.average_branch_sales) if row.average_branch_sales is not None else None,
        total_items_sold=_total_qty_moved(session, "SALE", today, negate=True),
        branches_reporting=row.branches_reporting,
    )


@router.get("/dashboard", response_model=DashboardOut)
def get_dashboard(
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[AppUser, Depends(get_current_user)],
    business_date: dt.date | None = Query(
        None, description="Day to summarise. Defaults to the server's current date."
    ),
) -> DashboardOut:
    """One aggregate read per nav screen, each included only if the caller
    holds the same permission that screen's own list endpoint requires.

    Requires: a valid access token. No single permission gates the whole
    endpoint — each section checks its own (see module docstring).
    """
    permissions = get_user_permissions(session, user.user_id)
    # The client sends its own local business date (the browser's calendar
    # day, not UTC's — see frontend/src/lib/date.ts); this fallback only
    # covers a caller that omits it entirely, e.g. curl or /docs.
    today = business_date or dt.date.today()

    receiving = sales = waste = stock = None
    if "order.read" in permissions:
        receiving = _receiving_summary(session, today)
        sales = _sales_summary(session, today)
        waste = WasteSummary(
            items_logged_today=_distinct_items_moved(session, "WASTE", today),
            branches_logged_today=_distinct_branches_moved(session, "WASTE", today),
        )
        run_outs_today = session.execute(
            select(func.count()).select_from(SoldOutEvent).where(SoldOutEvent.business_date == today)
        ).scalar_one()
        stock = StockSummary(run_outs_today=run_outs_today)

    counts = None
    if "count.submit" in permissions:
        open_count = session.execute(
            select(func.count()).select_from(CountSession).where(CountSession.status == "OPEN")
        ).scalar_one()
        pending_approval_count = session.execute(
            select(func.count()).select_from(CountSession).where(CountSession.status == "SUBMITTED")
        ).scalar_one()
        counts = CountsSummary(open_count=open_count, pending_approval_count=pending_approval_count)

    transfers = None
    if "transfer.read" in permissions:
        # RLS on core.transfer (migration 0016) already limits these counts
        # to transfers where the caller has scope on the source or
        # destination, same as every other query in this module.
        in_transit_count = session.execute(
            select(func.count()).select_from(Transfer).where(Transfer.status == "IN_TRANSIT")
        ).scalar_one()
        draft_count = session.execute(
            select(func.count()).select_from(Transfer).where(Transfer.status == "DRAFT")
        ).scalar_one()
        transfers = TransfersSummary(in_transit_count=in_transit_count, draft_count=draft_count)

    items = None
    if "item.read" in permissions:
        total_count = session.execute(select(func.count()).select_from(Item)).scalar_one()
        active_count = session.execute(
            select(func.count()).select_from(Item).where(Item.lifecycle_status == "ACTIVE")
        ).scalar_one()
        items = ItemsSummary(active_count=active_count, total_count=total_count)

    branches = None
    if "location.read" in permissions:
        # Excludes system/virtual location types (the transfers in-transit
        # bucket) — same reasoning as list_locations' own default: this
        # card is "how many branches," not "how many rows in core.location."
        not_system = Location.location_type.notin_(SYSTEM_LOCATION_TYPES)
        total_count = session.execute(
            select(func.count()).select_from(Location).where(not_system)
        ).scalar_one()
        active_count = session.execute(
            select(func.count()).select_from(Location).where(Location.is_active.is_(True), not_system)
        ).scalar_one()
        branches = BranchesSummary(active_count=active_count, total_count=total_count)

    return DashboardOut(
        receiving=receiving,
        sales=sales,
        waste=waste,
        counts=counts,
        stock=stock,
        transfers=transfers,
        items=items,
        branches=branches,
    )
