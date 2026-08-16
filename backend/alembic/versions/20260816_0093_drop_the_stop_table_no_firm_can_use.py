"""Drop the beat-plan stop table no firm can use.

``sales_beat_plan_stops`` names a **sub-territory** as a stop, which only works
when the hierarchy carries a level below the route to act as a day bucket.
Every firm here runs ``Region > Territory > Route``, so a plan's territory is
already the leaf and its stop list has nothing to point at.

``20260816_0090`` added ``sales_beat_plan_customer_stops`` beside it, which
names outlets directly and is what the call list resolves. This removes the
one that cannot work, so nobody models against it next.

Safe to drop rather than deprecate: the table is empty in every store, no
endpoint ever wrote it, and neither seeder mentions it. ``downgrade`` recreates
it unchanged.

Firm-owned table, so run ``scripts/migrate_all_stores.py``.

Revision ID: 20260816_0093
Revises: 20260816_0092
Create Date: 2026-08-16
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260816_0093"
down_revision: str | Sequence[str] | None = "20260816_0092"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "sales_beat_plan_stops"


def upgrade() -> None:
    """Drop the territory-level beat plan stop table."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        return
    # Refuse to drop a table somebody has started using, rather than take rows
    # with it. Empty in every store when this was written, and this keeps that
    # true for a store nobody has looked at.
    remaining = bind.execute(sa.text(f"SELECT COUNT(*) FROM {_TABLE}")).scalar()
    if int(remaining or 0) > 0:
        raise RuntimeError(
            f"{_TABLE} holds {remaining} row(s); migrate them to "
            "sales_beat_plan_customer_stops before dropping it."
        )
    op.drop_table(_TABLE)


def downgrade() -> None:
    """Recreate the territory-level beat plan stop table."""
    bind = op.get_bind()
    if sa.inspect(bind).has_table(_TABLE):
        return
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("beat_plan_id", sa.Uuid(), nullable=False),
        sa.Column("territory_id", sa.Uuid(), nullable=False),
        sa.Column("stop_order", sa.Integer(), nullable=False),
        sa.Column("planned_duration_minutes", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["beat_plan_id"],
            ["sales_beat_plans.id"],
            name="FK_sales_beat_plan_stops_beat_plan_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["territory_id"],
            ["sales_territories.id"],
            name="FK_sales_beat_plan_stops_territory_id",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "beat_plan_id", "stop_order", name="UQ_sales_beat_plan_stops_plan_order"
        ),
        sa.UniqueConstraint(
            "beat_plan_id",
            "territory_id",
            name="UQ_sales_beat_plan_stops_plan_territory",
        ),
    )
