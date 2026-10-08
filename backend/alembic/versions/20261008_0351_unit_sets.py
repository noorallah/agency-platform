"""Unit sets, and the end of the two things they replace.

Backlog 89, step 3. A unit set is a named template -- *Strip, box of 10* --
that fills a new product's units and its pack size in one choice. It is
copied onto the product, never linked.

* ``unit_sets``: the units and the purchase-to-stock factor. A row without
  ``firm_id`` is the shared catalogue; a row with one is that firm's own.
  One name per firm among live rows, and one among the shared live rows.
* ``unit_set_goods_types``: the goods types a set suits, one row per pair.
  It only orders the product form's picker; a set tied to none is offered
  to every product.
* ``products.unit_set_id``: the set a product's units were copied from, for
  reference. No existing product is given one.

Seeds, each only where missing: the eight shared unit sets, named here
rather than read from ``app/uom/unit_set_seed.py`` so a replay next year
writes these eight and not whatever the seed says then.

Dropped, after what is worth keeping has been moved:

* ``business_profile_uom_defaults``, which pre-filled every new product's
  units from the firm's profile without anyone choosing. A firm's own row
  becomes that firm's unit set *Firm default units*, tied to no goods type so
  every product is offered it. The profile-wide rows are the seed's and are
  covered by the shared sets.
* ``uom_industry_templates``, a catalogue of JSON nothing ever applied.

Firm-owned: run ``scripts/migrate_all_stores.py``. A store with no
``products`` -- the platform store once pruned -- only loses the two old
tables if it still has them. Idempotent.

Revision ID: 20261008_0351
Revises: 20261008_0350
Create Date: 2026-10-08

"""

from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID, uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261008_0351"
down_revision: str | Sequence[str] | None = "20261008_0350"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SETS = "unit_sets"
_TIES = "unit_set_goods_types"
_OLD_DEFAULTS = "business_profile_uom_defaults"
_OLD_TEMPLATES = "uom_industry_templates"
_FIRM_DEFAULT_NAME = "Firm default units"

_OPTIONAL_SLOTS = (
    "inventory_uom_id",
    "purchase_uom_id",
    "sales_uom_id",
    "minimum_sales_uom_id",
    "default_receiving_uom_id",
    "default_dispatch_uom_id",
)

#: id, name, stock unit, purchase unit, factor, decimals, goods types.
_SHARED: tuple[tuple[str, str, str, str, str | None, bool, tuple[str, ...]], ...] = (
    ("01", "Strip, box of 10", "STRIP", "BOX", "10", False, ("MEDICINE",)),
    ("02", "Strip, box of 15", "STRIP", "BOX", "15", False, ("MEDICINE",)),
    (
        "03",
        "Bottle, carton of 24",
        "BOTTLE",
        "CARTON",
        "24",
        False,
        ("MEDICINE", "FOOD", "COSMETICS"),
    ),
    ("04", "Tube, box of 20", "TUBE", "BOX", "20", False, ("MEDICINE", "COSMETICS")),
    ("05", "Pack, carton of 12", "PACK", "CARTON", "12", False, ("FOOD",)),
    ("06", "Litre, loose", "L", "L", None, True, ("PAINT",)),
    ("07", "Piece, loose", "PIECE", "PIECE", None, False, ()),
    ("08", "Unit, box of 10", "UNIT", "BOX", "10", False, ()),
)

_sets = sa.table(
    _SETS,
    sa.column("id", UUIDType()),
    sa.column("firm_id", UUIDType()),
    sa.column("name", sa.String()),
    sa.column("description", sa.Text()),
    sa.column("base_uom_id", UUIDType()),
    *(sa.column(name, UUIDType()) for name in _OPTIONAL_SLOTS),
    sa.column("allow_decimal", sa.Boolean()),
    sa.column("conversion_factor", sa.Numeric(24, 10)),
    sa.column("is_deleted", sa.Boolean()),
)
_ties = sa.table(
    _TIES,
    sa.column("id", UUIDType()),
    sa.column("unit_set_id", UUIDType()),
    sa.column("goods_type_id", UUIDType()),
)
_uoms = sa.table(
    "uoms",
    sa.column("id", UUIDType()),
    sa.column("code", sa.String()),
    sa.column("is_deleted", sa.Boolean()),
)
_types = sa.table(
    "goods_types",
    sa.column("id", UUIDType()),
    sa.column("firm_id", UUIDType()),
    sa.column("code", sa.String()),
    sa.column("is_deleted", sa.Boolean()),
)
_old_defaults = sa.table(
    _OLD_DEFAULTS,
    sa.column("firm_id", UUIDType()),
    sa.column("base_uom_id", UUIDType()),
    sa.column("inventory_uom_id", UUIDType()),
    sa.column("purchase_uom_id", UUIDType()),
    sa.column("sales_uom_id", UUIDType()),
    sa.column("allow_decimal", sa.Boolean()),
    sa.column("is_deleted", sa.Boolean()),
)


