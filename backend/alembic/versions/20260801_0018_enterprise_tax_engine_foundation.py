"""Phase 15A enterprise tax engine foundation."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260801_0018"
down_revision: str | Sequence[str] | None = "20260801_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tax_rules",
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("country_id", sa.Uuid(), nullable=True),
        sa.Column("business_profile_id", sa.Uuid(), nullable=True),
        sa.Column("tax_profile_id", sa.Uuid(), nullable=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="DRAFT"
        ),
        sa.Column("version_group_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("supersedes_rule_id", sa.Uuid(), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(
            ["business_profile_id"], ["business_profiles.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["country_id"], ["geo_countries.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.ForeignKeyConstraint(
            ["supersedes_rule_id"], ["tax_rules.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["tax_profile_id"], ["tax_profiles.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "firm_id", "code", "version_number", name="UQ_tax_rules_firm_code_version"
        ),
    )
    op.create_index(
        "IX_tax_rules_firm_priority", "tax_rules", ["firm_id", "priority"], unique=False
    )
    op.create_index(
        "IX_tax_rules_firm_status", "tax_rules", ["firm_id", "status"], unique=False
    )
    op.create_index(
        "IX_tax_rules_firm_version_group",
        "tax_rules",
        ["firm_id", "version_group_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tax_rules_firm_id"), "tax_rules", ["firm_id"], unique=False
    )
    op.create_index(
        op.f("ix_tax_rules_country_id"), "tax_rules", ["country_id"], unique=False
    )
    op.create_index(
        op.f("ix_tax_rules_tax_profile_id"),
        "tax_rules",
        ["tax_profile_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tax_rules_version_group_id"),
        "tax_rules",
        ["version_group_id"],
        unique=False,
    )

    op.create_table(
        "tax_rule_conditions",
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("tax_rule_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("field_key", sa.String(length=80), nullable=False),
        sa.Column("operator", sa.String(length=30), nullable=False),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("value_number", sa.Numeric(18, 4), nullable=True),
        sa.Column("value_date", sa.Date(), nullable=True),
        sa.Column("value_boolean", sa.Boolean(), nullable=True),
        sa.Column("value_json", sa.JSON(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.ForeignKeyConstraint(["tax_rule_id"], ["tax_rules.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "IX_tax_rule_conditions_firm_rule",
        "tax_rule_conditions",
        ["firm_id", "tax_rule_id"],
        unique=False,
    )
    op.create_index(
        "IX_tax_rule_conditions_firm_field",
        "tax_rule_conditions",
        ["firm_id", "field_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tax_rule_conditions_firm_id"),
        "tax_rule_conditions",
        ["firm_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tax_rule_conditions_tax_rule_id"),
        "tax_rule_conditions",
        ["tax_rule_id"],
        unique=False,
    )

    op.create_table(
        "tax_rule_actions",
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("tax_rule_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("action_type", sa.String(length=40), nullable=False),
        sa.Column("target_tax_profile_id", sa.Uuid(), nullable=True),
        sa.Column("target_tax_component_id", sa.Uuid(), nullable=True),
        sa.Column("percentage_override", sa.Numeric(8, 4), nullable=True),
        sa.Column(
            "parameters", sa.JSON(), nullable=False, server_default=sa.text("'{}'")
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]),
        sa.ForeignKeyConstraint(
            ["target_tax_component_id"], ["tax_components.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["target_tax_profile_id"], ["tax_profiles.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["tax_rule_id"], ["tax_rules.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "IX_tax_rule_actions_firm_rule",
        "tax_rule_actions",
        ["firm_id", "tax_rule_id"],
        unique=False,
    )
    op.create_index(
        "IX_tax_rule_actions_firm_type",
        "tax_rule_actions",
        ["firm_id", "action_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tax_rule_actions_firm_id"),
        "tax_rule_actions",
        ["firm_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tax_rule_actions_tax_rule_id"),
        "tax_rule_actions",
        ["tax_rule_id"],
        unique=False,
    )

    op.create_table(
        "tax_rule_execution_logs",
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("execution_mode", sa.String(length=30), nullable=False),
        sa.Column("transaction_type", sa.String(length=40), nullable=False),
        sa.Column("country_id", sa.Uuid(), nullable=True),
        sa.Column("business_profile_id", sa.Uuid(), nullable=True),
        sa.Column("tax_profile_id", sa.Uuid(), nullable=True),
        sa.Column("matched_rule_id", sa.Uuid(), nullable=True),
        sa.Column("applied_tax_profile_id", sa.Uuid(), nullable=True),
        sa.Column(
            "input_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")
        ),
        sa.Column(
            "evaluation_trace",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "result_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(
            ["applied_tax_profile_id"],
            ["tax_profiles.id"],
            name="FK_tax_rule_execution_logs_applied_tax_profile_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["business_profile_id"],
            ["business_profiles.id"],
            name="FK_tax_rule_execution_logs_business_profile_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["country_id"],
            ["geo_countries.id"],
            name="FK_tax_rule_execution_logs_country_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["firm_id"],
            ["firms.id"],
            name="FK_tax_rule_execution_logs_firm_id",
        ),
        sa.ForeignKeyConstraint(
            ["matched_rule_id"],
            ["tax_rules.id"],
            name="FK_tax_rule_execution_logs_matched_rule_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tax_profile_id"],
            ["tax_profiles.id"],
            name="FK_tax_rule_execution_logs_tax_profile_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "IX_tax_rule_execution_logs_firm_mode",
        "tax_rule_execution_logs",
        ["firm_id", "execution_mode"],
        unique=False,
    )
    op.create_index(
        "IX_tax_rule_execution_logs_firm_rule",
        "tax_rule_execution_logs",
        ["firm_id", "matched_rule_id"],
        unique=False,
    )
    op.create_index(
        "IX_tax_rule_execution_logs_firm_created",
        "tax_rule_execution_logs",
        ["firm_id", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tax_rule_execution_logs_firm_id"),
        "tax_rule_execution_logs",
        ["firm_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_tax_rule_execution_logs_firm_id"), table_name="tax_rule_execution_logs"
    )
    op.drop_index(
        "IX_tax_rule_execution_logs_firm_created", table_name="tax_rule_execution_logs"
    )
    op.drop_index(
        "IX_tax_rule_execution_logs_firm_rule", table_name="tax_rule_execution_logs"
    )
    op.drop_index(
        "IX_tax_rule_execution_logs_firm_mode", table_name="tax_rule_execution_logs"
    )
    op.drop_table("tax_rule_execution_logs")

    op.drop_index(
        op.f("ix_tax_rule_actions_tax_rule_id"), table_name="tax_rule_actions"
    )
    op.drop_index(op.f("ix_tax_rule_actions_firm_id"), table_name="tax_rule_actions")
    op.drop_index("IX_tax_rule_actions_firm_type", table_name="tax_rule_actions")
    op.drop_index("IX_tax_rule_actions_firm_rule", table_name="tax_rule_actions")
    op.drop_table("tax_rule_actions")

    op.drop_index(
        op.f("ix_tax_rule_conditions_tax_rule_id"), table_name="tax_rule_conditions"
    )
    op.drop_index(
        op.f("ix_tax_rule_conditions_firm_id"), table_name="tax_rule_conditions"
    )
    op.drop_index("IX_tax_rule_conditions_firm_field", table_name="tax_rule_conditions")
    op.drop_index("IX_tax_rule_conditions_firm_rule", table_name="tax_rule_conditions")
    op.drop_table("tax_rule_conditions")

    op.drop_index(op.f("ix_tax_rules_version_group_id"), table_name="tax_rules")
    op.drop_index(op.f("ix_tax_rules_tax_profile_id"), table_name="tax_rules")
    op.drop_index(op.f("ix_tax_rules_country_id"), table_name="tax_rules")
    op.drop_index(op.f("ix_tax_rules_firm_id"), table_name="tax_rules")
    op.drop_index("IX_tax_rules_firm_version_group", table_name="tax_rules")
    op.drop_index("IX_tax_rules_firm_status", table_name="tax_rules")
    op.drop_index("IX_tax_rules_firm_priority", table_name="tax_rules")
    op.drop_table("tax_rules")
