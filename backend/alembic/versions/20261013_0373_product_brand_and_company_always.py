"""Every product has a brand and every brand a company (backlog 138, row F7).

The owner's rule of 2026-10-13: a product is always filed under a brand, and a
brand always belongs to a company. Both links were optional (backlog 129), and
the services now refuse a blank; this revision settles the rows written
before, so no store is left holding what the forms no longer allow.

Per firm, and only where a row needs it:

* a brand with no company goes under the company **General** (code
  ``GENERAL``), made once;
* a product with no brand row whose brand was typed as text goes under the
  live brand of that name, whatever its case; where the firm keeps none, a
  brand of that name is made under *General*. The brand somebody typed is
  the brand the product keeps; only its spelling follows the brand row;
* a product with no brand at all goes under the brand **Unbranded**, made
  once under *General*, and its text says so -- which is what the product
  list's *Unbranded* filter finds.

**A row that has its parent is never touched**, and no column, key or index
changes: ``products.brand_id`` and ``brands.principal_id`` stay nullable,
because the refusal lives in the services and a firm store is partly built by
``Base.metadata.create_all``. Soft-deleted products and brands are settled
too -- a restore would otherwise bring back a row the form cannot save.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: the second run
finds nothing without its parent and writes nothing. A store without the three
tables (the platform store) is passed over.

Revision ID: 20261013_0373
Revises: 20261013_0372
Create Date: 2026-10-13

"""

from collections.abc import Sequence
from uuid import UUID, uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261013_0373"
down_revision: str | Sequence[str] | None = "20261013_0372"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GENERAL_CODE = "GENERAL"
_GENERAL_NAME = "General"
_UNBRANDED = "Unbranded"


