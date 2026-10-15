"""Offers chosen on the bill line: the tables and columns (L7, step 1).

Row L7 of ``docs/CUSTOMER_BUILD_TASKS.md``, step 1 of
``docs/design/OFFERS_ON_THE_BILL_LINE_DESIGN.md`` (section 3.9):

* ``sales_order_offers`` and ``sales_quotation_offers``: one row for each
  offer, price list or standing rate applied to, or refused on, a line or the
  whole document. No ``firm_id`` foreign key: ``firms`` lives only in the
  platform schema.
* ``promotions.allow_part_share`` (Boolean, default false): buy N get M free
  given in proportion at every quantity.
* ``offer_choice_made`` (Boolean, default false) on the order and quotation
  lines: a person chose the line's arrangement.
* ``SALES_OFFER_CHOOSE`` seeded and the system roles reconciled, which gives
  it to every role that makes a sales bill. Platform data only.

``promotion_mode`` takes ``ASK``; it is String(20) already, so nothing moves.
Nothing is backfilled and nothing reads the new objects yet, so every firm is
priced exactly as before.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: each table and
column is created only where missing, each table only where the tables its
keys point at are in the same store, and the permission and each grant only
where missing.

Revision ID: 20261015_0390
Revises: 20261015_0389
Create Date: 2026-10-15

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType
from app.identity.system_seed import ROLE_PERMISSION_CODES, SYSTEM_PERMISSION_CODES

revision: str = "20261015_0390"
down_revision: str | Sequence[str] | None = "20261015_0389"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: (table, document column, document table, line column, line table)
_OFFER_TABLES = (
    (
        "sales_order_offers",
        "sales_order_id",
        "sales_orders",
        "sales_order_line_id",
        "sales_order_lines",
    ),
    (
        "sales_quotation_offers",
        "sales_quotation_id",
        "sales_quotations",
        "sales_quotation_line_id",
        "sales_quotation_lines",
    ),
)
_LINE_TABLES = ("sales_order_lines", "sales_quotation_lines")

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
    sa.column("firm_id", UUIDType()),
    sa.column("is_deleted", sa.Boolean()),
)
_role_permissions = sa.table(
    "role_permissions",
    sa.column("id", UUIDType()),
    sa.column("role_id", UUIDType()),
    sa.column("permission_id", UUIDType()),
    sa.column("is_deleted", sa.Boolean()),
)


def _base_columns() -> list[sa.Column]:
    """Return the columns every entity in this repo carries.

    The two timestamps carry `CURRENT_TIMESTAMP`: a hand-written
    `create_table` that omits it builds a NOT NULL column with no default, and
    the first insert fails (`20260903_0114`).
    """
    return [
        sa.Column("id", UUIDType(), primary_key=True, nullable=False),
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
        sa.Column("created_by", UUIDType(), nullable=True),
        sa.Column("updated_by", UUIDType(), nullable=True),
        sa.Column("deleted_by", UUIDType(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("0")),
    ]


def _present(inspector: sa.Inspector, table: str) -> set[str]:
    """Return the names of the columns ``table`` already has."""
    return {column["name"] for column in inspector.get_columns(table)}


def _flag(name: str) -> sa.Column:
    """Return a not-null Boolean column that starts false."""
    return sa.Column(
        name, sa.Boolean(), nullable=False, server_default=sa.text("false")
    )


def _key(table: str, column: str, target: str, ondelete: str) -> sa.ForeignKey:
    """Return a foreign key named on the referring column."""
    return sa.ForeignKey(target, ondelete=ondelete, name=f"FK_{table}_{column}")


def _create_offer_table(
    table: str, document: str, documents: str, line: str, lines: str
) -> None:
    """Create one offer table with its keys and indexes."""
    op.create_table(
        table,
        *_base_columns(),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column(
            document,
            UUIDType(),
            _key(table, document, f"{documents}.id", "CASCADE"),
            nullable=False,
        ),
        sa.Column(
            line, UUIDType(), _key(table, line, f"{lines}.id", "CASCADE"), nullable=True
        ),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column(
            "promotion_id",
            UUIDType(),
            _key(table, "promotion_id", "promotions.id", "RESTRICT"),
            nullable=True,
        ),
        sa.Column("promotion_group_id", UUIDType(), nullable=True),
        sa.Column(
            "price_list_id",
            UUIDType(),
            _key(table, "price_list_id", "price_lists.id", "RESTRICT"),
            nullable=True,
        ),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        _flag("chosen"),
        sa.Column(
            "discount_amount", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column(
            "free_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        _flag("part_share"),
    )
    op.create_index(f"IX_{table}_firm_id", table, ["firm_id"])
    op.create_index(f"IX_{table}_{document}", table, [document])
    op.create_index(f"IX_{table}_{line}", table, [line])


def _seed_permission() -> None:
    """Insert missing system permissions and reconcile system role grants."""
    bind = op.get_bind()
    existing = {
        code: permission_id
        for permission_id, code in bind.execute(
            sa.select(_permissions.c.id, _permissions.c.code)
        ).all()
    }
    for code in SYSTEM_PERMISSION_CODES:
        if code in existing:
            continue
        permission_id = uuid4()
        existing[code] = permission_id
        bind.execute(
            _permissions.insert().values(
                id=permission_id,
                code=code,
                name=code.replace("_", " ").title(),
                description="System-defined permission.",
                is_system=True,
                is_active=True,
                is_deleted=False,
            )
        )
    # The platform's own roles only: a firm may have named a role of its own
    # with a system role's code.
    role_ids = {
        code: role_id
        for role_id, code in bind.execute(
            sa.select(_roles.c.id, _roles.c.code).where(
                _roles.c.firm_id.is_(None), _roles.c.is_deleted.is_(False)
            )
        ).all()
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
        for permission_code in permission_codes:
            permission_id = existing.get(permission_code)
            if permission_id is None or (role_id, permission_id) in granted:
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
    """Add the tables, the columns and the permission where missing."""
    inspector = sa.inspect(op.get_bind())
    # Identity tables live only in the platform schema.
    if inspector.has_table("permissions") and inspector.has_table("roles"):
        _seed_permission()
    if inspector.has_table("promotions") and "allow_part_share" not in _present(
        inspector, "promotions"
    ):
        op.add_column("promotions", _flag("allow_part_share"))
    for table in _LINE_TABLES:
        if inspector.has_table(table) and "offer_choice_made" not in _present(
            inspector, table
        ):
            op.add_column(table, _flag("offer_choice_made"))
    # The keys point at tables a firm store holds and the platform does not.
    if not (inspector.has_table("promotions") and inspector.has_table("price_lists")):
        return
    for table, document, documents, line, lines in _OFFER_TABLES:
        if inspector.has_table(documents) and not inspector.has_table(table):
            _create_offer_table(table, document, documents, line, lines)


def downgrade() -> None:
    """Drop the tables and columns; leave the permission, a grant may rest on it."""
    inspector = sa.inspect(op.get_bind())
    for table, *_ in _OFFER_TABLES:
        if inspector.has_table(table):
            op.drop_table(table)
    for table in _LINE_TABLES:
        if inspector.has_table(table) and "offer_choice_made" in _present(
            inspector, table
        ):
            op.drop_column(table, "offer_choice_made")
    if inspector.has_table("promotions") and "allow_part_share" in _present(
        inspector, "promotions"
    ):
        op.drop_column("promotions", "allow_part_share")
