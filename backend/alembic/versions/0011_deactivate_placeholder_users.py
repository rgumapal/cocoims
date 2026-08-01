"""deactivate placeholder seed users, keep the real roster

db/seed/002_client_data.sql's interactive users were always placeholders
standing in for real Cocopan positions (SPEC §16 open item #12: org chart
unconfirmed — see migration 0009's own docstring). Now that the app has a
real admin account (regie.gumapal@gmail.com, migration 0009), those
placeholders are noise in the Users screen rather than useful seed data.

Per CLAUDE.md ("never delete... deactivate — history depends on it") this
is is_active=FALSE, not a DELETE: role/scope grants and any created_by
references stay intact, and the accounts can be reactivated the moment a
real person is assigned to that position.

Two accounts are deliberately left active alongside regie.gumapal@gmail.com:
- system@cocopan.ph — the service account created_by defaults resolve to
  (migration 0005); not a person, has no "position" to reassign.
- svc.pos@cocopan.ph — the POS integration service account (SPEC §16 open
  item #4, still unresolved); same reasoning.
Both are is_service=TRUE, so they were never really "Users" in the sense
this cleanup is about — real people with logins.

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-31
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

KEEP_ACTIVE = ("system@cocopan.ph", "svc.pos@cocopan.ph", "regie.gumapal@gmail.com")


def upgrade() -> None:
    op.execute(f"""
        UPDATE core.app_user
        SET is_active = FALSE
        WHERE email NOT IN {KEEP_ACTIVE!r};

        UPDATE core.app_user
        SET role_hint = 'System Administrator'
        WHERE email = 'regie.gumapal@gmail.com' AND role_hint IS NULL;
    """)


def downgrade() -> None:
    op.execute(f"""
        UPDATE core.app_user
        SET is_active = TRUE
        WHERE email NOT IN {KEEP_ACTIVE!r};
    """)
