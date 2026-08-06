"""Tax profile group_code for version-safe product mapping.

- Remove effective_from/effective_to from tax_systems (no resolution role)
- Remove effective_from/effective_to from tax_components (versioned via new profile)
- Add group_code to tax_profiles (product maps to this family identifier)
- Replace tax_profile_id FK on products with tax_profile_group_code string

Revision ID: 20260807_0038
Revises: 20260805_0037
Create Date: 2026-08-07
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260807_0038"
down_revision: str = "20260805_0037"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # ── tax_systems: drop effective date columns ──────────────────────────────
    op.drop_column("tax_systems", "effective_from")
    op.drop_column("tax_systems", "effective_to")

    # ── tax_components: drop effective date columns ───────────────────────────
    op.drop_column("tax_components", "effective_from")
    op.drop_column("tax_components", "effective_to")

    # ── tax_profiles: add group_code + index ──────────────────────────────────
    op.add_column(
        "tax_profiles",
        sa.Column("group_code", sa.String(50), nullable=True),
    )
    # Back-fill: default group_code = code for all existing profiles
    op.execute(
        "UPDATE tax_profiles SET group_code = code WHERE group_code IS NULL"
    )
    op.create_index(
        "IX_tax_profiles_firm_group_code",
        "tax_profiles",
        ["firm_id", "group_code"],
    )

    # ── products: swap tax_profile_id FK → tax_profile_group_code string ─────
    # Drop the old FK index first, then the FK constraint, then the column
    op.drop_index("IX_products_firm_tax_profile", table_name="products")
    with op.batch_alter_table("products") as batch_op:
        batch_op.drop_constraint(
            "products_tax_profile_id_fkey",
            type_="foreignkey",
        )
        batch_op.drop_column("tax_profile_id")
        batch_op.add_column(
            sa.Column("tax_profile_group_code", sa.String(50), nullable=True)
        )
    op.create_index(
        "IX_products_firm_tax_group_code",
        "products",
        ["firm_id", "tax_profile_group_code"],
    )


def downgrade() -> None:
    # ── products: restore tax_profile_id ─────────────────────────────────────
    op.drop_index("IX_products_firm_tax_group_code", table_name="products")
    with op.batch_alter_table("products") as batch_op:
        batch_op.drop_column("tax_profile_group_code")
        batch_op.add_column(
            sa.Column(
                "tax_profile_id",
                sa.dialects.postgresql.UUID(as_uuid=True),
                nullable=True,
            )
        )
        batch_op.create_foreign_key(
            "products_tax_profile_id_fkey",
            "tax_profiles",
            ["tax_profile_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    op.create_index(
        "IX_products_firm_tax_profile", "products", ["firm_id", "tax_profile_id"]
    )

    # ── tax_profiles: drop group_code ─────────────────────────────────────────
    op.drop_index("IX_tax_profiles_firm_group_code", table_name="tax_profiles")
    op.drop_column("tax_profiles", "group_code")

    # ── tax_components: restore effective date columns ────────────────────────
    op.add_column("tax_components", sa.Column("effective_from", sa.Date(), nullable=True))
    op.add_column("tax_components", sa.Column("effective_to", sa.Date(), nullable=True))

    # ── tax_systems: restore effective date columns ───────────────────────────
    op.add_column("tax_systems", sa.Column("effective_from", sa.Date(), nullable=True))
    op.add_column("tax_systems", sa.Column("effective_to", sa.Date(), nullable=True))
