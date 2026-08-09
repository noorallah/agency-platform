"""Rebuild the sales-invoice tables, which never matched the ORM.

The six ``sales_invoice*`` tables in the firm stores were missing the
``BaseEntity`` columns ``version``, ``deleted_at`` and ``deleted_by``, plus
module columns the service writes on every save: ``note``/``note_type``,
``mime_type``/``attachment_kind``, and ``account_name``/``direction``/
``narration``/``source_line_id``. Any insert would have failed.

Nothing had noticed because the module's API was unreachable — its router
enforced permission codes that were never seeded — and it had no test. Every one
of the tables is empty in every deployed store, so this rebuilds them from the
ORM rather than patching column by column.

The rebuild is guarded twice: it only runs where the stale shape is detected
(no ``version`` column) and only when the table holds no rows, so it can never
discard data on replay.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# alembic/env.py imports every model module, so Base.metadata already describes
# the whole schema by the time a revision runs.
from app.core.database.base import Base
from app.sales_invoice.models import sales_invoice  # noqa: F401

revision: str = "20260809_0051"
down_revision: str | Sequence[str] | None = "20260809_0050"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Children first, so foreign keys drop cleanly.
TABLES = (
    "sales_invoice_accounting_events",
    "sales_invoice_attachments",
    "sales_invoice_notes",
    "sales_invoice_sources",
    "sales_invoice_lines",
    "sales_invoices",
)


def upgrade() -> None:
    """Recreate any sales-invoice table still carrying the pre-BaseEntity shape."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    stale: list[str] = []
    for name in TABLES:
        if not inspector.has_table(name):
            # Absent entirely, either because this revision was reversed or
            # because the store predates the module. Create it below.
            stale.append(name)
            continue
        columns = {column["name"] for column in inspector.get_columns(name)}
        if "version" in columns:
            continue
        rows = bind.execute(sa.text(f'SELECT COUNT(*) FROM "{name}"')).scalar() or 0
        if rows:
            raise RuntimeError(
                f"{name} has the stale shape but holds {rows} rows; "
                "repair it by hand rather than rebuilding."
            )
        stale.append(name)

    if not stale:
        return

    for name in stale:
        if inspector.has_table(name):
            op.drop_table(name)
    present = set(inspector.get_table_names()) | set(stale)
    staging = _staging_metadata(present)
    # Parents first on the way back in.
    for name in reversed(TABLES):
        if name in stale:
            staging.tables[name].create(bind)


def _staging_metadata(present: set[str]) -> sa.MetaData:
    """Copy the ORM schema, dropping foreign keys this store cannot satisfy.

    ``firms`` lives only in the platform schema, so emitting the ORM definition
    verbatim into a firm store fails with UndefinedTable. Every table is copied
    so that references to tables which *are* present still resolve; only the
    unsatisfiable ones are removed.

    Args:
        present: Table names available in the current store.

    Returns:
        A detached metadata safe to create from in the current store.

    """
    staging = sa.MetaData()
    for table in Base.metadata.tables.values():
        table.to_metadata(staging)
    for name in TABLES:
        table = staging.tables[name]
        for constraint in list(table.foreign_key_constraints):
            referred = constraint.elements[0].target_fullname.split(".")[0]
            if referred not in present:
                table.constraints.discard(constraint)
    return staging


def downgrade() -> None:
    """Drop the rebuilt tables.

    The previous shape could not store what the service writes, so it is not
    worth reconstructing; the tables were empty when this revision ran.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for name in TABLES:
        if inspector.has_table(name):
            op.drop_table(name)
