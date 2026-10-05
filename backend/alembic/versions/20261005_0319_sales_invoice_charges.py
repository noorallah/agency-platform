"""Charges on the bill with their own GST (SG-4, backlog 87 #4).

* ``sales_invoice_charges``: packing, handling, insurance or another charge
  on a sales invoice, priced before tax and taxed by the profile it names,
  with the tax kept by GST head as charged.
* ``OTHER_CHARGES_RECOVERED`` mapped to *Other Charges Recovered* (4050,
  revenue) for every firm whose books are open, the shape of
  ``20261005_0308``: only where missing, never overwriting.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: the table is
created only in a store that holds ``sales_invoices`` and lacks it, and the
key to ``tax_profiles`` only where that table is there. No ``firm_id``
foreign key: ``firms`` lives only in the platform store.

Revision ID: 20261005_0319
Revises: 20261005_0318
Create Date: 2026-10-05

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261005_0319"
down_revision: str | Sequence[str] | None = "20261005_0318"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "sales_invoice_charges"
_BILLS = "sales_invoices"
_PURPOSE = "OTHER_CHARGES_RECOVERED"

#: (purpose, code, name, account type, group code, group name)
_ACCOUNTS = (
    (
        _PURPOSE,
        "4050",
        "Other Charges Recovered",
        "INCOME",
        "REV",
        "Revenue",
    ),
)


def _money(name: str, precision: int = 18) -> sa.Column[object]:
    """Return a four-decimal figure that starts at nothing."""
    return sa.Column(
        name,
        sa.Numeric(precision, 4),
        server_default=sa.text("0"),
        nullable=False,
    )


def _create_charges(inspector: sa.Inspector) -> None:
    """Create the table a bill keeps its separately taxed charges in."""
    keys = [
        sa.ForeignKeyConstraint(
            ["sales_invoice_id"],
            [f"{_BILLS}.id"],
            name=f"FK_{_TABLE}_sales_invoice_id",
            ondelete="CASCADE",
        )
    ]
    if inspector.has_table("tax_profiles"):
        keys.append(
            sa.ForeignKeyConstraint(
                ["tax_profile_id"],
                ["tax_profiles.id"],
                name=f"FK_{_TABLE}_tax_profile_id",
                ondelete="RESTRICT",
            )
        )
    op.create_table(
        _TABLE,
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
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column("sales_invoice_id", UUIDType(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("hsn_sac", sa.String(20), nullable=True),
        _money("amount"),
        sa.Column("tax_profile_id", UUIDType(), nullable=True),
        _money("tax_rate_percent", 9),
        _money("tax_amount"),
        _money("igst_amount"),
        _money("cgst_amount"),
        _money("sgst_amount"),
        _money("cess_amount"),
        sa.PrimaryKeyConstraint("id", name=f"PK_{_TABLE}"),
        *keys,
    )
    op.create_index(f"IX_{_TABLE}_firm_id", _TABLE, ["firm_id"])
    op.create_index(f"IX_{_TABLE}_invoice", _TABLE, ["sales_invoice_id"])


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
    """Map the charges account for every firm whose books are open."""
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
                # credit the charges to whatever that is. Left for the firm.
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


def upgrade() -> None:
    """Create the charges table and map the account they are credited to."""
    inspector = sa.inspect(op.get_bind())
    # Firm stores only: the platform store holds no bills.
    if not inspector.has_table(_BILLS):
        return
    if not inspector.has_table(_TABLE):
        _create_charges(inspector)
    _seed_accounts(inspector)


def downgrade() -> None:
    """Drop the charges table and the mapping; keep the account."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("firm_control_accounts"):
        op.execute(
            sa.text(f"DELETE FROM firm_control_accounts WHERE purpose = '{_PURPOSE}'")
        )
    if inspector.has_table(_TABLE):
        op.drop_table(_TABLE)
