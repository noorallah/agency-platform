"""A product or a category may need several licences (backlog 152, row P3).

``products.required_licence_type_id`` and
``product_categories.required_licence_type_id`` named one trade licence type.
A medicine can need two, and a new kind of licence later must be an entry and
not a rebuild, so each becomes a list with no fixed size:

* ``product_licence_requirements`` -- one row per licence a product needs.
* ``product_category_licence_requirements`` -- the same for a category.

Every product and category that named a type keeps it, as a list of one, and
the single column is then dropped: nothing reads it any more.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: a table is
created only where missing, a row is copied only where the list does not
already hold that type, and the column is dropped only where it still exists.
The copy is done row by row from Python, with ids made here, so it does not
lean on a database function.

Revision ID: 20261014_0377
Revises: 20261014_0376
Create Date: 2026-10-14

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261014_0377"
down_revision: str | Sequence[str] | None = "20261014_0376"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD = "required_licence_type_id"

#: owner table, link table, the link's column naming its owner.
_LINKS = (
    ("products", "product_licence_requirements", "product_id"),
    (
        "product_categories",
        "product_category_licence_requirements",
        "category_id",
    ),
)


def _create_link(table: str, owner_table: str, owner_column: str) -> None:
    """Create one list table, shaped as the model declares it."""
    op.create_table(
        table,
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
            "is_deleted",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", UUIDType(), nullable=True),
        sa.Column("created_by", UUIDType(), nullable=True),
        sa.Column("updated_by", UUIDType(), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(owner_column, UUIDType(), nullable=False),
        sa.Column("licence_type_id", UUIDType(), nullable=False),
        sa.Column(
            "position", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=f"PK_{table}"),
        sa.ForeignKeyConstraint(
            [owner_column],
            [f"{owner_table}.id"],
            name=f"FK_{table}_{owner_column}",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["licence_type_id"],
            ["trade_licence_types.id"],
            name=f"FK_{table}_licence_type_id",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            owner_column,
            "licence_type_id",
            name=f"UQ_{table}_{owner_column.removesuffix('_id')}_type",
        ),
    )
    op.create_index(f"IX_{table}_{owner_column}", table, [owner_column])
    op.create_index(f"IX_{table}_licence_type_id", table, ["licence_type_id"])


def _copy_single(owner_table: str, table: str, owner_column: str) -> None:
    """Give every owner that named one type a list holding it."""
    bind = op.get_bind()
    link = sa.table(
        table,
        sa.column("id", UUIDType()),
        sa.column(owner_column, UUIDType()),
        sa.column("licence_type_id", UUIDType()),
        sa.column("position", sa.Integer()),
    )
    owner = sa.table(
        owner_table,
        sa.column("id", UUIDType()),
        sa.column(_OLD, UUIDType()),
    )
    held = {
        (owner_id, type_id)
        for owner_id, type_id in bind.execute(
            sa.select(link.c[owner_column], link.c.licence_type_id)
        ).all()
    }
    rows = [
        {
            "id": uuid4(),
            owner_column: owner_id,
            "licence_type_id": type_id,
            "position": 0,
        }
        for owner_id, type_id in bind.execute(
            sa.select(owner.c.id, owner.c[_OLD]).where(owner.c[_OLD].is_not(None))
        ).all()
        if (owner_id, type_id) not in held
    ]
    if rows:
        bind.execute(sa.insert(link), rows)


def upgrade() -> None:
    """Turn the one licence a product or category names into a list."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("trade_licence_types"):
        return
    for owner_table, table, owner_column in _LINKS:
        if not inspector.has_table(owner_table):
            continue
        if not inspector.has_table(table):
            _create_link(table, owner_table, owner_column)
        columns = {column["name"] for column in inspector.get_columns(owner_table)}
        if _OLD not in columns:
            continue
        _copy_single(owner_table, table, owner_column)
        # The key and the index on the column go with it; their names differ
        # between a store built by migration and one built from the models.
        op.drop_column(owner_table, _OLD)


def downgrade() -> None:
    """Put the single column back, holding the first licence of each list."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("trade_licence_types"):
        return
    for owner_table, table, owner_column in _LINKS:
        if not inspector.has_table(owner_table):
            continue
        columns = {column["name"] for column in inspector.get_columns(owner_table)}
        if _OLD not in columns:
            op.add_column(owner_table, sa.Column(_OLD, UUIDType(), nullable=True))
            op.create_foreign_key(
                f"FK_{owner_table}_{_OLD}",
                owner_table,
                "trade_licence_types",
                [_OLD],
                ["id"],
                ondelete="RESTRICT",
            )
            op.create_index(f"IX_{owner_table}_{_OLD}", owner_table, [_OLD])
        if not inspector.has_table(table):
            continue
        link = sa.table(
            table,
            sa.column(owner_column, UUIDType()),
            sa.column("licence_type_id", UUIDType()),
            sa.column("position", sa.Integer()),
            sa.column("is_deleted", sa.Boolean()),
        )
        owner = sa.table(
            owner_table,
            sa.column("id", UUIDType()),
            sa.column(_OLD, UUIDType()),
        )
        first: dict[object, object] = {}
        for owner_id, type_id in bind.execute(
            sa.select(link.c[owner_column], link.c.licence_type_id)
            .where(link.c.is_deleted.is_(False))
            .order_by(link.c.position.desc())
        ).all():
            first[owner_id] = type_id
        for owner_id, type_id in first.items():
            bind.execute(
                sa.update(owner).where(owner.c.id == owner_id).values({_OLD: type_id})
            )
        op.drop_table(table)
