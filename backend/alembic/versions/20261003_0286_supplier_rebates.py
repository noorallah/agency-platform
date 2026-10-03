"""Supplier volume rebates (BUY-13, decision A124).

* ``supplier_rebate_agreements`` and ``supplier_rebate_slabs``.
* ``party_adjustments.rebate_agreement_id`` and the kind ``SUPPLIER_REBATE``
  (supplier only) in ``CK_party_adjustments_parties_match_kind``.
* ``SUPPLIER_REBATE_RECEIVABLE`` mapped to *Supplier Rebates Receivable*
  (1410, current assets) for every firm whose books are open -- new firms get
  it from ``opening_setup``. Only where missing, never overwriting; an account
  holding 1410 of another type is left for the firm to map. The shape of
  ``20261003_0243``.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0286
Revises: 20261003_0285
Create Date: 2026-10-03

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261003_0286"
down_revision: str | Sequence[str] | None = "20261003_0285"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: (purpose, code, name, account type, group code, group name)
_ACCOUNTS = (
    (
        "SUPPLIER_REBATE_RECEIVABLE",
        "1410",
        "Supplier Rebates Receivable",
        "ASSET",
        "CA",
        "Current Assets",
    ),
)

_PARTIES = "CK_party_adjustments_parties_match_kind"
_PARTIES_BEFORE = (
    "(kind = 'CUSTOMER_WRITE_OFF' AND customer_id IS NOT NULL "
    "AND vendor_id IS NULL) OR (kind = 'SUPPLIER_WRITE_BACK' "
    "AND vendor_id IS NOT NULL AND customer_id IS NULL) OR "
    "(kind = 'SET_OFF' AND customer_id IS NOT NULL "
    "AND vendor_id IS NOT NULL)"
)
_PARTIES_CHECK = (
    _PARTIES_BEFORE + " OR (kind = 'SUPPLIER_REBATE' "
    "AND vendor_id IS NOT NULL AND customer_id IS NULL)"
)


def _audit_columns() -> list[sa.Column[object]]:
    """Return the columns every entity carries."""
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
    ]


def _tables(inspector: sa.Inspector) -> None:
    """Create the agreements and their slabs."""
    if not inspector.has_table("supplier_rebate_agreements"):
        op.create_table(
            "supplier_rebate_agreements",
            *_audit_columns(),
            sa.Column("firm_id", UUIDType(), nullable=False),
            sa.Column("vendor_id", UUIDType(), nullable=False),
            sa.Column("code", sa.String(40), nullable=False),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("period_from", sa.Date(), nullable=False),
            sa.Column("period_to", sa.Date(), nullable=False),
            sa.Column("status", sa.String(20), server_default="ACTIVE", nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("accrued_volume", sa.Numeric(18, 2), nullable=True),
            sa.Column("accrued_rate", sa.Numeric(7, 4), nullable=True),
            sa.Column("accrued_amount", sa.Numeric(18, 2), nullable=True),
            sa.Column("accrual_journal_id", UUIDType(), nullable=True),
            sa.Column("accrued_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("accrued_by", UUIDType(), nullable=True),
            sa.PrimaryKeyConstraint("id", name="PK_supplier_rebate_agreements"),
            sa.ForeignKeyConstraint(
                ["vendor_id"],
                ["vendors.id"],
                name="FK_supplier_rebate_agreements_vendor_id",
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["accrual_journal_id"],
                ["journal_entries.id"],
                name="FK_supplier_rebate_agreements_accrual_journal_id",
                ondelete="RESTRICT",
            ),
            sa.CheckConstraint(
                "period_to >= period_from",
                name="CK_supplier_rebate_agreements_period_order",
            ),
        )
        op.create_index(
            "IX_supplier_rebate_agreements_firm_id",
            "supplier_rebate_agreements",
            ["firm_id"],
        )
        op.create_index(
            "IX_supplier_rebate_agreements_firm_vendor",
            "supplier_rebate_agreements",
            ["firm_id", "vendor_id"],
        )
        op.create_index(
            "UQ_supplier_rebate_agreements_code_active",
            "supplier_rebate_agreements",
            ["firm_id", "code"],
            unique=True,
            postgresql_where=sa.text("is_deleted = false"),
        )
    if not inspector.has_table("supplier_rebate_slabs"):
        op.create_table(
            "supplier_rebate_slabs",
            *_audit_columns(),
            sa.Column("agreement_id", UUIDType(), nullable=False),
            sa.Column("firm_id", UUIDType(), nullable=False),
            sa.Column("line_number", sa.Integer(), nullable=False),
            sa.Column("threshold", sa.Numeric(18, 2), nullable=False),
            sa.Column("rate_percent", sa.Numeric(7, 4), nullable=False),
            sa.PrimaryKeyConstraint("id", name="PK_supplier_rebate_slabs"),
            sa.ForeignKeyConstraint(
                ["agreement_id"],
                ["supplier_rebate_agreements.id"],
                name="FK_supplier_rebate_slabs_agreement_id",
                ondelete="CASCADE",
            ),
            sa.CheckConstraint(
                "threshold >= 0", name="CK_supplier_rebate_slabs_threshold"
            ),
            sa.CheckConstraint(
                "rate_percent > 0 AND rate_percent <= 100",
                name="CK_supplier_rebate_slabs_rate",
            ),
        )
        op.create_index(
            "IX_supplier_rebate_slabs_agreement",
            "supplier_rebate_slabs",
            ["agreement_id"],
        )


def _party_adjustments(inspector: sa.Inspector) -> None:
    """Link a rebate settlement to its agreement and admit the kind."""
    if not inspector.has_table("party_adjustments"):
        return
    columns = {column["name"] for column in inspector.get_columns("party_adjustments")}
    if "rebate_agreement_id" not in columns:
        op.add_column(
            "party_adjustments",
            sa.Column("rebate_agreement_id", UUIDType(), nullable=True),
        )
        op.create_foreign_key(
            "FK_party_adjustments_rebate_agreement_id",
            "party_adjustments",
            "supplier_rebate_agreements",
            ["rebate_agreement_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_index(
            "IX_party_adjustments_rebate_agreement_id",
            "party_adjustments",
            ["rebate_agreement_id"],
        )
    checks = {
        str(check["name"]): str(check.get("sqltext", ""))
        for check in inspector.get_check_constraints("party_adjustments")
    }
    if _PARTIES in checks and "SUPPLIER_REBATE" not in checks[_PARTIES]:
        op.drop_constraint(_PARTIES, "party_adjustments", type_="check")
        checks.pop(_PARTIES)
    if _PARTIES not in checks:
        op.create_check_constraint(_PARTIES, "party_adjustments", _PARTIES_CHECK)


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
    """Map the rebate receivable for every firm whose books are open."""
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
                # post a rebate to whatever that is. Left for the firm.
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
                        ":kind, true, false, false, false, "
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
    """Create the tables, admit the kind and map the receivable."""
    inspector = sa.inspect(op.get_bind())
    # Firm stores only: the platform store holds no suppliers.
    if not inspector.has_table("vendors"):
        return
    _tables(inspector)
    _party_adjustments(inspector)
    _seed_accounts(inspector)


def downgrade() -> None:
    """Drop the rebate tables and the kind; keep the account and its postings."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("firm_control_accounts"):
        op.execute(
            sa.text(
                "DELETE FROM firm_control_accounts "
                "WHERE purpose = 'SUPPLIER_REBATE_RECEIVABLE'"
            )
        )
    if inspector.has_table("party_adjustments"):
        columns = {
            column["name"] for column in inspector.get_columns("party_adjustments")
        }
        op.drop_constraint(_PARTIES, "party_adjustments", type_="check")
        op.create_check_constraint(_PARTIES, "party_adjustments", _PARTIES_BEFORE)
        if "rebate_agreement_id" in columns:
            op.drop_index(
                "IX_party_adjustments_rebate_agreement_id",
                table_name="party_adjustments",
            )
            op.drop_constraint(
                "FK_party_adjustments_rebate_agreement_id",
                "party_adjustments",
                type_="foreignkey",
            )
            op.drop_column("party_adjustments", "rebate_agreement_id")
    for table in ("supplier_rebate_slabs", "supplier_rebate_agreements"):
        if inspector.has_table(table):
            op.drop_table(table)
