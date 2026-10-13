"""A supplier company with branches (backlog 127, row M9).

* ``vendors.parent_vendor_id``: the main office a supplier is a branch of.

One column and nothing else. A branch keeps its own GST number, which
``UQ_vendors_firm_gstin_active`` already holds to one live supplier, so no
number is copied and no key changes. No row is rewritten.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: the column,
the foreign key and the index are each added only where ``vendors`` exists
and lacks it, because a firm store is partly built by
``Base.metadata.create_all``.

Revision ID: 20261013_0366
Revises: 20261013_0365
Create Date: 2026-10-13

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261013_0366"
down_revision: str | Sequence[str] | None = "20261013_0365"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "vendors"
_PARENT = "parent_vendor_id"
_FK = "FK_vendors_parent_vendor_id"
_LOOKUP = "IX_vendors_parent_vendor_id"


def upgrade() -> None:
    """Add the link from a branch to its main office."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if _PARENT not in columns:
        op.add_column(_TABLE, sa.Column(_PARENT, UUIDType(), nullable=True))
    if _FK not in {key["name"] for key in inspector.get_foreign_keys(_TABLE)}:
        op.create_foreign_key(
            _FK, _TABLE, _TABLE, [_PARENT], ["id"], ondelete="RESTRICT"
        )
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes(_TABLE)}
    if _LOOKUP not in indexes:
        op.create_index(_LOOKUP, _TABLE, [_PARENT])


def downgrade() -> None:
    """Drop the link; every supplier stands alone again."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    if _LOOKUP in {index["name"] for index in inspector.get_indexes(_TABLE)}:
        op.drop_index(_LOOKUP, table_name=_TABLE)
    if _FK in {key["name"] for key in inspector.get_foreign_keys(_TABLE)}:
        op.drop_constraint(_FK, _TABLE, type_="foreignkey")
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if _PARENT in columns:
        op.drop_column(_TABLE, _PARENT)
