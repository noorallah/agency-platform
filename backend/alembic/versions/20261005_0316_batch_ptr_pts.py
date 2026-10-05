"""Batch-wise PTR / PTS (PG-14, backlog 86 #22, 55 G5).

* ``batches.ptr`` and ``batches.pts``: price to retailer and price to
  stockist, per stock unit before tax, beside the batch's MRP.
* ``goods_receipt_lines.ptr`` and ``.pts``: captured at receipt and handed to
  the batch on completion.
* ``customers.trade_class``: RETAILER, STOCKIST or OTHER; null reads as OTHER.
* The ``BATCH_PTR_PTS`` business feature, implemented, and switched on for
  the PHARMACY, FOOD and WHOLESALE profiles -- each only where missing, so a
  feature an administrator already switched off for a profile stays off.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: each column is
added only where its table exists and lacks it, the feature row only where the
catalogue lacks the code, and a profile mapping only where none exists.

Revision ID: 20261005_0316
Revises: 20261005_0315
Create Date: 2026-10-05

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261005_0316"
down_revision: str | Sequence[str] | None = "20261005_0315"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: (table, column, type) -- every column nullable, so an old row means "none".
_COLUMNS: tuple[tuple[str, str, sa.types.TypeEngine[object]], ...] = (
    ("batches", "ptr", sa.Numeric(18, 2)),
    ("batches", "pts", sa.Numeric(18, 2)),
    ("goods_receipt_lines", "ptr", sa.Numeric(18, 2)),
    ("goods_receipt_lines", "pts", sa.Numeric(18, 2)),
    ("customers", "trade_class", sa.String(20)),
)

_FEATURE = "BATCH_PTR_PTS"
_PROFILES = ("PHARMACY", "FOOD", "WHOLESALE")

_features = sa.table(
    "business_features",
    sa.column("id", UUIDType()),
    sa.column("code", sa.String()),
    sa.column("name", sa.String()),
    sa.column("description", sa.Text()),
    sa.column("category", sa.String()),
    sa.column("default_enabled", sa.Boolean()),
    sa.column("is_active", sa.Boolean()),
    sa.column("is_implemented", sa.Boolean()),
    sa.column("is_deleted", sa.Boolean()),
    sa.column("version", sa.Integer()),
)
_profiles = sa.table(
    "business_profiles",
    sa.column("id", UUIDType()),
    sa.column("code", sa.String()),
    sa.column("is_deleted", sa.Boolean()),
)
_profile_features = sa.table(
    "profile_features",
    sa.column("id", UUIDType()),
    sa.column("business_profile_id", UUIDType()),
    sa.column("feature_id", UUIDType()),
    sa.column("is_enabled", sa.Boolean()),
    sa.column("is_deleted", sa.Boolean()),
)


def _add_columns(inspector: sa.Inspector) -> None:
    """Add each column where its table exists and it does not."""
    for table, name, kind in _COLUMNS:
        if not inspector.has_table(table):
            continue
        present = {column["name"] for column in inspector.get_columns(table)}
        if name not in present:
            op.add_column(table, sa.Column(name, kind, nullable=True))


def _seed_feature(bind: sa.Connection, inspector: sa.Inspector) -> None:
    """Add the feature to the catalogue and to the three profiles, if missing."""
    if not inspector.has_table("business_features"):
        return
    feature_id = bind.execute(
        sa.select(_features.c.id).where(_features.c.code == _FEATURE)
    ).scalar()
    if feature_id is None:
        feature_id = uuid4()
        bind.execute(
            _features.insert().values(
                id=feature_id,
                code=_FEATURE,
                name="Batch PTR / PTS",
                description=(
                    "Price to retailer and price to stockist per batch, "
                    "captured at receipt and charged by the buyer's trade class."
                ),
                category="SALES",
                default_enabled=False,
                is_active=True,
                is_implemented=True,
                is_deleted=False,
                version=1,
            )
        )
    if not inspector.has_table("business_profiles") or not inspector.has_table(
        "profile_features"
    ):
        return
    for profile_id in bind.execute(
        sa.select(_profiles.c.id).where(
            _profiles.c.code.in_(_PROFILES), _profiles.c.is_deleted.is_(False)
        )
    ).scalars():
        mapped = bind.execute(
            sa.select(_profile_features.c.id).where(
                _profile_features.c.business_profile_id == profile_id,
                _profile_features.c.feature_id == feature_id,
            )
        ).first()
        if mapped is not None:
            continue
        bind.execute(
            _profile_features.insert().values(
                id=uuid4(),
                business_profile_id=profile_id,
                feature_id=feature_id,
                is_enabled=True,
                is_deleted=False,
            )
        )


def upgrade() -> None:
    """Add the columns and the feature."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    _add_columns(inspector)
    _seed_feature(bind, inspector)


def downgrade() -> None:
    """Drop the columns; the feature row is left, as other catalogue seeds are.

    Removing a catalogue row would take every profile's mapping with it, and
    a mapping is an administrator's decision this migration did not make.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table, name, _kind in reversed(_COLUMNS):
        if not inspector.has_table(table):
            continue
        present = {column["name"] for column in inspector.get_columns(table)}
        if name in present:
            op.drop_column(table, name)
