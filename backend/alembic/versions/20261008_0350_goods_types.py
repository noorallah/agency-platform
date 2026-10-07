"""Goods types: the table, the firm's use of one, and the two columns.

Backlog 89, step 1. A product's behaviour is to follow its goods type
(Medicine, Food, Paint, Electronics) rather than the firm's one business
profile, so a firm carrying several lines handles each by its own rules.

* ``goods_types``: the tracking a line of goods starts a product with. A row
  without ``firm_id`` is the shared catalogue; a row with one is that firm's
  own. One code per firm among live rows, and one among the shared live rows.
* ``firm_goods_types``: the types a firm trades in, each with the HSN code
  and tax group a new product of it starts with. A tax group is the firm's
  own code, which is why the defaults sit here and not on a shared row.
* ``product_categories.goods_type_id``: the category carries the type.
* ``products.goods_type_id``: the product stores the one it took, indexed
  with the firm so a report by goods type reads the product row alone.

Null is General on both columns, so no product is rewritten here: every
product that exists today is General until its category is given a type and
it is filed again.

Seeds, each only where missing:

* the five shared goods types, named here rather than read from
  ``app/products/goods_type_seed.py`` so a replay next year writes these
  five and not whatever the seed says then;
* each firm's starting set from the profile it is on today -- PHARMACY
  starts with Medicine, FOOD and RESTAURANT with Food, ELECTRONICS with
  Electronics -- for a firm that holds no row at all.

Nothing is dropped. The profile's own say over batches, expiry and serial
numbers is withdrawn by the later steps of backlog 89.

Firm-owned: run ``scripts/migrate_all_stores.py``. A store with no
``product_categories`` -- the platform store once pruned -- is left alone.
Idempotent.

Revision ID: 20261008_0350
Revises: 20261007_0349
Create Date: 2026-10-08

"""

from collections.abc import Sequence
from uuid import UUID, uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261008_0350"
down_revision: str | Sequence[str] | None = "20261007_0349"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TYPES = "goods_types"
_USES = "firm_goods_types"

#: id, code, name, description, the switches that are on.
_SHARED: tuple[tuple[str, str, str, str, tuple[str, ...]], ...] = (
    (
        "89000000-0000-0000-0000-000000000001",
        "MEDICINE",
        "Medicine",
        "Medicines and healthcare goods: batch and expiry on all.",
        ("track_batch", "track_expiry", "track_manufacturing_date"),
    ),
    (
        "89000000-0000-0000-0000-000000000002",
        "FOOD",
        "Food",
        "Food, grocery and packaged goods with a shelf life.",
        ("track_batch", "track_expiry", "track_manufacturing_date"),
    ),
    (
        "89000000-0000-0000-0000-000000000003",
        "COSMETICS",
        "Cosmetics and personal care",
        "Personal care goods sold by batch with a use-by date.",
        ("track_batch", "track_expiry", "track_manufacturing_date"),
    ),
    (
        "89000000-0000-0000-0000-000000000004",
        "PAINT",
        "Paint",
        "Paints and coatings: a batch for the shade, no expiry.",
        ("track_batch",),
    ),
    (
        "89000000-0000-0000-0000-000000000005",
        "ELECTRONICS",
        "Electronics",
        "Electronic goods sold by serial number under warranty.",
        ("track_serial", "track_warranty"),
    ),
)

_SWITCHES = (
    "track_batch",
    "track_expiry",
    "track_manufacturing_date",
    "track_serial",
    "track_warranty",
)

#: The goods types a firm starts with, by the code of its profile.
_STARTING: dict[str, tuple[str, ...]] = {
    "PHARMACY": ("MEDICINE",),
    "FOOD": ("FOOD",),
    "RESTAURANT": ("FOOD",),
    "ELECTRONICS": ("ELECTRONICS",),
}

