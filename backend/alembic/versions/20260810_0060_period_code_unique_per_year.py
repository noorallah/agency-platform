"""Let a firm hold more than one financial year.

``accounting_periods`` carried two unique constraints that contradicted each
other:

* ``UQ_accounting_periods_year_number`` on ``(financial_year_id,
  period_number)`` -- period 1 exists once **per year**, so periods repeat
  across years, which is what an accounting calendar is;
* ``UQ_accounting_periods_firm_code`` on ``(firm_id, code)`` -- code ``P01``
  exists once **per firm**, ever.

``seed_finance_setup`` writes codes ``P01``..``P12`` for whichever year it is
given, so the second constraint made a firm's second financial year impossible.
Not merely awkward: the insert failed. A firm could never carry a prior year,
which rules out year-end, comparatives and any prior-year report.

The code identifies a period within its year, exactly as the number does, so
this rescopes the constraint to match. Nothing about existing rows changes --
one year's worth of periods satisfies both the old constraint and the new one.

``accounting_periods`` is firm-owned, so this runs in every firm store and not
in ``platform``.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260810_0060"
down_revision: str | Sequence[str] | None = "20260810_0059"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "accounting_periods"
_OLD = "UQ_accounting_periods_firm_code"
_NEW = "UQ_accounting_periods_year_code"


def upgrade() -> None:
    """Rescope the period-code constraint from the firm to the year."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        return
    existing = {
        constraint["name"] for constraint in inspector.get_unique_constraints(_TABLE)
    }
    if _OLD in existing:
        op.drop_constraint(_OLD, _TABLE, type_="unique")
    if _NEW not in existing:
        op.create_unique_constraint(_NEW, _TABLE, ["financial_year_id", "code"])


def downgrade() -> None:
    """Restore the firm-scoped constraint.

    This can fail where a firm has since gained a second financial year, which
    is the whole point of the change. Remove the extra years first.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        return
    existing = {
        constraint["name"] for constraint in inspector.get_unique_constraints(_TABLE)
    }
    if _NEW in existing:
        op.drop_constraint(_NEW, _TABLE, type_="unique")
    if _OLD not in existing:
        op.create_unique_constraint(_OLD, _TABLE, ["firm_id", "code"])
