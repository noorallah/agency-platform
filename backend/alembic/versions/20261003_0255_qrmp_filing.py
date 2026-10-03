"""Quarterly GST filing, QRMP (GST-7, decision A83).

* ``gst_compliance_settings``: ``filing_frequency`` (MONTHLY), ``quarterly_from``
  and ``qrmp_payment_method`` (FIXED_SUM).
* ``gst_payments.cash_ledger_*``: what PMT-06 deposits paid of a settlement.
* ``gst_cash_deposits``: PMT-06 challans for months 1 and 2 of a quarter.
* The control purpose ``GST_CASH_LEDGER`` on *GST Electronic Cash Ledger*
  (1340, current asset) for every firm whose books are open, only where
  missing and never overwriting -- the shape of ``20261003_0253``.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0255
Revises: 20261003_0254
Create Date: 2026-10-03

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261003_0255"
down_revision: str | Sequence[str] | None = "20261003_0254"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PURPOSE = "GST_CASH_LEDGER"
_ACCOUNT = ("1340", "GST Electronic Cash Ledger", "ASSET", "CA", "Current Assets")
_HEADS = ("igst", "cgst", "sgst", "cess")


def _money(name: str) -> sa.Column[object]:
    """Return a NOT NULL money column defaulting to zero."""
    return sa.Column(
        name, sa.Numeric(18, 2), server_default=sa.text("0"), nullable=False
    )


def _columns(inspector: sa.Inspector, table: str) -> set[str]:
    """Return the column names a table has."""
    return {column["name"] for column in inspector.get_columns(table)}


def _settings(inspector: sa.Inspector) -> None:
    """Add the filing frequency to the GST settings where missing."""
    if not inspector.has_table("gst_compliance_settings"):
        return
    have = _columns(inspector, "gst_compliance_settings")
    if "filing_frequency" not in have:
        op.add_column(
            "gst_compliance_settings",
            sa.Column(
                "filing_frequency",
                sa.String(10),
                server_default=sa.text("'MONTHLY'"),
                nullable=False,
            ),
        )
    if "quarterly_from" not in have:
        op.add_column("gst_compliance_settings", sa.Column("quarterly_from", sa.Date()))
    if "qrmp_payment_method" not in have:
        op.add_column(
            "gst_compliance_settings",
            sa.Column(
                "qrmp_payment_method",
                sa.String(20),
                server_default=sa.text("'FIXED_SUM'"),
                nullable=False,
            ),
        )


def _payments(inspector: sa.Inspector) -> None:
    """Add what the deposits paid to each settlement, where missing."""
    if not inspector.has_table("gst_payments"):
        return
    have = _columns(inspector, "gst_payments")
    for head in _HEADS:
        if f"cash_ledger_{head}" not in have:
            op.add_column("gst_payments", _money(f"cash_ledger_{head}"))


def _deposits(inspector: sa.Inspector) -> None:
    """Create the PMT-06 deposit table where missing."""
    if inspector.has_table("gst_cash_deposits") or not inspector.has_table(
        "journal_entries"
    ):
        return
    op.create_table(
        "gst_cash_deposits",
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
        sa.Column("return_period", sa.String(7), nullable=False),
        sa.Column("deposit_date", sa.Date(), nullable=False),
        sa.Column("method", sa.String(20), nullable=False),
        sa.Column("money_account_id", UUIDType(), nullable=False),
        sa.Column("challan_cpin", sa.String(20), nullable=True),
        sa.Column("challan_cin", sa.String(30), nullable=True),
        *(_money(f"amount_{head}") for head in _HEADS),
        sa.Column("narration", sa.Text(), nullable=True),
        sa.Column(
            "status", sa.String(20), server_default=sa.text("'POSTED'"), nullable=False
        ),
        sa.Column("journal_entry_id", UUIDType(), nullable=False),
        sa.Column("reversal_journal_entry_id", UUIDType(), nullable=True),
        sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reversed_by", UUIDType(), nullable=True),
        sa.Column("reversal_reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="PK_gst_cash_deposits"),
        sa.ForeignKeyConstraint(
            ["money_account_id"],
            ["ledger_accounts.id"],
            name="FK_gst_cash_deposits_money_account_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["journal_entry_id"],
            ["journal_entries.id"],
            name="FK_gst_cash_deposits_journal_entry_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reversal_journal_entry_id"],
            ["journal_entries.id"],
            name="FK_gst_cash_deposits_reversal_journal_entry_id",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("IX_gst_cash_deposits_firm_id", "gst_cash_deposits", ["firm_id"])
    op.create_index(
        "IX_gst_cash_deposits_firm_period",
        "gst_cash_deposits",
        ["firm_id", "return_period"],
    )


def _group_for(bind: sa.Connection, firm_id: object) -> object:
    """Return the firm's current-assets group, creating it only if missing."""
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
    """Map the cash-ledger purpose for every firm whose books are open."""
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
                    ":kind, true, false, false, false, "
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
    """Add quarterly filing, the deposits and the cash-ledger purpose."""
    inspector = sa.inspect(op.get_bind())
    _settings(inspector)
    _payments(inspector)
    _deposits(inspector)
    _seed_purpose(inspector)


def downgrade() -> None:
    """Drop the deposits, the columns and the mapping; keep the account."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("gst_cash_deposits"):
        op.drop_table("gst_cash_deposits")
    if inspector.has_table("gst_payments"):
        have = _columns(inspector, "gst_payments")
        for head in _HEADS:
            if f"cash_ledger_{head}" in have:
                op.drop_column("gst_payments", f"cash_ledger_{head}")
    if inspector.has_table("gst_compliance_settings"):
        have = _columns(inspector, "gst_compliance_settings")
        for column in ("filing_frequency", "quarterly_from", "qrmp_payment_method"):
            if column in have:
                op.drop_column("gst_compliance_settings", column)
    if inspector.has_table("firm_control_accounts"):
        op.execute(
            sa.text(
                "DELETE FROM firm_control_accounts WHERE purpose = 'GST_CASH_LEDGER'"
            )
        )
