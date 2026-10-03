"""The supplier gifts register (BUY-2, decision A112).

* ``supplier_gifts``: date, supplier, item, value, who keeps it, the account,
  the delivery and scheme, 194R TDS, the journal.
* ``SUPPLIER_INCENTIVE_INCOME`` on *Supplier Incentives Received* (4320) and
  ``DRAWINGS`` on *Drawings* (3100) for every firm whose books are open, only
  where missing -- the shape of ``20261003_0243``.
* ``SUPPLIER_GIFT_MANAGE`` seeded and the system roles reconciled.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0276
Revises: 20261003_0275
Create Date: 2026-10-03

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType
from app.identity.system_seed import ROLE_PERMISSION_CODES, SYSTEM_PERMISSION_CODES

revision: str = "20261003_0276"
down_revision: str | Sequence[str] | None = "20261003_0275"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACCOUNTS = (
    (
        "SUPPLIER_INCENTIVE_INCOME",
        "4320",
        "Supplier Incentives Received",
        "INCOME",
        "REV",
        "Revenue",
    ),
    ("DRAWINGS", "3100", "Drawings", "EQUITY", "EQ", "Equity"),
)


def _group_for(
    bind: sa.Connection, firm_id: object, *, code: str, kind: str, name: str
) -> object:
    """Return the firm's group for an account, creating it only if it has none."""
    group_id = bind.execute(
        sa.text(
            "SELECT id FROM account_groups WHERE firm_id = :firm "
            "AND code = :code AND is_deleted = false"
        ),
        {"firm": firm_id, "code": code},
    ).scalar()
    if group_id is not None:
        return group_id
    group_id = uuid4()
    bind.execute(
        sa.text(
            "INSERT INTO account_groups (id, firm_id, code, name, "
            "account_type, is_active, is_deleted, version, "
            "created_at, updated_at) VALUES (:id, :firm, :code, "
            ":name, :kind, true, false, 1, now(), now())"
        ),
        {"id": group_id, "firm": firm_id, "code": code, "name": name, "kind": kind},
    )
    return group_id


def _seed_accounts(inspector: sa.Inspector) -> None:
    """Map the two gift purposes for every firm whose books are open."""
    if not inspector.has_table("ledger_accounts") or not inspector.has_table(
        "firm_control_accounts"
    ):
        return
    bind = op.get_bind()
    firms = (
        bind.execute(
            sa.text(
                "SELECT DISTINCT firm_id FROM ledger_accounts WHERE is_deleted = false"
            )
        )
        .scalars()
        .all()
    )
    for firm_id in firms:
        for purpose, code, name, kind, group_code, group_name in _ACCOUNTS:
            mapped = bind.execute(
                sa.text(
                    "SELECT id FROM firm_control_accounts WHERE firm_id = :firm "
                    "AND purpose = :purpose AND is_deleted = false"
                ),
                {"firm": firm_id, "purpose": purpose},
            ).scalar()
            if mapped is not None:
                continue
            found = bind.execute(
                sa.text(
                    "SELECT id, account_type FROM ledger_accounts "
                    "WHERE firm_id = :firm AND code = :code AND is_deleted = false"
                ),
                {"firm": firm_id, "code": code},
            ).first()
            if found is not None and found[1] != kind:
                # The firm used the code for something else; mapping it would
                # post an issue to whatever that is. Left for the firm.
                continue
            account_id = None if found is None else found[0]
            if account_id is None:
                group_id = _group_for(
                    bind, firm_id, code=group_code, kind=kind, name=group_name
                )
                account_id = uuid4()
                bind.execute(
                    sa.text(
                        "INSERT INTO ledger_accounts (id, firm_id, "
                        "account_group_id, code, name, account_type, "
                        "is_balance_sheet, is_profit_loss, "
                        "requires_cost_center, requires_profit_center, "
                        "is_active, is_deleted, version, created_at, "
                        "updated_at) VALUES (:id, :firm, :group, :code, :name, "
                        ":kind, false, true, false, false, "
                        "true, false, 1, now(), now())"
                    ),
                    {
                        "id": account_id,
                        "firm": firm_id,
                        "group": group_id,
                        "code": code,
                        "name": name,
                        "kind": kind,
                    },
                )
            bind.execute(
                sa.text(
                    "INSERT INTO firm_control_accounts (id, firm_id, purpose, "
                    "ledger_account_id, is_deleted, version, created_at, "
                    "updated_at) VALUES (:id, :firm, :purpose, :account, "
                    "false, 1, now(), now())"
                ),
                {
                    "id": uuid4(),
                    "firm": firm_id,
                    "purpose": purpose,
                    "account": account_id,
                },
            )


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


def _seed_permissions() -> None:
    """Insert missing system permissions and reconcile system role grants."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # Identity tables live only in the platform schema.
    if not inspector.has_table("permissions") or not inspector.has_table("roles"):
        return

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
    """Create the register, map the purposes and seed the permission."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("supplier_gifts") and inspector.has_table("vendors"):
        op.create_table(
            "supplier_gifts",
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
            sa.Column(
                "version", sa.Integer(), server_default=sa.text("0"), nullable=False
            ),
            sa.Column("firm_id", UUIDType(), nullable=False),
            sa.Column("gift_number", sa.String(60), nullable=False),
            sa.Column("gift_date", sa.Date(), nullable=False),
            sa.Column("vendor_id", UUIDType(), nullable=False),
            sa.Column("item", sa.String(200), nullable=False),
            sa.Column("value", sa.Numeric(18, 2), nullable=False),
            sa.Column("kept_by", sa.String(20), nullable=False),
            sa.Column("debit_account_id", UUIDType(), nullable=True),
            sa.Column("goods_receipt_id", UUIDType(), nullable=True),
            sa.Column("scheme_name", sa.String(120), nullable=True),
            sa.Column(
                "tds_194r_amount",
                sa.Numeric(18, 2),
                server_default=sa.text("0"),
                nullable=False,
            ),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("journal_entry_id", UUIDType(), nullable=True),
            sa.Column("reversal_journal_entry_id", UUIDType(), nullable=True),
            sa.Column("remarks", sa.Text(), nullable=True),
            sa.Column("cancel_reason", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id", name="PK_supplier_gifts"),
            sa.ForeignKeyConstraint(
                ["vendor_id"],
                ["vendors.id"],
                name="FK_supplier_gifts_vendor_id",
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["debit_account_id"],
                ["ledger_accounts.id"],
                name="FK_supplier_gifts_debit_account_id",
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["goods_receipt_id"],
                ["goods_receipts.id"],
                name="FK_supplier_gifts_goods_receipt_id",
                ondelete="SET NULL",
            ),
        )
        op.create_index("IX_supplier_gifts_firm_id", "supplier_gifts", ["firm_id"])
        op.create_index(
            "IX_supplier_gifts_firm_vendor_date",
            "supplier_gifts",
            ["firm_id", "vendor_id", "gift_date"],
        )
    _seed_accounts(inspector)
    _seed_permissions()


def downgrade() -> None:
    """Drop the register and the mappings; keep the accounts."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("supplier_gifts"):
        op.drop_table("supplier_gifts")
    if inspector.has_table("firm_control_accounts"):
        op.execute(
            sa.text(
                "DELETE FROM firm_control_accounts WHERE purpose IN "
                "('SUPPLIER_INCENTIVE_INCOME', 'DRAWINGS')"
            )
        )
