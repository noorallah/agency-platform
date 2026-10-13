"""A parent buyer with shops; a GST number held once (backlog 125, row M7).

* ``customers.parent_customer_id``: the buyer a customer is a shop of.
* ``customers.gst_number_from_parent``: the shop's GST number is a copy of
  its parent's, written by the server.
* ``UQ_customers_firm_gst_number_own_active``: a GST number typed on a
  customer is on one live customer of the firm; the copies are left out.

**Customers that already share a GST number are made one family**, because the
key cannot be built over them and a GST number belongs to one registration in
one state: of each group of live customers of a firm holding the same number,
the oldest (then the lowest code) stays its holder and becomes the parent, and
the rest become its shops, marked as taking the number from it. No number on
any row changes, so every bill is taxed as it was. A customer that is already
a shop, and the walk-in customer, are left alone. Replayed, there is no group
left to find.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: each column,
the foreign key and each index is added only where ``customers`` exists and
lacks it, because a firm store is partly built by ``Base.metadata.create_all``.

Revision ID: 20261013_0365
Revises: 20261013_0364
Create Date: 2026-10-13

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261013_0365"
down_revision: str | Sequence[str] | None = "20261013_0364"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "customers"
_PARENT = "parent_customer_id"
_MARK = "gst_number_from_parent"
_FK = "FK_customers_parent_customer_id"
_KEY = "UQ_customers_firm_gst_number_own_active"
_LOOKUP = "IX_customers_parent_customer_id"
#: A number a customer holds as its own: what the key allows once per firm.
_OWN = (
    "gst_number IS NOT NULL AND gst_number <> '' "
    "AND gst_number_from_parent = false AND is_deleted = false"
)

_customers = sa.table(
    _TABLE,
    sa.column("id", UUIDType()),
    sa.column("firm_id", UUIDType()),
    sa.column("code", sa.String()),
    sa.column("gst_number", sa.String()),
    sa.column(_PARENT, UUIDType()),
    sa.column(_MARK, sa.Boolean()),
    sa.column("is_cash_sale", sa.Boolean()),
    sa.column("is_deleted", sa.Boolean()),
    sa.column("created_at", sa.DateTime(timezone=True)),
)


def _gather_families(bind: sa.engine.Connection) -> None:
    """Put the customers sharing a GST number under the oldest of them."""
    rows = bind.execute(
        sa.select(
            _customers.c.id,
            _customers.c.firm_id,
            _customers.c.gst_number,
            _customers.c.code,
        )
        .where(
            _customers.c.is_deleted.is_(False),
            _customers.c.is_cash_sale.is_(False),
            _customers.c.gst_number.is_not(None),
            _customers.c.gst_number != "",
            _customers.c[_MARK].is_(False),
            _customers.c[_PARENT].is_(None),
        )
        .order_by(
            _customers.c.firm_id,
            _customers.c.gst_number,
            _customers.c.created_at,
            _customers.c.code,
        )
    ).all()
    holders: dict[tuple[object, str], object] = {}
    for customer_id, firm_id, gst_number, code in rows:
        key = (firm_id, gst_number)
        holder = holders.setdefault(key, customer_id)
        if holder == customer_id:
            continue
        bind.execute(
            _customers.update()
            .where(_customers.c.id == customer_id)
            .values({_PARENT: holder, _MARK: True})
        )
        # A migration that rewrites a master says what it did.
        print(
            f"  customer {code}: made a shop of the holder of GST number "
            f"{gst_number}"
        )


def upgrade() -> None:
    """Add the link and the marker, gather families, then build the key."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if _PARENT not in columns:
        op.add_column(_TABLE, sa.Column(_PARENT, UUIDType(), nullable=True))
    if _MARK not in columns:
        op.add_column(
            _TABLE,
            sa.Column(
                _MARK,
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
        )
    if _FK not in {key["name"] for key in inspector.get_foreign_keys(_TABLE)}:
        op.create_foreign_key(
            _FK, _TABLE, _TABLE, [_PARENT], ["id"], ondelete="RESTRICT"
        )
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes(_TABLE)}
    if _LOOKUP not in indexes:
        op.create_index(_LOOKUP, _TABLE, [_PARENT])
    if _KEY not in indexes:
        _gather_families(bind)
        op.create_index(
            _KEY,
            _TABLE,
            ["firm_id", "gst_number"],
            unique=True,
            postgresql_where=sa.text(_OWN),
            sqlite_where=sa.text(_OWN),
        )


def downgrade() -> None:
    """Drop the key, the link and the marker; the numbers stay on the rows."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    indexes = {index["name"] for index in inspector.get_indexes(_TABLE)}
    for name in (_KEY, _LOOKUP):
        if name in indexes:
            op.drop_index(name, table_name=_TABLE)
    if _FK in {key["name"] for key in inspector.get_foreign_keys(_TABLE)}:
        op.drop_constraint(_FK, _TABLE, type_="foreignkey")
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    for name in (_MARK, _PARENT):
        if name in columns:
            op.drop_column(_TABLE, name)
