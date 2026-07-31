"""client data seed

Applies db/seed/002_client_data.sql: the real item master (30 SKUs) and
branch master (121 locations) pulled from the client's forecast workbook,
plus assumed reference data (areas/clusters/routes/geography/calendar),
RBAC (idempotent — already present from 0001, re-inserted here with
ON CONFLICT DO NOTHING so this migration also works standalone), and the
"Client Baseline (as-is)" param_set needed for SPEC §14 AC-1 calibration.

Depends on 0002: several INSERT statements target core.item_price's
location_code/price_status columns added there.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-31
"""
from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

REPO_ROOT = Path(__file__).resolve().parents[3]
SEED_SQL = REPO_ROOT / "db" / "seed" / "002_client_data.sql"


def _strip_outer_transaction(sql: str) -> str:
    lines = [line for line in sql.splitlines() if line.strip() not in ("BEGIN;", "COMMIT;")]
    return "\n".join(lines)


def upgrade() -> None:
    cursor = op.get_bind().connection.cursor()
    cursor.execute(_strip_outer_transaction(SEED_SQL.read_text(encoding="utf-8")))
    cursor.close()


def downgrade() -> None:
    # Additive client data only; no reliable single-statement reversal given
    # how much of it is derived via SELECT ... FROM joins. Roll back via
    # `alembic downgrade 0001` (drops and recreates the whole schema) instead
    # if this needs to be undone.
    pass
