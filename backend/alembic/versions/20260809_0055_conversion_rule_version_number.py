"""Separate a conversion rule's published version from its concurrency counter.

``ConversionRule`` declared a business column named ``version``, which is the
name ``BaseEntity`` gives the mapper's ``version_id_col``. The two became one
column: every ORM update incremented the rule's published version, the number
documents store in ``conversion_version`` to identify the factor they converted
with, and the number ``UQ_uom_conversion_rules_unique_version`` keys on. Editing
a rule's ``reason`` silently moved it from version 1 to version 2.

The business column becomes ``version_number`` (the name ``tax`` already uses for
this) and ``version`` is recreated as the counter, starting at zero.

``uom_conversion_rules`` is firm-owned: it exists in every firm store and not in
``platform``, so this is a no-op there.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260809_0055"
down_revision: str | Sequence[str] | None = "20260809_0054"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "uom_conversion_rules"
_CONSTRAINT = "UQ_uom_conversion_rules_unique_version"


def upgrade() -> None:
    """Rename the business version and restore the concurrency counter."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    constraints = {c["name"] for c in inspector.get_unique_constraints(_TABLE)}

    if _CONSTRAINT in constraints:
        op.drop_constraint(_CONSTRAINT, _TABLE, type_="unique")
    if "version_number" not in columns:
        op.alter_column(_TABLE, "version", new_column_name="version_number")
        columns.discard("version")
        columns.add("version_number")
    if "version" not in columns:
        op.add_column(
            _TABLE,
            sa.Column(
                "version",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )
    op.create_unique_constraint(
        _CONSTRAINT,
        _TABLE,
        ["firm_id", "product_id", "from_uom_id", "to_uom_id", "version_number"],
    )


def downgrade() -> None:
    """Fold the counter back into the business version column."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    constraints = {c["name"] for c in inspector.get_unique_constraints(_TABLE)}

    if _CONSTRAINT in constraints:
        op.drop_constraint(_CONSTRAINT, _TABLE, type_="unique")
    if "version" in columns:
        op.drop_column(_TABLE, "version")
    if "version_number" in columns:
        op.alter_column(_TABLE, "version_number", new_column_name="version")
    op.create_unique_constraint(
        _CONSTRAINT,
        _TABLE,
        ["firm_id", "product_id", "from_uom_id", "to_uom_id", "version"],
    )
