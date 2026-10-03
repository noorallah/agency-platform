"""The post-dated cheque register (ACC-2, decision A80).

* ``post_dated_cheques`` -- a cheque dated ahead, from a customer or to a
  supplier, held until it is banked; then the receipt or payment it became,
  and whether the bank cleared or returned it, with the return's charges.
* The control purpose ``CHEQUE_RETURN_CHARGES`` on *Cheque Return Charges
  Recovered* (4310, other income) for every firm whose books are open, only
  where missing and never overwriting -- the shape of ``20261003_0252``.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0253
Revises: 20261003_0252
Create Date: 2026-10-03

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261003_0253"
down_revision: str | Sequence[str] | None = "20261003_0252"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PURPOSE = "CHEQUE_RETURN_CHARGES"
_ACCOUNT = ("4310", "Cheque Return Charges Recovered", "INCOME", "REV", "Revenue")


def _base_columns() -> list[sa.Column[object]]:
    """Return the columns every ``BaseEntity`` table carries."""
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
        sa.Column("version", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("firm_id", UUIDType(), nullable=False),
    ]


def _create_cheques(inspector: sa.Inspector) -> None:
    """Create the register where it is missing."""
    if inspector.has_table("post_dated_cheques"):
        return
    op.create_table(
        "post_dated_cheques",
        *_base_columns(),
        sa.Column("direction", sa.String(20), nullable=False),
        sa.Column("customer_id", UUIDType(), nullable=True),
        sa.Column("vendor_id", UUIDType(), nullable=True),
        sa.Column("cheque_number", sa.String(30), nullable=False),
        sa.Column("cheque_date", sa.Date(), nullable=False),
        sa.Column("drawn_on_bank", sa.String(120), nullable=True),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("received_on", sa.Date(), nullable=False),
        sa.Column("narration", sa.Text(), nullable=True),
        sa.Column(
            "status", sa.String(20), server_default=sa.text("'HELD'"), nullable=False
        ),
        sa.Column("settlement_id", UUIDType(), nullable=True),
        sa.Column("deposited_on", sa.Date(), nullable=True),
        sa.Column("cleared_on", sa.Date(), nullable=True),
        sa.Column("bounced_on", sa.Date(), nullable=True),
        sa.Column("bounce_reason", sa.Text(), nullable=True),
        sa.Column(
            "bank_charges_amount",
            sa.Numeric(18, 2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "customer_charge_amount",
            sa.Numeric(18, 2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("charges_journal_entry_id", UUIDType(), nullable=True),
        sa.Column("charge_receivable_transaction_id", UUIDType(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="PK_post_dated_cheques"),
        sa.CheckConstraint(
            "(direction = 'RECEIPT' AND customer_id IS NOT NULL AND vendor_id IS "
            "NULL) OR (direction = 'PAYMENT' AND vendor_id IS NOT NULL AND "
            "customer_id IS NULL)",
            name="CK_post_dated_cheques_party_matches_direction",
        ),
        sa.CheckConstraint("amount > 0", name="CK_post_dated_cheques_amount_positive"),
        sa.CheckConstraint(
            "bank_charges_amount >= 0 AND customer_charge_amount >= 0",
            name="CK_post_dated_cheques_charges_not_negative",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name="FK_post_dated_cheques_customer_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["vendor_id"],
            ["vendors.id"],
            name="FK_post_dated_cheques_vendor_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["settlement_id"],
            ["settlements.id"],
            name="FK_post_dated_cheques_settlement_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["charges_journal_entry_id"],
            ["journal_entries.id"],
            name="FK_post_dated_cheques_charges_journal_entry_id",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("IX_post_dated_cheques_firm_id", "post_dated_cheques", ["firm_id"])
    op.create_index(
        "IX_post_dated_cheques_firm_status_date",
        "post_dated_cheques",
        ["firm_id", "status", "cheque_date"],
    )
    op.create_index(
        "IX_post_dated_cheques_firm_customer",
        "post_dated_cheques",
        ["firm_id", "customer_id"],
    )
    op.create_index(
        "IX_post_dated_cheques_firm_vendor",
        "post_dated_cheques",
        ["firm_id", "vendor_id"],
    )


def _group_for(bind: sa.Connection, firm_id: object) -> object:
    """Return the firm's revenue group, creating it only if missing."""
    _, _, kind, code, name = _ACCOUNT
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


def _seed_purpose(inspector: sa.Inspector) -> None:
    """Map the return-charges purpose for every firm whose books are open."""
    if not inspector.has_table("ledger_accounts") or not inspector.has_table(
        "firm_control_accounts"
    ):
        return
    bind = op.get_bind()
    code, name, kind, _, _ = _ACCOUNT
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
        mapped = bind.execute(
            sa.text(
                "SELECT id FROM firm_control_accounts WHERE firm_id = :firm "
                "AND purpose = :purpose AND is_deleted = false"
            ),
            {"firm": firm_id, "purpose": _PURPOSE},
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
            # The firm used the code for something else. Left for the firm.
            continue
        account_id = None if found is None else found[0]
        if account_id is None:
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
                    "group": _group_for(bind, firm_id),
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
                "purpose": _PURPOSE,
                "account": account_id,
            },
        )


def upgrade() -> None:
    """Build the register and map the return-charges purpose."""
    inspector = sa.inspect(op.get_bind())
    if (
        inspector.has_table("settlements")
        and inspector.has_table("customers")
        and inspector.has_table("vendors")
    ):
        _create_cheques(inspector)
    _seed_purpose(inspector)


def downgrade() -> None:
    """Drop the register and the mapping; keep the account."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("post_dated_cheques"):
        op.drop_table("post_dated_cheques")
    if inspector.has_table("firm_control_accounts"):
        op.execute(
            sa.text(
                "DELETE FROM firm_control_accounts "
                "WHERE purpose = 'CHEQUE_RETURN_CHARGES'"
            )
        )
