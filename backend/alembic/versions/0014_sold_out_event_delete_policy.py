"""add DELETE policy to core.sold_out_event

Migration 0010 gave this table FORCE ROW LEVEL SECURITY with SELECT and
INSERT policies only — it was designed as an append/lookup-only event log
at the time. The new Sales edit flow (app/api/v1/sales.py) needs to clear a
sold_out flag when a line is edited or removed, which is a real DELETE, not
an append-only-ledger violation (there's no "offsetting" way to un-flag a
boolean the way stock_movement corrections offset a quantity).

Without this, cocoims_app's DELETE grant (already present — see the table
grants set by migration 0004's ALTER DEFAULT PRIVILEGES) is silently
overridden by RLS: FORCE ROW LEVEL SECURITY with no policy for a given
command denies every row for that command by default, so the DELETE
succeeds (no error) but removes zero rows. Found by testing the edit flow
end-to-end, not by inspection — a stale sold_out flag survived a delete
that looked like it should have worked.

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-01
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE POLICY scope_by_location_delete ON core.sold_out_event
            FOR DELETE
            USING (
                current_setting('app.unrestricted', true) = 'on'
                OR location_code = ANY (string_to_array(current_setting('app.location_scope', true), ','))
            );
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS scope_by_location_delete ON core.sold_out_event;")