_types = sa.table(
    _TYPES,
    sa.column("id", UUIDType()),
    sa.column("firm_id", UUIDType()),
    sa.column("code", sa.String()),
    sa.column("name", sa.String()),
    sa.column("description", sa.Text()),
    *(sa.column(name, sa.Boolean()) for name in _SWITCHES),
    sa.column("is_deleted", sa.Boolean()),
)
_uses = sa.table(
    _USES,
    sa.column("id", UUIDType()),
    sa.column("firm_id", UUIDType()),
    sa.column("goods_type_id", UUIDType()),
)
_firm_profiles = sa.table(
    "firm_business_profiles",
    sa.column("firm_id", UUIDType()),
    sa.column("business_profile_id", UUIDType()),
    sa.column("is_deleted", sa.Boolean()),
)
_profiles = sa.table(
    "business_profiles",
    sa.column("id", UUIDType()),
    sa.column("code", sa.String()),
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


def _create_types() -> None:
    """Create ``goods_types`` with its two code keys."""
    op.create_table(
        _TYPES,
        *_entity_columns(),
        sa.Column("firm_id", UUIDType(), nullable=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        *(
            sa.Column(
                name, sa.Boolean(), server_default=sa.text("false"), nullable=False
            )
            for name in _SWITCHES
        ),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="PK_goods_types"),
    )
    op.create_index("IX_goods_types_firm_id", _TYPES, ["firm_id"])
    op.create_index(
        "UQ_goods_types_firm_code_active",
        _TYPES,
        ["firm_id", "code"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false AND firm_id IS NOT NULL"),
    )
    op.create_index(
        "UQ_goods_types_shared_code_active",
        _TYPES,
        ["code"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false AND firm_id IS NULL"),
    )


def _create_uses() -> None:
    """Create ``firm_goods_types``, one live row per firm and type."""
    op.create_table(
        _USES,
        *_entity_columns(),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column("goods_type_id", UUIDType(), nullable=False),
        sa.Column("default_hsn_sac", sa.String(length=20), nullable=True),
        sa.Column(
            "default_tax_profile_group_code", sa.String(length=50), nullable=True
        ),
        sa.PrimaryKeyConstraint("id", name="PK_firm_goods_types"),
        sa.ForeignKeyConstraint(
            ["goods_type_id"],
            ["goods_types.id"],
            name="FK_firm_goods_types_goods_type_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("IX_firm_goods_types_firm_id", _USES, ["firm_id"])
    op.create_index("IX_firm_goods_types_goods_type_id", _USES, ["goods_type_id"])
    op.create_index(
        "UQ_firm_goods_types_firm_type_active",
        _USES,
        ["firm_id", "goods_type_id"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )


def _add_column(table: str, index: tuple[str, list[str]]) -> None:
    """Add ``goods_type_id`` to a table with its key and index, if missing."""
    inspector = sa.inspect(op.get_bind())
    if "goods_type_id" not in {c["name"] for c in inspector.get_columns(table)}:
        op.add_column(table, sa.Column("goods_type_id", UUIDType(), nullable=True))
    key = f"FK_{table}_goods_type_id"
    if key not in {fk["name"] for fk in inspector.get_foreign_keys(table)}:
        op.create_foreign_key(
            key, table, _TYPES, ["goods_type_id"], ["id"], ondelete="RESTRICT"
        )
    name, columns = index
    if name not in {item["name"] for item in inspector.get_indexes(table)}:
        op.create_index(name, table, columns)


def _seed_shared() -> dict[str, UUID]:
    """Insert the shared goods types that are missing; return ids by code."""
    bind = op.get_bind()
    held = {
        code: goods_type_id
        for goods_type_id, code in bind.execute(
            sa.select(_types.c.id, _types.c.code).where(
                _types.c.firm_id.is_(None), _types.c.is_deleted.is_(False)
            )
        ).all()
    }
    for raw_id, code, name, description, switches in _SHARED:
        if code in held:
            continue
        held[code] = UUID(raw_id)
        bind.execute(
            _types.insert().values(
                id=UUID(raw_id),
                firm_id=None,
                code=code,
                name=name,
                description=description,
                **{switch: switch in switches for switch in _SWITCHES},
            )
        )
    return held


def _seed_starting_sets(shared: dict[str, UUID]) -> None:
    """Give each firm that holds no goods type its profile's starting set."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not (
        inspector.has_table("firm_business_profiles")
        and inspector.has_table("business_profiles")
    ):
        return
    # Any row, deleted or not: a firm that dropped its types keeps none.
    holding = set(bind.execute(sa.select(_uses.c.firm_id)).scalars())
    assigned = bind.execute(
        sa.select(_firm_profiles.c.firm_id, _profiles.c.code)
        .join(_profiles, _profiles.c.id == _firm_profiles.c.business_profile_id)
        .where(_firm_profiles.c.is_deleted.is_(False))
    ).all()
    for firm_id, profile_code in assigned:
        if firm_id in holding:
            continue
        for code in _STARTING.get(profile_code, ()):
            if code in shared:
                bind.execute(
                    _uses.insert().values(
                        id=uuid4(), firm_id=firm_id, goods_type_id=shared[code]
                    )
                )


def upgrade() -> None:
    """Build goods types where the store holds products, and seed them."""
    inspector = sa.inspect(op.get_bind())
    if not (
        inspector.has_table("product_categories") and inspector.has_table("products")
    ):
        return
    if not inspector.has_table(_TYPES):
        _create_types()
    if not inspector.has_table(_USES):
        _create_uses()
    _add_column(
        "product_categories",
        ("IX_product_categories_goods_type_id", ["goods_type_id"]),
    )
    _add_column(
        "products", ("IX_products_firm_goods_type", ["firm_id", "goods_type_id"])
    )
    _seed_starting_sets(_seed_shared())


def downgrade() -> None:
    """Take the two columns and the two tables out again."""
    inspector = sa.inspect(op.get_bind())
    for table, index in (
        ("products", "IX_products_firm_goods_type"),
        ("product_categories", "IX_product_categories_goods_type_id"),
    ):
        if not inspector.has_table(table):
            continue
        if "goods_type_id" not in {c["name"] for c in inspector.get_columns(table)}:
            continue
        if index in {item["name"] for item in inspector.get_indexes(table)}:
            op.drop_index(index, table_name=table)
        key = f"FK_{table}_goods_type_id"
        if key in {fk["name"] for fk in inspector.get_foreign_keys(table)}:
            op.drop_constraint(key, table, type_="foreignkey")
        op.drop_column(table, "goods_type_id")
    for table in (_USES, _TYPES):
        if inspector.has_table(table):
            op.drop_table(table)
