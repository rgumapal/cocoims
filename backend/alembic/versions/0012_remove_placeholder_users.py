"""hard-delete placeholder seed users, keep only the real account

Migration 0011 deactivated these (is_active=FALSE) rather than deleting
them, per CLAUDE.md's general "never delete, deactivate" rule. The user
explicitly asked for actual removal this time, not deactivation — and
unlike branches/items/reason codes, these were never real people with
real activity: they're placeholders standing in for an org chart SPEC §16
open item #12 never confirmed (see migration 0009's docstring). Checked
before writing this: no audit-trail column (created_by, granted_by,
changed_by, submitted_by, approved_by) anywhere in the schema references
any of them — only core.app_user #1 (system) and #16 (regie.gumapal@
gmail.com) ever appear in those columns. So nothing this hard-delete
touches was ever actually attributed to these accounts.

One real reference did exist: core.location.om_user_id (a real FK,
NO ACTION) had five of these placeholders — the OM placeholders — assigned
across all 121 branches. That has to be cleared first or the DELETE fails
outright. This isn't a loss of real data: no actual person currently holds
that assignment (the accounts being deleted were never anyone real), and
SPEC's own seed-file comments already flag OM assignment as placeholder
data pending client confirmation. Every branch's om_user_id goes to NULL
until a real OM is assigned through the Branches screen.

core.user_role and core.user_scope rows for these users are FK CASCADE —
no separate cleanup needed for those.

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-01
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

KEEP = ("system@cocopan.ph", "svc.pos@cocopan.ph", "regie.gumapal@gmail.com")


def upgrade() -> None:
    op.execute(f"""
        UPDATE core.location
        SET om_user_id = NULL
        WHERE om_user_id IN (SELECT user_id FROM core.app_user WHERE email NOT IN {KEEP!r});

        DELETE FROM core.app_user WHERE email NOT IN {KEEP!r};
    """)


def downgrade() -> None:
    # Not reversible: this is a genuine hard delete of seed data (unlike
    # 0011's deactivate), and om_user_id's prior placeholder assignments
    # aren't recoverable from anything else in the schema. Re-running
    # db/seed/002_client_data.sql's user section by hand is the only way
    # back, deliberately not automated here.
    pass
