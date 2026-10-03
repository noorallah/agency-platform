"""Claims to the principal (SEL-11, decision A128).

* ``promotions.principal_id`` and ``principal_share_percent``: the principal
  funding a scheme, and its share.
* ``principal_claims``, ``principal_claim_lines`` and
  ``principal_claim_receipts``.
* ``party_adjustments.principal_claim_id`` and the kind ``PRINCIPAL_CLAIM``
  (supplier only) in ``CK_party_adjustments_parties_match_kind``.
* ``PRINCIPAL_CLAIM_RECEIVABLE`` mapped to *Claims Receivable from
  Principals* (1420, current assets) for every firm whose books are open, the
  shape of ``20261003_0286``: only where missing, never overwriting.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0290
Revises: 20261003_0289
Create Date: 2026-10-03

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261003_0290"
down_revision: str | Sequence[str] | None = "20261003_0289"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: (purpose, code, name, account type, group code, group name)
_ACCOUNTS = (
    (
        "PRINCIPAL_CLAIM_RECEIVABLE",
        "1420",
        "Claims Receivable from Principals",
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
    "AND vendor_id IS NOT NULL) OR (kind = 'SUPPLIER_REBATE' "
    "AND vendor_id IS NOT NULL AND customer_id IS NULL)"
)
_PARTIES_CHECK = (
    _PARTIES_BEFORE + " OR (kind = 'PRINCIPAL_CLAIM' AND vendor_id IS NOT NULL "
    "AND customer_id IS NULL)"
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


def _money(name: str) -> sa.Column[object]:
    """Return an amount column defaulting to zero."""
    return sa.Column(
        name, sa.Numeric(18, 2), server_default=sa.text("0"), nullable=False
    )


def _fk(column: str, table: str, target: str, ondelete: str) -> sa.ForeignKeyConstraint:
    """Return a foreign key named for its referring column."""
    return sa.ForeignKeyConstraint(
        [column], [f"{target}.id"], name=f"FK_{table}_{column}", ondelete=ondelete
    )


def _promotions(inspector: sa.Inspector) -> None:
    """Let a promotion name the principal funding it."""
    if not inspector.has_table("promotions"):
        return
    columns = {column["name"] for column in inspector.get_columns("promotions")}
    if "principal_id" not in columns:
        op.add_column(
            "promotions", sa.Column("principal_id", UUIDType(), nullable=True)
        )
        if inspector.has_table("principals"):
            op.create_foreign_key(
                "FK_promotions_principal_id",
                "promotions",
                "principals",
                ["principal_id"],
                ["id"],
                ondelete="RESTRICT",
            )
    if "principal_share_percent" not in columns:
        op.add_column(
            "promotions",
            sa.Column(
                "principal_share_percent",
                sa.Numeric(7, 4),
                server_default=sa.text("100"),
                nullable=False,
            ),
        )


def _tables(inspector: sa.Inspector) -> None:
    """Create the claim, line and receipt tables."""
    if not inspector.has_table("principal_claims"):
        op.create_table(
            "principal_claims",
            *_audit_columns(),
            sa.Column("firm_id", UUIDType(), nullable=False),
            sa.Column("claim_number", sa.String(60), nullable=False),
            sa.Column("claim_date", sa.Date(), nullable=False),
            sa.Column("principal_id", UUIDType(), nullable=False),
            sa.Column("vendor_id", UUIDType(), nullable=True),
            sa.Column("period_from", sa.Date(), nullable=False),
            sa.Column("period_to", sa.Date(), nullable=False),
            _money("scheme_amount"),
            _money("expiry_amount"),
            _money("breakage_amount"),
            _money("total_amount"),
            sa.Column(
                "status",
                sa.String(20),
                server_default=sa.text("'RAISED'"),
                nullable=False,
            ),
            sa.Column("journal_entry_id", UUIDType(), nullable=True),
            sa.Column("remarks", sa.Text(), nullable=True),
            sa.Column("cancel_reason", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id", name="PK_principal_claims"),
            _fk("principal_id", "principal_claims", "principals", "RESTRICT"),
            _fk("vendor_id", "principal_claims", "vendors", "RESTRICT"),
            _fk("journal_entry_id", "principal_claims", "journal_entries", "RESTRICT"),
        )
        op.create_index("IX_principal_claims_firm_id", "principal_claims", ["firm_id"])
        op.create_index(
            "IX_principal_claims_firm_principal",
            "principal_claims",
            ["firm_id", "principal_id"],
        )
        op.create_index(
            "UQ_principal_claims_number_active",
            "principal_claims",
            ["firm_id", "claim_number"],
            unique=True,
            postgresql_where=sa.text("is_deleted = false"),
        )
    if not inspector.has_table("principal_claim_lines"):
        op.create_table(
            "principal_claim_lines",
            *_audit_columns(),
            sa.Column("claim_id", UUIDType(), nullable=False),
            sa.Column("firm_id", UUIDType(), nullable=False),
            sa.Column("line_number", sa.Integer(), nullable=False),
            sa.Column("kind", sa.String(20), nullable=False),
            sa.Column("source_id", UUIDType(), nullable=False),
            sa.Column("source_number", sa.String(80), nullable=False),
            sa.Column("source_date", sa.Date(), nullable=False),
            sa.Column("product_id", UUIDType(), nullable=True),
            sa.Column("quantity", sa.Numeric(18, 4), nullable=True),
            sa.Column("description", sa.String(300), nullable=False),
            sa.Column("amount", sa.Numeric(18, 2), nullable=False),
            sa.PrimaryKeyConstraint("id", name="PK_principal_claim_lines"),
            _fk("claim_id", "principal_claim_lines", "principal_claims", "CASCADE"),
            _fk("product_id", "principal_claim_lines", "products", "RESTRICT"),
        )
        op.create_index(
            "IX_principal_claim_lines_firm_id", "principal_claim_lines", ["firm_id"]
        )
        op.create_index(
            "IX_principal_claim_lines_claim", "principal_claim_lines", ["claim_id"]
        )
        op.create_index(
            "UQ_principal_claim_lines_source_active",
            "principal_claim_lines",
            ["kind", "source_id"],
            unique=True,
            postgresql_where=sa.text("is_deleted = false"),
        )
    if not inspector.has_table("principal_claim_receipts"):
        op.create_table(
            "principal_claim_receipts",
            *_audit_columns(),
            sa.Column("claim_id", UUIDType(), nullable=False),
            sa.Column("firm_id", UUIDType(), nullable=False),
            sa.Column("received_on", sa.Date(), nullable=False),
            sa.Column("amount", sa.Numeric(18, 2), nullable=False),
            sa.Column("money_account_id", UUIDType(), nullable=False),
            sa.Column("reference", sa.String(100), nullable=True),
            sa.Column(
                "status",
                sa.String(20),
                server_default=sa.text("'POSTED'"),
                nullable=False,
            ),
            sa.Column("journal_entry_id", UUIDType(), nullable=True),
            sa.PrimaryKeyConstraint("id", name="PK_principal_claim_receipts"),
            _fk("claim_id", "principal_claim_receipts", "principal_claims", "CASCADE"),
            _fk(
                "money_account_id",
                "principal_claim_receipts",
                "ledger_accounts",
                "RESTRICT",
            ),
            _fk(
                "journal_entry_id",
                "principal_claim_receipts",
                "journal_entries",
                "RESTRICT",
            ),
        )
        op.create_index(
            "IX_principal_claim_receipts_firm_id",
            "principal_claim_receipts",
            ["firm_id"],
        )
        op.create_index(
            "IX_principal_claim_receipts_claim",
            "principal_claim_receipts",
            ["claim_id"],
        )


def _party_adjustments(inspector: sa.Inspector) -> None:
    """Link a claim settlement to its claim and admit the kind."""
    if not inspector.has_table("party_adjustments"):
        return
    columns = {column["name"] for column in inspector.get_columns("party_adjustments")}
    if "principal_claim_id" not in columns:
        op.add_column(
            "party_adjustments",
            sa.Column("principal_claim_id", UUIDType(), nullable=True),
        )
        op.create_foreign_key(
            "FK_party_adjustments_principal_claim_id",
            "party_adjustments",
            "principal_claims",
            ["principal_claim_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_index(
            "IX_party_adjustments_principal_claim_id",
            "party_adjustments",
            ["principal_claim_id"],
        )
    checks = {
        str(check["name"]): str(check.get("sqltext", ""))
        for check in inspector.get_check_constraints("party_adjustments")
    }
    # Found by its ending and dropped by its own name, as 0286 does: the
    # deployed name carries the table prefix the naming convention adds.
    found = [name for name in checks if name.endswith("parties_match_kind")]
    current = [name for name in found if "PRINCIPAL_CLAIM" in checks[name]]
    for name in found:
        if name not in current:
            op.drop_constraint(op.f(name), "party_adjustments", type_="check")
    if not current:
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
    """Map the claims receivable for every firm whose books are open."""
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
                # post a claim to whatever that is. Left for the firm.
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
    """Add the funding, the claim tables, the kind and the receivable."""
    inspector = sa.inspect(op.get_bind())
    # Firm stores only: the platform store holds no suppliers.
    if not inspector.has_table("vendors"):
        return
    _promotions(inspector)
    _tables(inspector)
    _party_adjustments(sa.inspect(op.get_bind()))
    _seed_accounts(inspector)


def downgrade() -> None:
    """Drop the claim tables, the kind and the funding; keep the account."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("firm_control_accounts"):
        op.execute(
            sa.text(
                "DELETE FROM firm_control_accounts "
                "WHERE purpose = 'PRINCIPAL_CLAIM_RECEIVABLE'"
            )
        )
    if inspector.has_table("party_adjustments"):
        columns = {
            column["name"] for column in inspector.get_columns("party_adjustments")
        }
        for check in inspector.get_check_constraints("party_adjustments"):
            name = str(check["name"])
            if name.endswith("parties_match_kind"):
                op.drop_constraint(op.f(name), "party_adjustments", type_="check")
        op.create_check_constraint(_PARTIES, "party_adjustments", _PARTIES_BEFORE)
        if "principal_claim_id" in columns:
            op.drop_index(
                "IX_party_adjustments_principal_claim_id",
                table_name="party_adjustments",
            )
            op.drop_constraint(
                "FK_party_adjustments_principal_claim_id",
                "party_adjustments",
                type_="foreignkey",
            )
            op.drop_column("party_adjustments", "principal_claim_id")
    for table in (
        "principal_claim_receipts",
        "principal_claim_lines",
        "principal_claims",
    ):
        if inspector.has_table(table):
            op.drop_table(table)
    if inspector.has_table("promotions"):
        columns = {column["name"] for column in inspector.get_columns("promotions")}
        if "principal_id" in columns:
            if any(
                fk.get("name") == "FK_promotions_principal_id"
                for fk in inspector.get_foreign_keys("promotions")
            ):
                op.drop_constraint(
                    "FK_promotions_principal_id", "promotions", type_="foreignkey"
                )
            op.drop_column("promotions", "principal_id")
        if "principal_share_percent" in columns:
            op.drop_column("promotions", "principal_share_percent")
