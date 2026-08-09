"""Let a firm nominate the accounts its documents post to.

Automatic GL posting has never existed. The three ``*_accounting_events`` tables
hold hardcoded account *names* and narration reading "Placeholder accounting
event for …", and an earlier consumer that guessed accounts by matching on their
name was removed.

Which account a firm's receivables or cost of goods sold lands in is that firm's
decision and differs between firms sharing a chart of accounts, so it belongs in
data. This table maps a posting *purpose* onto a nominated ledger account; the
posting rules stay in code.

No seed. An unmapped purpose is refused by name at posting time, which is the
intended behaviour: a journal posted to a guessed account is worse than a
journal refused.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260809_0053"
down_revision: str | Sequence[str] | None = "20260809_0052"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the firm control-account mapping."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("firm_control_accounts"):
        return
    if not inspector.has_table("ledger_accounts"):
        # Finance is firm-owned; nothing to map against in the platform store.
        return

    constraints: list[sa.schema.SchemaItem] = [
        sa.ForeignKeyConstraint(
            ["ledger_account_id"], ["ledger_accounts.id"], ondelete="RESTRICT"
        )
    ]
    # firms exists only in the platform schema.
    if inspector.has_table("firms"):
        constraints.append(sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]))

    op.create_table(
        "firm_control_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(length=40), nullable=False),
        sa.Column("ledger_account_id", sa.Uuid(), nullable=False),
        *constraints,
        sa.PrimaryKeyConstraint("id", name="PK_firm_control_accounts"),
        sa.UniqueConstraint(
            "firm_id", "purpose", name="UQ_firm_control_accounts_firm_purpose"
        ),
    )
    op.create_index(
        "IX_firm_control_accounts_firm", "firm_control_accounts", ["firm_id"]
    )
    op.create_index(
        "IX_firm_control_accounts_firm_id", "firm_control_accounts", ["firm_id"]
    )


def downgrade() -> None:
    """Drop the firm control-account mapping."""
    bind = op.get_bind()
    if sa.inspect(bind).has_table("firm_control_accounts"):
        op.drop_table("firm_control_accounts")
