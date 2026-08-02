"""add UPDATE/DELETE RLS policies to core.stock_movement

Same class of bug as migration 0014's sold_out_event fix, found while
investigating a failing pytest suite rather than by inspection: migration
0004 gave core.stock_movement FORCE ROW LEVEL SECURITY with SELECT and
INSERT policies only. Postgres's default-deny behavior means any command
type with no matching policy is silently denied for every row — not with
an error, just zero rows affected — for ANY role, including the owning
superuser `cocoims` (FORCE applies even to the owner).

The append-only guarantee this table depends on (CLAUDE.md DATA: "No
UPDATE or DELETE") was still effectively holding, but for the wrong
reason: an UPDATE/DELETE against this table was silently matching zero
rows *before* core.fn_block_movement_mutation's BEFORE-trigger ever got a
chance to fire and raise its clear "append-only" exception (migration
0004's `trg_stock_movement_immutable`). A developer attempting a mutation
today sees "0 rows affected", not the intended, actionable error message —
confusing, and easy to mistake for "my WHERE clause matched nothing"
rather than "this table doesn't allow that".

This migration doesn't change what's allowed (mutations were already
impossible) — it changes *why*, restoring the documented trigger-based
mechanism so the error message actually explains itself. Discovered via
tests/test_ledger_immutability.py::test_owning_superuser_still_cannot_update
et al. asserting the specific "append-only" message and getting a silent
no-op instead.

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-02
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE POLICY scope_by_location_update ON core.stock_movement
            FOR UPDATE
            USING (
                current_setting('app.unrestricted', true) = 'on'
                OR location_code = ANY (string_to_array(current_setting('app.location_scope', true), ','))
            );
    """)
    op.execute("""
        CREATE POLICY scope_by_location_delete ON core.stock_movement
            FOR DELETE
            USING (
                current_setting('app.unrestricted', true) = 'on'
                OR location_code = ANY (string_to_array(current_setting('app.location_scope', true), ','))
            );
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS scope_by_location_update ON core.stock_movement;")
    op.execute("DROP POLICY IF EXISTS scope_by_location_delete ON core.stock_movement;")
