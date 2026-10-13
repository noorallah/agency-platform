"""A supplier's GST number follows the customers' rule (backlog 136, row F5).

* ``vendors.gstin_from_parent``: the branch's GST number is a copy of its
  main office's, written by the server.
* ``UQ_vendors_firm_gstin_own_active`` replaces
  ``UQ_vendors_firm_gstin_active``: a GST number typed on a supplier is on one
  live supplier of the firm; the copies, and a blank, are left out. The old
  key held every live row, so a branch could not hold its main office's
  number at all.

**No number on any row changes.** A branch entered with no number before this
revision stays blank and stays its own: nothing says it meant its main
office's, and writing one onto it would change the tax on its next bill. It
takes the number the next time it is saved with the box left blank.

The old key was stricter than the new one, so the new one builds wherever the
old one stood. A store that somehow lacks the old key may hold a number twice:
there the later rows are put under the oldest as branches taking its number,
as ``20261013_0365`` did for customers, and a row that cannot be (it has
branches of its own, or sits under another main office) is named and the key
is left unbuilt for that store rather than the migration failing; the service
check refuses the next duplicate either way.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: the column and
each index are touched only where ``vendors`` exists and needs it, because a
firm store is partly built by ``Base.metadata.create_all``.

Revision ID: 20261013_0372
Revises: 20261013_0371
Create Date: 2026-10-13

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261013_0372"
down_revision: str | Sequence[str] | None = "20261013_0371"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "vendors"
_PARENT = "parent_vendor_id"
_MARK = "gstin_from_parent"
_OLD_KEY = "UQ_vendors_firm_gstin_active"
_KEY = "UQ_vendors_firm_gstin_own_active"
#: A number a supplier holds as its own: what the key allows once per firm.
_OWN = (
    "gstin IS NOT NULL AND gstin <> '' "
    "AND gstin_from_parent = false AND is_deleted = false"
)

_vendors = sa.table(
    _TABLE,
    sa.column("id", UUIDType()),
    sa.column("firm_id", UUIDType()),
    sa.column("code", sa.String()),
    sa.column("gstin", sa.String()),
    sa.column(_PARENT, UUIDType()),
    sa.column(_MARK, sa.Boolean()),
    sa.column("is_deleted", sa.Boolean()),
    sa.column("created_at", sa.DateTime(timezone=True)),
)


def _gather_companies(bind: sa.engine.Connection) -> bool:
    """Put suppliers sharing a GST number under the oldest; say if all fit."""
    rows = bind.execute(
        sa.select(
            _vendors.c.id,
            _vendors.c.firm_id,
            _vendors.c.gstin,
            _vendors.c.code,
            _vendors.c[_PARENT],
        )
        .where(
            _vendors.c.is_deleted.is_(False),
            _vendors.c.gstin.is_not(None),
            _vendors.c.gstin != "",
            _vendors.c[_MARK].is_(False),
        )
        .order_by(
            _vendors.c.firm_id,
            _vendors.c.gstin,
            # A main office before its branches, then the oldest.
            sa.case((_vendors.c[_PARENT].is_(None), 0), else_=1),
            _vendors.c.created_at,
            _vendors.c.code,
        )
    ).all()
    main_offices = {
        parent_id
        for (parent_id,) in bind.execute(
            sa.select(_vendors.c[_PARENT]).where(
                _vendors.c[_PARENT].is_not(None), _vendors.c.is_deleted.is_(False)
            )
        )
    }
    holders: dict[tuple[object, str], tuple[object, object]] = {}
    clean = True
    for vendor_id, firm_id, gstin, code, parent_id in rows:
        holder_id, holder_parent = holders.setdefault(
            (firm_id, gstin), (vendor_id, parent_id)
        )
        if holder_id == vendor_id:
            continue
        fits = (
            holder_parent is None
            and vendor_id not in main_offices
            and parent_id in (None, holder_id)
        )
        if not fits:
            clean = False
            # A migration that cannot settle a master says so by name.
            print(
                f"  supplier {code}: shares GST number {gstin} with another "
                "supplier and could not be made its branch; the key is not "
                "built for this store"
            )
            continue
        bind.execute(
            _vendors.update()
            .where(_vendors.c.id == vendor_id)
            .values({_PARENT: holder_id, _MARK: True})
        )
        print(
            f"  supplier {code}: made a branch of the holder of GST number " f"{gstin}"
        )
    return clean


def upgrade() -> None:
    """Add the marker, then swap the key for one that leaves the copies out."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
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
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes(_TABLE)}
    if _KEY not in indexes:
        # With the old key in place no number can be held twice.
        buildable = _OLD_KEY in indexes or _gather_companies(bind)
        if buildable:
            op.create_index(
                _KEY,
                _TABLE,
                ["firm_id", "gstin"],
                unique=True,
                postgresql_where=sa.text(_OWN),
                sqlite_where=sa.text(_OWN),
            )
    if _OLD_KEY in indexes:
        op.drop_index(_OLD_KEY, table_name=_TABLE)


def downgrade() -> None:
    """Put the old key back where no copy stands in its way; drop the marker."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    indexes = {index["name"] for index in inspector.get_indexes(_TABLE)}
    if _KEY in indexes:
        op.drop_index(_KEY, table_name=_TABLE)
    if _MARK in columns:
        # A copy is the main office's number, not the branch's: give it back.
        bind.execute(
            _vendors.update().where(_vendors.c[_MARK].is_(True)).values(gstin=None)
        )
        op.drop_column(_TABLE, _MARK)
    if _OLD_KEY not in indexes:
        op.create_index(
            _OLD_KEY,
            _TABLE,
            ["firm_id", "gstin"],
            unique=True,
            postgresql_where=sa.text("is_deleted = false"),
            sqlite_where=sa.text("is_deleted = false"),
        )
