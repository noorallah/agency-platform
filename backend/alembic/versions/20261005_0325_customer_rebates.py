"""Turnover rebates to customers (SG-9, backlog 87 #9).

The selling-side twin of ``20261003_0286``.

* ``customer_rebate_agreements`` and ``customer_rebate_slabs``: an agreement
  names one customer or one customer group, a period and its slabs.
* ``party_adjustments.customer_rebate_agreement_id`` and the kind
  ``CUSTOMER_REBATE`` (customer only) in
  ``CK_party_adjustments_parties_match_kind``.
* ``REBATES_ALLOWED`` mapped to *Rebates Allowed* (5310, direct expenses) and
  ``CUSTOMER_REBATE_PAYABLE`` to *Customer Rebates Payable* (2900, current
  liabilities) for every firm whose books are open -- new firms get both from
  ``opening_setup``. Only where missing, never overwriting; an account holding
  either code under another type is left for the firm to map. The shape of
  ``20261005_0319``.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent. No ``firm_id``
foreign key: ``firms`` lives only in the platform store.

Revision ID: 20261005_0325
Revises: 20261005_0324
Create Date: 2026-10-05

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261005_0325"
down_revision: str | Sequence[str] | None = "20261005_0324"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_AGREEMENTS = "customer_rebate_agreements"
_SLABS = "customer_rebate_slabs"
_ADJUSTMENTS = "party_adjustments"
_LINK = "customer_rebate_agreement_id"

#: (purpose, code, name, account type, group code, group name, balance sheet)
_ACCOUNTS = (
    (
        "REBATES_ALLOWED",
        "5310",
        "Rebates Allowed",
        "EXPENSE",
        "EXP",
        "Direct Expenses",
        False,
    ),
    (
        "CUSTOMER_REBATE_PAYABLE",
        "2900",
        "Customer Rebates Payable",
        "LIABILITY",
        "CL",
        "Current Liabilities",
        True,
    ),
)

_PARTIES = "CK_party_adjustments_parties_match_kind"
_PARTIES_BEFORE = (
    "(kind = 'CUSTOMER_WRITE_OFF' AND customer_id IS NOT NULL "
    "AND vendor_id IS NULL) OR (kind = 'SUPPLIER_WRITE_BACK' "
    "AND vendor_id IS NOT NULL AND customer_id IS NULL) OR "
    "(kind = 'SET_OFF' AND customer_id IS NOT NULL "
    "AND vendor_id IS NOT NULL) OR (kind = 'SUPPLIER_REBATE' "
    "AND vendor_id IS NOT NULL AND customer_id IS NULL) OR "
    "(kind = 'PRINCIPAL_CLAIM' AND vendor_id IS NOT NULL "
    "AND customer_id IS NULL)"
)
_PARTIES_CHECK = (
    _PARTIES_BEFORE + " OR (kind = 'CUSTOMER_REBATE' AND customer_id IS NOT NULL "
    "AND vendor_id IS NULL)"
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
    if not inspector.has_table(_AGREEMENTS):
        keys: list[sa.ForeignKeyConstraint] = [
            sa.ForeignKeyConstraint(
                ["customer_id"],
                ["customers.id"],
                name="FK_customer_rebate_agreements_customer_id",
                ondelete="RESTRICT",
            )
        ]
        # Guarded as every cross-table key here is: a store shaped by
        # `create_all` can hold some of these and not others.
        if inspector.has_table("customer_groups"):
            keys.append(
                sa.ForeignKeyConstraint(
                    ["customer_group_id"],
                    ["customer_groups.id"],
                    name="FK_customer_rebate_agreements_customer_group_id",
                    ondelete="RESTRICT",
                )
            )
        if inspector.has_table("journal_entries"):
            keys.append(
                sa.ForeignKeyConstraint(
                    ["accrual_journal_id"],
                    ["journal_entries.id"],
                    name="FK_customer_rebate_agreements_accrual_journal_id",
                    ondelete="RESTRICT",
                )
            )
        op.create_table(
            _AGREEMENTS,
            *_audit_columns(),
            sa.Column("firm_id", UUIDType(), nullable=False),
            sa.Column("customer_id", UUIDType(), nullable=True),
            sa.Column("customer_group_id", UUIDType(), nullable=True),
            sa.Column("code", sa.String(40), nullable=False),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("period_from", sa.Date(), nullable=False),
            sa.Column("period_to", sa.Date(), nullable=False),
            sa.Column("status", sa.String(20), server_default="ACTIVE", nullable=False),
            sa.Column(
                "agreed_before_sale",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("accrued_turnover", sa.Numeric(18, 2), nullable=True),
            sa.Column("accrued_rate", sa.Numeric(7, 4), nullable=True),
            sa.Column("accrued_amount", sa.Numeric(18, 2), nullable=True),
            sa.Column("accrual_journal_id", UUIDType(), nullable=True),
            sa.Column("accrued_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("accrued_by", UUIDType(), nullable=True),
            sa.PrimaryKeyConstraint("id", name="PK_customer_rebate_agreements"),
            *keys,
            sa.CheckConstraint(
                "period_to >= period_from",
                name=op.f("CK_customer_rebate_agreements_period_order"),
            ),
            sa.CheckConstraint(
                "(customer_id IS NOT NULL AND customer_group_id IS NULL) OR "
                "(customer_id IS NULL AND customer_group_id IS NOT NULL)",
                name=op.f("CK_customer_rebate_agreements_one_party"),
            ),
        )
        op.create_index(
            "IX_customer_rebate_agreements_firm_id", _AGREEMENTS, ["firm_id"]
        )
        op.create_index(
            "IX_customer_rebate_agreements_firm_customer",
            _AGREEMENTS,
            ["firm_id", "customer_id"],
        )
        op.create_index(
            "IX_customer_rebate_agreements_firm_group",
            _AGREEMENTS,
            ["firm_id", "customer_group_id"],
        )
        op.create_index(
            "UQ_customer_rebate_agreements_code_active",
            _AGREEMENTS,
            ["firm_id", "code"],
            unique=True,
            postgresql_where=sa.text("is_deleted = false"),
        )
    if not inspector.has_table(_SLABS):
        op.create_table(
            _SLABS,
            *_audit_columns(),
            sa.Column("agreement_id", UUIDType(), nullable=False),
            sa.Column("firm_id", UUIDType(), nullable=False),
            sa.Column("line_number", sa.Integer(), nullable=False),
            sa.Column("threshold", sa.Numeric(18, 2), nullable=False),
            sa.Column("rate_percent", sa.Numeric(7, 4), nullable=False),
            sa.PrimaryKeyConstraint("id", name="PK_customer_rebate_slabs"),
            sa.ForeignKeyConstraint(
                ["agreement_id"],
                [f"{_AGREEMENTS}.id"],
                name="FK_customer_rebate_slabs_agreement_id",
                ondelete="CASCADE",
            ),
            sa.CheckConstraint(
                "threshold >= 0", name=op.f("CK_customer_rebate_slabs_threshold")
            ),
            sa.CheckConstraint(
                "rate_percent > 0 AND rate_percent <= 100",
                name=op.f("CK_customer_rebate_slabs_rate"),
            ),
        )
        op.create_index("IX_customer_rebate_slabs_agreement", _SLABS, ["agreement_id"])


def _party_adjustments(inspector: sa.Inspector) -> None:
    """Link a rebate settlement to its agreement and admit the kind."""
    if not inspector.has_table(_ADJUSTMENTS):
        return
    columns = {column["name"] for column in inspector.get_columns(_ADJUSTMENTS)}
    if _LINK not in columns:
        op.add_column(_ADJUSTMENTS, sa.Column(_LINK, UUIDType(), nullable=True))
        op.create_foreign_key(
            f"FK_party_adjustments_{_LINK}",
            _ADJUSTMENTS,
            _AGREEMENTS,
            [_LINK],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_index(f"IX_party_adjustments_{_LINK}", _ADJUSTMENTS, [_LINK])
    checks = {
        str(check["name"]): str(check.get("sqltext", ""))
        for check in inspector.get_check_constraints(_ADJUSTMENTS)
    }
    # Found by its ending and dropped by its own name, as 0286 and 0290 do:
    # the deployed name carries the table prefix the naming convention adds,
    # and creating it through the convention keeps it what `create_all` makes.
    found = [name for name in checks if name.endswith("parties_match_kind")]
    current = [name for name in found if "CUSTOMER_REBATE" in checks[name]]
    for name in found:
        if name not in current:
            op.drop_constraint(op.f(name), _ADJUSTMENTS, type_="check")
    if not current:
        op.create_check_constraint(_PARTIES, _ADJUSTMENTS, _PARTIES_CHECK)


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
    """Map the two rebate accounts for every firm whose books are open."""
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
        for purpose, code, name, kind, group_code, group_name, on_sheet in _ACCOUNTS:
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
                        ":kind, :on_sheet, :in_profit, false, false, "
                        "true, false, 1, now(), now())"
                    ),
                    {
                        "id": account_id,
                        "firm": firm_id,
                        "group": group_id,
                        "code": code,
                        "name": name,
                        "kind": kind,
                        "on_sheet": on_sheet,
                        "in_profit": not on_sheet,
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
    """Create the tables, admit the kind and map the two accounts."""
    inspector = sa.inspect(op.get_bind())
    # Firm stores only: the platform store holds no customers.
    if not inspector.has_table("customers"):
        return
    _tables(inspector)
    _party_adjustments(inspector)
    _seed_accounts(inspector)


def downgrade() -> None:
    """Drop the rebate tables and the kind; keep the accounts and postings."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("firm_control_accounts"):
        op.execute(
            sa.text(
                "DELETE FROM firm_control_accounts WHERE purpose IN "
                "('REBATES_ALLOWED', 'CUSTOMER_REBATE_PAYABLE')"
            )
        )
    if inspector.has_table(_ADJUSTMENTS):
        columns = {column["name"] for column in inspector.get_columns(_ADJUSTMENTS)}
        for check in inspector.get_check_constraints(_ADJUSTMENTS):
            name = str(check["name"])
            if name.endswith("parties_match_kind"):
                op.drop_constraint(op.f(name), _ADJUSTMENTS, type_="check")
        op.create_check_constraint(_PARTIES, _ADJUSTMENTS, _PARTIES_BEFORE)
        if _LINK in columns:
            op.drop_index(f"IX_party_adjustments_{_LINK}", table_name=_ADJUSTMENTS)
            op.drop_constraint(
                f"FK_party_adjustments_{_LINK}", _ADJUSTMENTS, type_="foreignkey"
            )
            op.drop_column(_ADJUSTMENTS, _LINK)
    for table in (_SLABS, _AGREEMENTS):
        if inspector.has_table(table):
            op.drop_table(table)
