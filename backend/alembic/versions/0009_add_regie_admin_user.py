"""add the developer's own SYS_ADMIN account

db/seed/002_client_data.sql's users are all placeholders standing in for
real Cocopan positions (SPEC §16 open item #12: org chart unconfirmed).
regie.gumapal@gmail.com is different — a real person's personal admin
login for building/managing this system, not a role placeholder — so it's
added here rather than folded into that seed file.

SYS_ADMIN already holds every permission (db/seed/002_client_data.sql:
`INSERT INTO role_permission SELECT 'SYS_ADMIN', permission_code FROM
permission`), so granting that one role satisfies "ALL permissions"
without a special case. Scope is ALL, matching the existing admin
accounts (it.admin@cocopan.ph, from migration 0005).

password_hash is left NULL here, same as every other seeded user — run
`python -m scripts.set_dev_passwords` after this migration to set the
shared local-dev password (that script targets every is_service=FALSE
user, so this account is picked up automatically, no special-casing
needed).

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-31
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMAIL = "regie.gumapal@gmail.com"


def upgrade() -> None:
    op.execute(f"""
        INSERT INTO core.app_user (email, full_name, is_active, is_service)
        VALUES ('{EMAIL}', 'Regie Gumapal', TRUE, FALSE)
        ON CONFLICT DO NOTHING;

        INSERT INTO core.user_role (user_id, role_code, granted_by)
        SELECT u.user_id, 'SYS_ADMIN', u.user_id  -- self-granted: this is the account's own bootstrap
        FROM core.app_user u
        WHERE u.email = '{EMAIL}'
        ON CONFLICT DO NOTHING;

        INSERT INTO core.user_scope (user_id, scope_type, scope_value)
        SELECT u.user_id, 'ALL', '*'
        FROM core.app_user u
        WHERE u.email = '{EMAIL}'
        ON CONFLICT DO NOTHING;
    """)


def downgrade() -> None:
    op.execute(f"""
        DELETE FROM core.user_scope
        WHERE user_id = (SELECT user_id FROM core.app_user WHERE email = '{EMAIL}');

        DELETE FROM core.user_role
        WHERE user_id = (SELECT user_id FROM core.app_user WHERE email = '{EMAIL}');

        DELETE FROM core.app_user WHERE email = '{EMAIL}';
    """)
