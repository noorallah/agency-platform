"""Let a beat plan name the outlets it calls.

``sales_beat_plan_stops`` names a *sub-territory*, which only works when the
hierarchy carries a level below the route to act as a day bucket. Every demo
firm runs ``Region > Territory > Route``, so a plan's territory is already the
leaf and its territory stops have nothing to point at -- the table cannot be
used by them at all.

This adds an outlet-level stop beside it rather than changing it, so a route
that splits into several day-beats can say which shops belong to which. It is
additive in the strict sense: a plan that lists no outlet stops falls back to
the customers assigned to its territory in ``visit_sequence`` order, which is
the ordinary case and needs no row here.

Firm-owned table, so it exists in ``firm_shared`` and in every dedicated firm
store and **not** in ``platform``. Run it with
``scripts/migrate_all_stores.py``, never a bare ``alembic upgrade head``.

Revision ID: 20260816_0090
Revises: 20260815_0089
Create Date: 2026-08-16
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260816_0090"
down_revision: str | Sequence[str] | None = "20260815_0089"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "sales_beat_plan_customer_stops"


def upgrade() -> None:
    """Create the outlet-level beat plan stop table."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # The parent tables live only in firm stores, so this migration is a no-op
    # against the platform schema. Checked rather than assumed: firm schemas are
    # partly built by `Base.metadata.create_all` from the sample-data and
    # tenancy-reset scripts, so the table can already exist at an older
    # `alembic_version`.
    if inspector.has_table(_TABLE) or not inspector.has_table("sales_beat_plans"):
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
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("stop_order", sa.Integer(), nullable=False),
        sa.Column("planned_duration_minutes", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        # Named for the referring column, not the referred table: two foreign
        # keys to one target would otherwise collide, which PostgreSQL rejects
        # and `Base.metadata.create_all` relies on.
        sa.ForeignKeyConstraint(
            ["beat_plan_id"],
            ["sales_beat_plans.id"],
            name="FK_sales_beat_plan_customer_stops_beat_plan_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name="FK_sales_beat_plan_customer_stops_customer_id",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "beat_plan_id",
            "stop_order",
            name="UQ_sales_beat_plan_customer_stops_plan_order",
        ),
        sa.UniqueConstraint(
            "beat_plan_id",
            "customer_id",
            name="UQ_sales_beat_plan_customer_stops_plan_customer",
        ),
    )
    op.create_index(
        "IX_sales_beat_plan_customer_stops_beat_plan_id",
        _TABLE,
        ["beat_plan_id"],
    )
    op.create_index(
        "IX_sales_beat_plan_customer_stops_customer_id",
        _TABLE,
        ["customer_id"],
    )


def downgrade() -> None:
    """Drop the outlet-level beat plan stop table."""
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(_TABLE):
        return
    op.drop_index("IX_sales_beat_plan_customer_stops_customer_id", table_name=_TABLE)
    op.drop_index("IX_sales_beat_plan_customer_stops_beat_plan_id", table_name=_TABLE)
    op.drop_table(_TABLE)