def _entity_columns() -> list[sa.Column[object]]:
    """Return the columns every entity table carries, with their defaults."""
    return [
        sa.Column("id", UUIDType(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", UUIDType(), nullable=True),
        sa.Column("created_by", UUIDType(), nullable=True),
        sa.Column("updated_by", UUIDType(), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
    ]


def _create_sets() -> None:
    """Create ``unit_sets`` with its two name keys."""
    op.create_table(
        _SETS,
        *_entity_columns(),
        sa.Column("firm_id", UUIDType(), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("base_uom_id", UUIDType(), nullable=False),
        *(sa.Column(name, UUIDType(), nullable=True) for name in _OPTIONAL_SLOTS),
        sa.Column(
            "allow_decimal",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("conversion_factor", sa.Numeric(24, 10), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="PK_unit_sets"),
        *(
            sa.ForeignKeyConstraint(
                [name], ["uoms.id"], name=f"FK_unit_sets_{name}", ondelete="RESTRICT"
            )
            for name in ("base_uom_id", *_OPTIONAL_SLOTS)
        ),
    )
    op.create_index("IX_unit_sets_firm_id", _SETS, ["firm_id"])
    op.create_index(
        "UQ_unit_sets_firm_name_active",
        _SETS,
        ["firm_id", "name"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false AND firm_id IS NOT NULL"),
    )
    op.create_index(
        "UQ_unit_sets_shared_name_active",
        _SETS,
        ["name"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false AND firm_id IS NULL"),
    )


def _create_ties() -> None:
    """Create ``unit_set_goods_types``, one row per pair."""
    op.create_table(
        _TIES,
        *_entity_columns(),
        sa.Column("unit_set_id", UUIDType(), nullable=False),
        sa.Column("goods_type_id", UUIDType(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="PK_unit_set_goods_types"),
        sa.ForeignKeyConstraint(
            ["unit_set_id"],
            ["unit_sets.id"],
            name="FK_unit_set_goods_types_unit_set_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["goods_type_id"],
            ["goods_types.id"],
            name="FK_unit_set_goods_types_goods_type_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "unit_set_id", "goods_type_id", name="UQ_unit_set_goods_types_pair"
        ),
    )
    op.create_index("IX_unit_set_goods_types_goods_type_id", _TIES, ["goods_type_id"])


def _add_product_column() -> None:
    """Add ``products.unit_set_id`` and its key, if missing."""
    inspector = sa.inspect(op.get_bind())
    if "unit_set_id" not in {c["name"] for c in inspector.get_columns("products")}:
        op.add_column("products", sa.Column("unit_set_id", UUIDType(), nullable=True))
    key = "FK_products_unit_set_id"
    if key not in {fk["name"] for fk in inspector.get_foreign_keys("products")}:
        op.create_foreign_key(
            key, "products", _SETS, ["unit_set_id"], ["id"], ondelete="SET NULL"
        )


def _seed_shared() -> None:
    """Insert the shared unit sets that are missing, with their goods types."""
    bind = op.get_bind()
    # Any row, deleted or not, holds its id; only a live one holds its name.
    held_ids = set(
        bind.execute(sa.select(_sets.c.id).where(_sets.c.firm_id.is_(None))).scalars()
    )
    held_names = set(
        bind.execute(
            sa.select(_sets.c.name).where(
                _sets.c.firm_id.is_(None), _sets.c.is_deleted.is_(False)
            )
        ).scalars()
    )
    units = {
        code: unit_id
        for code, unit_id in bind.execute(
            sa.select(_uoms.c.code, _uoms.c.id).where(_uoms.c.is_deleted.is_(False))
        ).all()
    }
    types = {
        code: type_id
        for code, type_id in bind.execute(
            sa.select(_types.c.code, _types.c.id).where(
                _types.c.firm_id.is_(None), _types.c.is_deleted.is_(False)
            )
        ).all()
    }
    for suffix, name, stock, purchase, factor, decimals, goods_types in _SHARED:
        set_id = UUID(f"8a000000-0000-0000-0000-0000000000{suffix}")
        if set_id in held_ids or name in held_names:
            continue
        if stock not in units or purchase not in units:
            continue
        bind.execute(
            _sets.insert().values(
                id=set_id,
                firm_id=None,
                name=name,
                base_uom_id=units[stock],
                inventory_uom_id=units[stock],
                purchase_uom_id=units[purchase],
                sales_uom_id=units[stock],
                allow_decimal=decimals,
                conversion_factor=None if factor is None else Decimal(factor),
            )
        )
        for code in goods_types:
            if code in types:
                bind.execute(
                    _ties.insert().values(
                        id=uuid4(), unit_set_id=set_id, goods_type_id=types[code]
                    )
                )


def _keep_firm_defaults() -> None:
    """Turn each firm's own default units into that firm's unit set."""
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(_OLD_DEFAULTS):
        return
    # Any row of that name, deleted or not: a firm that removed the set is
    # not handed it again by a replay.
    holding = set(
        bind.execute(
            sa.select(_sets.c.firm_id).where(_sets.c.name == _FIRM_DEFAULT_NAME)
        ).scalars()
    )
    rows = bind.execute(
        sa.select(
            _old_defaults.c.firm_id,
            _old_defaults.c.base_uom_id,
            _old_defaults.c.inventory_uom_id,
            _old_defaults.c.purchase_uom_id,
            _old_defaults.c.sales_uom_id,
            _old_defaults.c.allow_decimal,
        ).where(
            _old_defaults.c.firm_id.is_not(None),
            _old_defaults.c.is_deleted.is_(False),
        )
    ).all()
    for firm_id, base, inventory, purchase, sales, decimals in rows:
        stock = base or inventory
        if firm_id in holding or stock is None:
            continue
        holding.add(firm_id)
        bind.execute(
            _sets.insert().values(
                id=uuid4(),
                firm_id=firm_id,
                name=_FIRM_DEFAULT_NAME,
                description="The units this firm's new products used to start with.",
                base_uom_id=stock,
                inventory_uom_id=inventory,
                purchase_uom_id=purchase,
                sales_uom_id=sales,
                allow_decimal=bool(decimals),
            )
        )


def upgrade() -> None:
    """Build unit sets where the store holds products; drop what they replace."""
    inspector = sa.inspect(op.get_bind())
    if all(inspector.has_table(name) for name in ("products", "uoms", "goods_types")):
        if not inspector.has_table(_SETS):
            _create_sets()
        if not inspector.has_table(_TIES):
            _create_ties()
        _add_product_column()
        _seed_shared()
        _keep_firm_defaults()
    for table in (_OLD_DEFAULTS, _OLD_TEMPLATES):
        if sa.inspect(op.get_bind()).has_table(table):
            op.drop_table(table)


def _recreate_old_tables() -> None:
    """Put the two dropped tables back, empty."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_OLD_TEMPLATES):
        op.create_table(
            _OLD_TEMPLATES,
            *_entity_columns(),
            sa.Column("code", sa.String(length=60), nullable=False),
            sa.Column("name", sa.String(length=140), nullable=False),
            sa.Column("industry_type", sa.String(length=60), nullable=False),
            sa.Column("template_payload", sa.JSON(), nullable=False),
            sa.Column(
                "status",
                sa.String(length=20),
                server_default="ACTIVE",
                nullable=False,
            ),
            sa.Column(
                "is_system",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id", name="PK_uom_industry_templates"),
            sa.UniqueConstraint("code", name="UQ_uom_industry_templates_code"),
        )
    if inspector.has_table(_OLD_DEFAULTS) or not inspector.has_table("uoms"):
        return
    slots = ("base", "inventory", "purchase", "sales")
    op.create_table(
        _OLD_DEFAULTS,
        *_entity_columns(),
        sa.Column("firm_id", UUIDType(), nullable=True),
        sa.Column("business_profile_id", UUIDType(), nullable=False),
        *(sa.Column(f"{slot}_uom_id", UUIDType(), nullable=True) for slot in slots),
        sa.Column(
            "allow_fraction",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "allow_decimal",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="PK_business_profile_uom_defaults"),
        sa.UniqueConstraint(
            "firm_id",
            "business_profile_id",
            name="UQ_business_profile_uom_defaults_firm_profile",
        ),
        *(
            sa.ForeignKeyConstraint(
                [f"{slot}_uom_id"],
                ["uoms.id"],
                name=f"FK_business_profile_uom_defaults_{slot}_uoms",
                ondelete="RESTRICT",
            )
            for slot in slots
        ),
    )


def downgrade() -> None:
    """Take unit sets out again and put the two old tables back, empty."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("products") and "unit_set_id" in {
        c["name"] for c in inspector.get_columns("products")
    }:
        key = "FK_products_unit_set_id"
        if key in {fk["name"] for fk in inspector.get_foreign_keys("products")}:
            op.drop_constraint(key, "products", type_="foreignkey")
        op.drop_column("products", "unit_set_id")
    for table in (_TIES, _SETS):
        if inspector.has_table(table):
            op.drop_table(table)
    _recreate_old_tables()
