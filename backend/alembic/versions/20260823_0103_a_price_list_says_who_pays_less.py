"""A price list says who pays less than the product's price, and by how much.

`products.selling_price` is one number for everybody, and
`customers.default_discount_percent` lets a firm put one customer on a blanket
rate. Neither expresses the ordinary arrangement in distribution: this
customer, or everyone on this round, gets a particular rate on a particular
product, from a particular date.

The rows hold **rates off the product's price**, not prices of their own. That
is the decision the shape rests on: a firm revises a product's price once and
every arrangement built on it follows, where a list of absolute prices would
keep charging last year's figure until somebody edited every row.

Scope is two nullable keys rather than a type-and-id pair. `customer_id` names
one shop, `territory_id` names a round, and both NULL is the firm's own
standing list -- so "which lists could apply here" is three equality tests and
the specificity order falls out of which key is filled.

Revision ID: 20260823_0103
Revises: 20260823_0102
Create Date: 2026-08-23
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType
from app.identity.system_seed import ROLE_PERMISSION_CODES

revision: str = "20260823_0103"
down_revision: str | Sequence[str] | None = "20260823_0102"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The codes `app/pricing/api/router.py` enforces. A code that is not seeded
#: has no permission row, so it can be attached to no role, and the endpoint
#: silently becomes platform-admin-only -- which is exactly what happened when
#: this shipped without the insert and every price-list call answered "You do
#: not have permission to perform this action."
_NEW_CODES = ("PRICE_LIST_VIEW", "PRICE_LIST_MANAGE")

_permissions = sa.table(
    "permissions",
    sa.column("id", UUIDType()),
    sa.column("code", sa.String()),
    sa.column("name", sa.String()),
    sa.column("description", sa.Text()),
    sa.column("is_system", sa.Boolean()),
    sa.column("is_active", sa.Boolean()),
    sa.column("is_deleted", sa.Boolean()),
)
_roles = sa.table(
    "roles",
    sa.column("id", UUIDType()),
    sa.column("code", sa.String()),
)
_role_permissions = sa.table(
    "role_permissions",
    sa.column("id", UUIDType()),
    sa.column("role_id", UUIDType()),
    sa.column("permission_id", UUIDType()),
    sa.column("is_deleted", sa.Boolean()),
)


def _display_name(code: str) -> str:
    """Render a permission code as a readable name."""
    return code.replace("_", " ").title()


def _base_columns() -> list[sa.Column[object]]:
    """Return the columns every `BaseEntity` table carries.

    Written out rather than assumed: `20260822_0096` shipped twice without
    `deleted_by` and without the timestamp server defaults, and neither was
    visible to the SQLite unit suite, which builds from ORM metadata.
    """
    return [
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    ]


def _seed_permissions(inspector: sa.Inspector) -> None:
    """Insert the price-list codes and grant them where the seed says.

    Guarded on the identity tables existing: they live only in the platform
    schema, so this is a no-op against a firm store.
    """
    # Identity tables live only in the platform schema.
    if not inspector.has_table("permissions") or not inspector.has_table("roles"):
        return
    bind = op.get_bind()
    existing = {
        code: permission_id
        for permission_id, code in bind.execute(
            sa.select(_permissions.c.id, _permissions.c.code).where(
                _permissions.c.code.in_(_NEW_CODES)
            )
        ).all()
    }
    for code in _NEW_CODES:
        if code in existing:
            continue
        permission_id = uuid4()
        existing[code] = permission_id
        bind.execute(
            _permissions.insert().values(
                id=permission_id,
                code=code,
                name=_display_name(code),
                description="System-defined permission.",
                is_system=True,
                is_active=True,
                is_deleted=False,
            )
        )

    role_ids = {
        code: role_id
        for role_id, code in bind.execute(sa.select(_roles.c.id, _roles.c.code)).all()
    }
    granted = {
        (role_id, permission_id)
        for role_id, permission_id in bind.execute(
            sa.select(
                _role_permissions.c.role_id, _role_permissions.c.permission_id
            ).where(_role_permissions.c.is_deleted.is_(False))
        ).all()
    }
    for role_code, permission_codes in ROLE_PERMISSION_CODES.items():
        role_id = role_ids.get(role_code)
        if role_id is None:
            continue
        for code in _NEW_CODES:
            if code not in permission_codes:
                continue
            permission_id = existing[code]
            if (role_id, permission_id) in granted:
                continue
            bind.execute(
                _role_permissions.insert().values(
                    id=uuid4(),
                    role_id=role_id,
                    permission_id=permission_id,
                    is_deleted=False,
                )
            )


def upgrade() -> None:
    """Create the price lists, their rows, and seed the permission codes."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # Firm-owned, so absent from the platform schema entirely; and firm stores
    # are partly built by `Base.metadata.create_all`, so a table can exist even
    # where `alembic_version` reads older.
    _seed_permissions(inspector)
    if not inspector.has_table("customers"):
        return

    if not inspector.has_table("price_lists"):
        op.create_table(
            "price_lists",
            *_base_columns(),
            sa.Column("firm_id", sa.Uuid(), nullable=False),
            sa.Column("code", sa.String(length=50), nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("customer_id", sa.Uuid(), nullable=True),
            sa.Column("territory_id", sa.Uuid(), nullable=True),
            sa.Column("effective_from", sa.Date(), nullable=False),
            sa.Column("effective_to", sa.Date(), nullable=True),
            sa.Column(
                "status", sa.String(length=30), nullable=False, server_default="ACTIVE"
            ),
            sa.ForeignKeyConstraint(
                ["customer_id"],
                ["customers.id"],
                name="FK_price_lists_customer_id",
                ondelete="RESTRICT",
            ),
            sa.UniqueConstraint("firm_id", "code", name="UQ_price_lists_firm_code"),
        )
        op.create_index(
            "IX_price_lists_firm_status", "price_lists", ["firm_id", "status"]
        )
        op.create_index(
            "IX_price_lists_customer", "price_lists", ["firm_id", "customer_id"]
        )
        op.create_index(
            "IX_price_lists_territory", "price_lists", ["firm_id", "territory_id"]
        )
        # The territory key is declared only where the table is there to point
        # at -- the guarded cross-schema pattern `20260809_0042` established.
        if inspector.has_table("sales_territories"):
            op.create_foreign_key(
                "FK_price_lists_territory_id",
                "price_lists",
                "sales_territories",
                ["territory_id"],
                ["id"],
                ondelete="RESTRICT",
            )

    if not inspector.has_table("price_list_items"):
        op.create_table(
            "price_list_items",
            *_base_columns(),
            sa.Column("price_list_id", sa.Uuid(), nullable=False),
            sa.Column("firm_id", sa.Uuid(), nullable=False),
            sa.Column("product_id", sa.Uuid(), nullable=False),
            sa.Column(
                "discount_percent",
                sa.Numeric(precision=9, scale=4),
                nullable=False,
                server_default="0",
            ),
            sa.ForeignKeyConstraint(
                ["price_list_id"],
                ["price_lists.id"],
                name="FK_price_list_items_price_list_id",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["product_id"],
                ["products.id"],
                name="FK_price_list_items_product_id",
                ondelete="RESTRICT",
            ),
            sa.UniqueConstraint(
                "price_list_id", "product_id", name="UQ_price_list_items_list_product"
            ),
        )
        op.create_index(
            "IX_price_list_items_list", "price_list_items", ["price_list_id"]
        )
        op.create_index(
            "IX_price_list_items_product", "price_list_items", ["firm_id", "product_id"]
        )


def downgrade() -> None:
    """Drop them, rows first."""
    inspector = sa.inspect(op.get_bind())
    for table in ("price_list_items", "price_lists"):
        if inspector.has_table(table):
            op.drop_table(table)
