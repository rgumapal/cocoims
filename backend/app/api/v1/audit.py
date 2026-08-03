"""Audit trail viewer — SPEC §13 GET /api/v1/audit.

Read-only surface over audit.record_change (see app/models/audit.py's own
docstring for why this app never writes to it). Every master, reference
and parameter table mutation lands there via a database trigger
(db/ddl/001_schema.sql §4.9) — this router only filters, paginates, and
exports what's already there.
"""
import csv
import datetime as dt
import io
import json
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel
from sqlalchemy import distinct, select
from sqlalchemy.orm import Session

from app.api.v1.pagination import Page
from app.auth.deps import get_db, require_permission
from app.models import AppUser, AuditRecordChange

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])

# Export has no cursor — it's a one-shot download, not a paginated feed —
# so it gets its own hard cap instead of CLAUDE.md's usual cursor-only
# rule. 20,000 rows is already generous against this table's real growth
# rate (a few hundred a week across the whole network today).
EXPORT_ROW_LIMIT = 20_000


class AuditRecordOut(BaseModel):
    audit_id: int
    occurred_at: dt.datetime
    schema_name: str
    table_name: str
    record_pk: str
    action: str
    changed_by: int | None
    changed_by_email: str | None
    changed_by_full_name: str | None
    changed_fields: list[str] | None
    old_values: dict | None
    new_values: dict | None
    request_id: str | None


def _date_range_filters(
    start_date: dt.date, end_date: dt.date, table_name: str | None, changed_by: int | None
) -> list:
    return [
        AuditRecordChange.occurred_at >= start_date,
        # end_date is inclusive of the whole day, so compare against the
        # start of the *next* day rather than a bare "< end_date".
        AuditRecordChange.occurred_at < end_date + dt.timedelta(days=1),
        *([AuditRecordChange.table_name == table_name] if table_name else []),
        *([AuditRecordChange.changed_by == changed_by] if changed_by else []),
    ]


@router.get("/tables", response_model=list[str])
def list_audited_tables(
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[AppUser, Depends(require_permission("audit.read"))],
) -> list[str]:
    """Every table name that actually appears in the audit trail — backs
    the table filter dropdown with real values instead of a hand-maintained
    list that can drift from db/ddl's actual trigger set."""
    return list(
        session.execute(
            select(distinct(AuditRecordChange.table_name)).order_by(AuditRecordChange.table_name)
        ).scalars().all()
    )


@router.get("", response_model=Page[AuditRecordOut])
def list_audit(
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[AppUser, Depends(require_permission("audit.read"))],
    start_date: dt.date = Query(...),
    end_date: dt.date = Query(...),
    table_name: str | None = Query(default=None),
    changed_by: int | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
) -> Page[AuditRecordOut]:
    """Every table/record mutation in the date range, newest first.

    Cursor is the audit_id of the last row on the previous page
    (CLAUDE.md PERFORMANCE: cursor pagination only, never OFFSET on a
    table that can grow past a few thousand rows). audit_id is a single
    BIGSERIAL shared across every partition, not reset per partition, so
    it sorts identically to occurred_at without needing a compound cursor.
    """
    stmt = (
        select(AuditRecordChange, AppUser.full_name)
        .outerjoin(AppUser, AppUser.user_id == AuditRecordChange.changed_by)
        .where(*_date_range_filters(start_date, end_date, table_name, changed_by))
        .order_by(AuditRecordChange.audit_id.desc())
    )
    if cursor:
        stmt = stmt.where(AuditRecordChange.audit_id < int(cursor))

    rows = session.execute(stmt.limit(limit + 1)).all()
    next_cursor = str(rows[limit - 1][0].audit_id) if len(rows) > limit else None
    items = [
        AuditRecordOut(
            audit_id=r.audit_id,
            occurred_at=r.occurred_at,
            schema_name=r.schema_name,
            table_name=r.table_name,
            record_pk=r.record_pk,
            action=r.action,
            changed_by=r.changed_by,
            changed_by_email=r.changed_by_email,
            changed_by_full_name=full_name,
            changed_fields=r.changed_fields,
            old_values=r.old_values,
            new_values=r.new_values,
            request_id=str(r.request_id) if r.request_id else None,
        )
        for r, full_name in rows[:limit]
    ]
    return Page(items=items, next_cursor=next_cursor)


@router.get("/export")
def export_audit(
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[AppUser, Depends(require_permission("audit.read"))],
    start_date: dt.date = Query(...),
    end_date: dt.date = Query(...),
    table_name: str | None = Query(default=None),
    changed_by: int | None = Query(default=None),
) -> Response:
    """Downloads every matching row as CSV. Same filters as the list
    endpoint above, but no pagination — this is a one-shot export a
    reviewer takes offline, capped at EXPORT_ROW_LIMIT rather than
    cursor-paginated.
    """
    rows = session.execute(
        select(AuditRecordChange, AppUser.full_name)
        .outerjoin(AppUser, AppUser.user_id == AuditRecordChange.changed_by)
        .where(*_date_range_filters(start_date, end_date, table_name, changed_by))
        .order_by(AuditRecordChange.audit_id.desc())
        .limit(EXPORT_ROW_LIMIT)
    ).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "occurred_at",
            "table_name",
            "record_pk",
            "action",
            "changed_by_email",
            "changed_by_full_name",
            "changed_fields",
            "old_values",
            "new_values",
            "request_id",
        ]
    )
    for movement, full_name in rows:
        writer.writerow(
            [
                movement.occurred_at.isoformat(),
                movement.table_name,
                movement.record_pk,
                movement.action,
                movement.changed_by_email or "",
                full_name or "",
                ",".join(movement.changed_fields) if movement.changed_fields else "",
                json.dumps(movement.old_values) if movement.old_values else "",
                json.dumps(movement.new_values) if movement.new_values else "",
                str(movement.request_id) if movement.request_id else "",
            ]
        )

    filename = f"audit-{start_date}-to-{end_date}.csv"
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
