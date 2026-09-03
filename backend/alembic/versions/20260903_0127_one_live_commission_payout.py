"""One live commission payout per person per period.

`_assert_period_is_free` reads and then `accrue` writes, so two requests that
both check before either commits both pass. Driven on WHOLE01 during the
2026-09-03 module review: two interleaved sessions left one salesman holding
two live payouts for one month, which pays the same collections twice and
leaves nothing downstream able to say which was the real one.

Partial, so a CANCELLED accrual holds no claim and a period accrued at the
wrong rate stays correctable. PostgreSQL only, as with `UQ_firms_code_active`
and its siblings -- the service check remains authoritative, and it is also
what covers *overlapping* periods, which no unique key can express.

Revision ID: 20260903_0127
Revises: 20260903_0126
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260903_0127"
down_revision: str | None = "20260903_0126"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX = "UQ_commission_payouts_period_active"
_TABLE = "commission_payouts"


def upgrade() -> None:
    """Add the partial unique index where the table exists."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # Firm-owned: absent from the platform schema, and the firm stores are
    # partly built by `create_all`, so the index may already be there.
    if not inspector.has_table(_TABLE):
        return
    if any(index["name"] == _INDEX for index in inspector.get_indexes(_TABLE)):
        return
    if bind.dialect.name != "postgresql":
        return
    op.create_index(
        _INDEX,
        _TABLE,
        ["firm_id", "salesman_id", "period_start", "period_end"],
        unique=True,
        postgresql_where=sa.text("NOT is_deleted AND status <> 'CANCELLED'"),
    )


def downgrade() -> None:
    """Drop it."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        return
    if any(index["name"] == _INDEX for index in inspector.get_indexes(_TABLE)):
        op.drop_index(_INDEX, table_name=_TABLE)
