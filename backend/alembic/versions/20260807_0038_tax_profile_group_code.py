"""Tax profile group_code for version-safe product mapping.

- Remove effective_from/effective_to from tax_systems (no resolution role)
- Remove effective_from/effective_to from tax_components (versioned via new profile)
- Add group_code to tax_profiles (product maps to this family identifier)
- Replace tax_profile_id FK on products with tax_profile_group_code string

Revision ID: 20260807_0038
Revises: 20260805_0037
Create Date: 2026-08-07

NOTE: Business tables (tax_systems, tax_profiles, products, …) live in per-firm
schemas (firm_shared, wholesale_hub, …), NOT in the platform schema.
This migration discovers every schema that contains tax_systems and applies the
DDL changes there using raw SQL with IF EXISTS / DO $$ guards for idempotency.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260807_0038"
down_revision: str = "20260805_0037"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _firm_schemas(bind: sa.engine.Connection) -> list[str]:
    """Return every schema that contains the tax_systems table."""
    result = bind.execute(
        sa.text(
            "SELECT DISTINCT table_schema "
            "FROM information_schema.tables "
            "WHERE table_name = 'tax_systems' "
            "  AND table_schema NOT IN ('pg_catalog','information_schema')"
        )
    )
    return [row[0] for row in result.fetchall()]


def upgrade() -> None:
    """Apply tax profile group_code for version-safe product mapping."""
    bind = op.get_bind()
    for schema in _firm_schemas(bind):
        s = schema  # alias for f-strings

        # ── tax_systems: drop effective date columns ──────────────────────────
        bind.execute(
            sa.text(
                f'ALTER TABLE "{s}".tax_systems DROP COLUMN IF EXISTS effective_from'
            )
        )
        bind.execute(
            sa.text(f'ALTER TABLE "{s}".tax_systems DROP COLUMN IF EXISTS effective_to')
        )

        # ── tax_components: drop effective date columns ───────────────────────
        bind.execute(
            sa.text(
                f'ALTER TABLE "{s}".tax_components DROP COLUMN IF EXISTS effective_from'
            )
        )
        bind.execute(
            sa.text(
                f'ALTER TABLE "{s}".tax_components DROP COLUMN IF EXISTS effective_to'
            )
        )

        # ── tax_profiles: add group_code + index ──────────────────────────────
        bind.execute(
            sa.text(
                f"""
            DO $$ BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = '{s}'
                      AND table_name   = 'tax_profiles'
                      AND column_name  = 'group_code'
                ) THEN
                    ALTER TABLE "{s}".tax_profiles
                        ADD COLUMN group_code VARCHAR(50);
                END IF;
            END $$;
        """
            )
        )
        bind.execute(
            sa.text(
                f'UPDATE "{s}".tax_profiles SET group_code = code '
                "WHERE group_code IS NULL"
            )
        )
        bind.execute(
            sa.text(
                f"""
            CREATE INDEX IF NOT EXISTS "IX_tax_profiles_firm_group_code"
            ON "{s}".tax_profiles (firm_id, group_code)
        """
            )
        )

        # ── products: swap tax_profile_id FK → tax_profile_group_code string ──
        bind.execute(
            sa.text(
                f"""
            DROP INDEX IF EXISTS "{s}"."IX_products_firm_tax_profile"
        """
            )
        )
        bind.execute(
            sa.text(
                f"""
            ALTER TABLE "{s}".products
                DROP CONSTRAINT IF EXISTS "FK_products_tax_profile"
        """
            )
        )
        bind.execute(
            sa.text(
                f"""
            ALTER TABLE "{s}".products
                DROP COLUMN IF EXISTS tax_profile_id
        """
            )
        )
        bind.execute(
            sa.text(
                f"""
            DO $$ BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = '{s}'
                      AND table_name   = 'products'
                      AND column_name  = 'tax_profile_group_code'
                ) THEN
                    ALTER TABLE "{s}".products
                        ADD COLUMN tax_profile_group_code VARCHAR(50);
                END IF;
            END $$;
        """
            )
        )
        bind.execute(
            sa.text(
                f"""
            CREATE INDEX IF NOT EXISTS "IX_products_firm_tax_group_code"
            ON "{s}".products (firm_id, tax_profile_group_code)
        """
            )
        )


def downgrade() -> None:
    """Reverse tax profile group_code for version-safe product mapping."""
    bind = op.get_bind()
    for schema in _firm_schemas(bind):
        s = schema

        # ── products: restore tax_profile_id ──────────────────────────────────
        bind.execute(
            sa.text(
                f"""
            DROP INDEX IF EXISTS "{s}"."IX_products_firm_tax_group_code"
        """
            )
        )
        bind.execute(
            sa.text(
                f"""
            ALTER TABLE "{s}".products
                DROP COLUMN IF EXISTS tax_profile_group_code
        """
            )
        )
        bind.execute(
            sa.text(
                f"""
            DO $$ BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = '{s}'
                      AND table_name   = 'products'
                      AND column_name  = 'tax_profile_id'
                ) THEN
                    ALTER TABLE "{s}".products
                        ADD COLUMN tax_profile_id UUID;
                END IF;
            END $$;
        """
            )
        )
        bind.execute(
            sa.text(
                f"""
            DO $$ BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.table_constraints
                    WHERE constraint_schema = '{s}'
                      AND table_name        = 'products'
                      AND constraint_name   = 'FK_products_tax_profile'
                ) THEN
                    ALTER TABLE "{s}".products
                        ADD CONSTRAINT "FK_products_tax_profile"
                        FOREIGN KEY (tax_profile_id)
                        REFERENCES "{s}".tax_profiles (id)
                        ON DELETE RESTRICT;
                END IF;
            END $$;
        """
            )
        )
        bind.execute(
            sa.text(
                f"""
            CREATE INDEX IF NOT EXISTS "IX_products_firm_tax_profile"
            ON "{s}".products (firm_id, tax_profile_id)
        """
            )
        )

        # ── tax_profiles: drop group_code ─────────────────────────────────────
        bind.execute(
            sa.text(
                f"""
            DROP INDEX IF EXISTS "{s}"."IX_tax_profiles_firm_group_code"
        """
            )
        )
        bind.execute(
            sa.text(f'ALTER TABLE "{s}".tax_profiles DROP COLUMN IF EXISTS group_code')
        )

        # ── tax_components: restore effective date columns ────────────────────
        bind.execute(
            sa.text(
                f"""
            DO $$ BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = '{s}'
                      AND table_name   = 'tax_components'
                      AND column_name  = 'effective_from'
                ) THEN
                    ALTER TABLE "{s}".tax_components ADD COLUMN effective_from DATE;
                    ALTER TABLE "{s}".tax_components ADD COLUMN effective_to   DATE;
                END IF;
            END $$;
        """
            )
        )

        # ── tax_systems: restore effective date columns ───────────────────────
        bind.execute(
            sa.text(
                f"""
            DO $$ BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = '{s}'
                      AND table_name   = 'tax_systems'
                      AND column_name  = 'effective_from'
                ) THEN
                    ALTER TABLE "{s}".tax_systems ADD COLUMN effective_from DATE;
                    ALTER TABLE "{s}".tax_systems ADD COLUMN effective_to   DATE;
                END IF;
            END $$;
        """
            )
        )