def _entity() -> list[sa.ColumnClause[object]]:
    """Return the columns both masters share, fresh for each table."""
    return [
        sa.column("id", UUIDType()),
        sa.column("firm_id", UUIDType()),
        sa.column("is_active", sa.Boolean()),
        sa.column("is_deleted", sa.Boolean()),
        sa.column("version", sa.Integer()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    ]


_principals = sa.table(
    "principals",
    *_entity(),
    sa.column("code", sa.String()),
    sa.column("name", sa.String()),
)
_brands = sa.table(
    "brands",
    *_entity(),
    sa.column("name", sa.String()),
    sa.column("principal_id", UUIDType()),
)
_products = sa.table(
    "products",
    sa.column("id", UUIDType()),
    sa.column("firm_id", UUIDType()),
    sa.column("brand", sa.String()),
    sa.column("brand_id", UUIDType()),
    sa.column("created_at", sa.DateTime(timezone=True)),
)


def _new_row(firm_id: UUID) -> dict[str, object]:
    """Return what every master row made here starts with."""
    return {
        "id": uuid4(),
        "firm_id": firm_id,
        "is_active": True,
        "is_deleted": False,
        "version": 1,
        "created_at": sa.func.now(),
        "updated_at": sa.func.now(),
    }


class _Firm:
    """One firm's company *General* and its brands by name, made on demand."""

    def __init__(self, bind: sa.engine.Connection, firm_id: UUID) -> None:
        """Read the firm's live brands once, the oldest of a name first."""
        self._bind = bind
        self._firm_id = firm_id
        self._general: UUID | None = None
        self.made: list[str] = []
        self._brands: dict[str, tuple[UUID, str]] = {}
        for brand_id, name in bind.execute(
            sa.select(_brands.c.id, _brands.c.name)
            .where(_brands.c.firm_id == firm_id, _brands.c.is_deleted.is_(False))
            .order_by(_brands.c.created_at, _brands.c.id)
        ):
            self._brands.setdefault(name.strip().lower(), (brand_id, name))

    def general(self) -> UUID:
        """Return the company *General*, by code then by name, else made."""
        if self._general is None:
            live = sa.and_(
                _principals.c.firm_id == self._firm_id,
                _principals.c.is_deleted.is_(False),
            )
            found = self._bind.scalar(
                sa.select(_principals.c.id)
                .where(
                    live,
                    sa.or_(
                        _principals.c.code == _GENERAL_CODE,
                        sa.func.lower(_principals.c.name) == _GENERAL_NAME.lower(),
                    ),
                )
                .order_by(
                    sa.case((_principals.c.code == _GENERAL_CODE, 0), else_=1),
                    _principals.c.created_at,
                    _principals.c.id,
                )
                .limit(1)
            )
            if found is None:
                row = _new_row(self._firm_id)
                self._bind.execute(
                    _principals.insert().values(
                        **row, code=_GENERAL_CODE, name=_GENERAL_NAME
                    )
                )
                found = row["id"]
                self.made.append(f"company {_GENERAL_NAME}")
            assert isinstance(found, UUID)
            self._general = found
        return self._general

    def brand(self, name: str) -> tuple[UUID, str]:
        """Return the live brand of this name and its spelling, else made."""
        key = name.strip().lower()
        if key not in self._brands:
            row = _new_row(self._firm_id)
            # ``brands.name`` is 120 wide, as ``products.brand`` is.
            spelt = name.strip()[:120]
            self._bind.execute(
                _brands.insert().values(**row, name=spelt, principal_id=self.general())
            )
            assert isinstance(row["id"], UUID)
            self._brands[key] = (row["id"], spelt)
            self.made.append(f"brand {spelt}")
        return self._brands[key]


def upgrade() -> None:
    """File every brand under a company and every product under a brand."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not all(
        inspector.has_table(name) for name in ("principals", "brands", "products")
    ):
        return
    loose_brands = dict(
        bind.execute(
            sa.select(_brands.c.firm_id, sa.func.count())
            .where(_brands.c.principal_id.is_(None))
            .group_by(_brands.c.firm_id)
        ).all()
    )
    # Grouped here rather than in SQL: one typed brand in two spellings is one
    # brand, spelt as the oldest product has it.
    loose_products: dict[tuple[UUID, str], tuple[str, list[UUID]]] = {}
    for product_id, firm_id, typed in bind.execute(
        sa.select(_products.c.id, _products.c.firm_id, _products.c.brand)
        .where(_products.c.brand_id.is_(None))
        .order_by(_products.c.firm_id, _products.c.created_at, _products.c.id)
    ):
        spelt = (typed or "").strip()
        loose_products.setdefault((firm_id, spelt.lower()), (spelt, []))[1].append(
            product_id
        )
    firms: dict[UUID, _Firm] = {}
    for firm_id, count in loose_brands.items():
        firm = firms.setdefault(firm_id, _Firm(bind, firm_id))
        bind.execute(
            _brands.update()
            .where(_brands.c.firm_id == firm_id, _brands.c.principal_id.is_(None))
            .values(principal_id=firm.general())
        )
        print(f"  firm {firm_id}: {count} brand(s) put under {_GENERAL_NAME}")
    for (firm_id, _key), (typed, product_ids) in loose_products.items():
        firm = firms.setdefault(firm_id, _Firm(bind, firm_id))
        brand_id, spelt = firm.brand(typed or _UNBRANDED)
        for start in range(0, len(product_ids), 1000):
            bind.execute(
                _products.update()
                .where(
                    _products.c.id.in_(product_ids[start : start + 1000]),
                    _products.c.brand_id.is_(None),
                )
                .values(brand_id=brand_id, brand=spelt)
            )
        print(
            f"  firm {firm_id}: {len(product_ids)} product(s) put under "
            f"brand {spelt}"
        )
    for firm_id, firm in firms.items():
        if firm.made:
            print(f"  firm {firm_id}: made {', '.join(firm.made)}")


def downgrade() -> None:
    """Leave every row where it was put.

    Nothing records which products and brands were filed here rather than by
    a person, and a brand made here may since have been named on a supplier
    or moved to its real company. The columns were never changed, so the
    earlier code reads these rows as it read any other.
    """
