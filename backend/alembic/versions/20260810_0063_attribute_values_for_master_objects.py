"""Give customers, vendors, branches, warehouses, tax profiles and units custom fields.

``AttributeEntityType`` declared PRODUCT, CUSTOMER, VENDOR, BRANCH and WAREHOUSE
from the start, but only ``product_attribute_values`` was ever created. The other
four could be targeted by an ``AttributeDefinition`` and had nowhere to store a
value, so custom fields were unusable on four of the five objects that claimed to
support them. This adds the missing tables and two new targets, tax profiles and
units of measure.

Units are the odd one out and their table is shaped differently. ``uoms`` carries
no ``firm_id`` and one row serves every firm sharing a store, so the firm is part
of this table's identity: uniqueness is (firm, unit, attribute) rather than
(unit, attribute). Keying it on the unit alone would let whichever firm saved
first claim an attribute and lock every other firm in the store out of setting
it, and reads that filtered only on the unit would hand one firm another firm's
annotations.

**These are firm-owned tables.** They live in ``firm_shared`` and in every
dedicated firm schema and database -- not in ``platform`` -- so this migration
must be run against every firm target, not just the default schema. Enumerate
them from ``firms`` and ``firm_storage_mappings`` rather than trusting a list.

Cross-schema foreign keys are declared only when the target is present:
``firms`` exists solely in the platform schema, so a firm store gets the column
without the constraint, following ``_external_fk`` in ``20260809_0042``. Every
step checks before it acts, because firm schemas are partly built by
``Base.metadata.create_all`` from the sample-data and tenancy-reset scripts and
so may already hold objects while ``alembic_version`` reads older.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260810_0063"
down_revision: str | Sequence[str] | None = "20260810_0062"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: (table, owner column, owner table). Order is irrelevant; each is independent.
_TABLES: tuple[tuple[str, str, str], ...] = (
    ("customer_attribute_values", "customer_id", "customers"),
    ("vendor_attribute_values", "vendor_id", "vendors"),
    ("branch_attribute_values", "branch_id", "branches"),
    ("warehouse_attribute_values", "warehouse_id", "warehouses"),
    ("tax_profile_attribute_values", "tax_profile_id", "tax_profiles"),
    ("uom_attribute_values", "uom_id", "uoms"),
)

#: The shared catalogue, whose values are keyed by firm as well as by owner.
_SHARED_OWNER = "uom_attribute_values"


def _base_columns() -> list[sa.Column[object]]:
    """Return the shared BaseEntity columns."""
    return [
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
        # Left unnamed on purpose: constraint names are per schema, so a shared
        # literal would collide across these six tables, and the naming
        # convention carries no "pk" key -- `Base.metadata.create_all` lets
        # PostgreSQL derive `<table>_pkey`, and this must produce the same.
        sa.PrimaryKeyConstraint("id"),
    ]


def upgrade() -> None:
    """Create one value table per newly supported object, where it belongs."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())

    # Without the catalogue there is nothing for a value to point at, which is
    # how the platform schema correctly ends up with none of these tables.
    if "attribute_definitions" not in existing:
        return

    for table, owner_column, owner_table in _TABLES:
        if table in existing or owner_table not in existing:
            continue

        constraints: list[sa.schema.SchemaItem] = [
            sa.ForeignKeyConstraint(
                ["attribute_definition_id"],
                ["attribute_definitions.id"],
                name=f"FK_{table}_attribute_definition_id",
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                [owner_column],
                [f"{owner_table}.id"],
                name=f"FK_{table}_{owner_column}",
                ondelete="CASCADE",
            ),
        ]
        # `firms` lives only in the platform schema; a firm store keeps the
        # column and drops the constraint rather than failing to migrate.
        if "firms" in existing:
            constraints.append(
                sa.ForeignKeyConstraint(
                    ["firm_id"], ["firms.id"], name=f"FK_{table}_firm_id"
                )
            )

        if table == _SHARED_OWNER:
            constraints.append(
                sa.UniqueConstraint(
                    "firm_id",
                    owner_column,
                    "attribute_definition_id",
                    name=f"UQ_{table}_firm_uom_attribute",
                )
            )
        else:
            constraints.append(
                sa.UniqueConstraint(
                    owner_column,
                    "attribute_definition_id",
                    name=f"UQ_{table}_owner_attribute",
                )
            )

        op.create_table(
            table,
            *_base_columns(),
            sa.Column("firm_id", sa.Uuid(), nullable=False),
            sa.Column(owner_column, sa.Uuid(), nullable=False),
            sa.Column("attribute_definition_id", sa.Uuid(), nullable=False),
            sa.Column("value_text", sa.Text(), nullable=True),
            sa.Column("value_number", sa.Numeric(18, 6), nullable=True),
            sa.Column("value_date", sa.Date(), nullable=True),
            sa.Column("value_boolean", sa.Boolean(), nullable=True),
            *constraints,
        )

        # Typed value columns are indexed with the firm so list filters and
        # reports can use them; storing values as JSON is what made the
        # predecessor unfilterable.
        for name, columns in (
            (f"IX_{table}_firm_id", ["firm_id"]),
            (f"IX_{table}_{owner_column}", [owner_column]),
            (
                f"IX_{table}_attribute_definition_id",
                ["attribute_definition_id"],
            ),
            (f"IX_{table}_firm_text", ["firm_id", "value_text"]),
            (f"IX_{table}_firm_number", ["firm_id", "value_number"]),
            (f"IX_{table}_firm_date", ["firm_id", "value_date"]),
        ):
            op.create_index(name, table, columns)


def downgrade() -> None:
    """Drop the value tables, and with them any custom field data they hold."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())
    for table, _owner_column, _owner_table in reversed(_TABLES):
        if table in existing:
            op.drop_table(table)
