"""fix missing it.admin@cocopan.ph user

Found while testing auth live: only 14 of the 15 users db/seed/002_client_data.sql
intends to create actually exist. system@cocopan.ph is inserted first with an
explicit user_id=1 (needed so location_status_history.changed_by has a valid
FK target during the same seed run), which does not advance
core.app_user_user_id_seq. The very next INSERT — a 14-row batch starting
with it.admin@cocopan.ph, relying on the BIGSERIAL default — then has its
first row's nextval() also return 1, collide with system@cocopan.ph's
explicit row, and get silently dropped by the seed's own ON CONFLICT DO
NOTHING (which catches any conflicting unique constraint, not only the one
intended). Every later row in that batch succeeds, because nextval() already
advanced past 1 by the time of the collision — this is why demand.planner
and everyone after it exist, and only it.admin is missing.

The blast radius: it.admin@cocopan.ph never existed, so the later user_role
and user_scope inserts that join on `email = 'it.admin@cocopan.ph'` matched
zero rows too — no SYS_ADMIN role, no ALL scope. There was no interactively-
loggable SYS_ADMIN account at all (system@cocopan.ph holds that role but is
is_service=TRUE with no password, by design, for API-key auth only).

Fixed by inserting exactly the three rows the original seed intended, with
the same idempotency guard (ON CONFLICT DO NOTHING) so re-running this is
safe. The sequence itself needs no repair: nextval() already self-corrected
for every row after the collision, and no other row in this codebase inserts
app_user with an explicit id, so this cannot recur.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-31
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO core.app_user (email, full_name, is_active, is_service)
        VALUES ('it.admin@cocopan.ph', 'IT Administrator', TRUE, FALSE)
        ON CONFLICT DO NOTHING;

        INSERT INTO core.user_role (user_id, role_code, granted_by)
        SELECT u.user_id, 'SYS_ADMIN', 1
        FROM core.app_user u
        WHERE u.email = 'it.admin@cocopan.ph'
        ON CONFLICT DO NOTHING;

        INSERT INTO core.user_scope (user_id, scope_type, scope_value)
        SELECT u.user_id, 'ALL', '*'
        FROM core.app_user u
        WHERE u.email = 'it.admin@cocopan.ph'
        ON CONFLICT DO NOTHING;
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM core.user_scope
        WHERE user_id = (SELECT user_id FROM core.app_user WHERE email = 'it.admin@cocopan.ph');

        DELETE FROM core.user_role
        WHERE user_id = (SELECT user_id FROM core.app_user WHERE email = 'it.admin@cocopan.ph');

        DELETE FROM core.app_user WHERE email = 'it.admin@cocopan.ph';
    """)
