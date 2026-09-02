"""Give every timestamp column back the default the ORM says it has.

`TimestampMixin` declares `created_at` and `updated_at` with
``server_default=func.now()``, so `Base.metadata.create_all` builds them with a
default and nothing has to supply a value. A hand-written ``op.create_table``
that spells the two columns out without one builds a table that **cannot be
inserted into at all**: the first write raises NotNullViolation, because
SQLAlchemy leaves the column out of the INSERT and expects the database to
fill it.

That is invisible to the unit suite, which builds its schema from the ORM and
therefore always has the default the migration forgot. It was found by driving
a real firm, where creating a commission slab failed on the first insert.

The twelve `tax` tables are in the same state and have been since they were
written. They work only because `TaxFrameworkService` passes ``created_at=now``
by hand on every insert -- so the tables are usable today and the next line of
code that inserts a tax row the ordinary way would fail. This closes the whole
class rather than the one table that surfaced it.

Data-driven rather than a list somebody maintains: it asks the catalogue which
NOT NULL timestamp columns have no default and sets one on each, so a table
this misses is a table that does not exist. Idempotent, and skipped on any
dialect that cannot alter a default in place.

`tests/integration/test_multi_schema_tenancy.py::
test_every_deployed_table_can_be_inserted_into` is the guard.

Revision ID: 20260903_0114
Revises: 20260903_0113
Create Date: 2026-09-03

"""

import sqlalchemy as sa

from alembic import op

revision = "20260903_0114"
down_revision = "20260903_0113"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Set CURRENT_TIMESTAMP on every undefaulted timestamp column."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    schema = bind.execute(sa.text("SELECT current_schema()")).scalar()
    undefaulted = bind.execute(
        sa.text(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = :schema
              AND column_name IN ('created_at', 'updated_at')
              AND is_nullable = 'NO'
              AND column_default IS NULL
            ORDER BY table_name, column_name
            """
        ),
        {"schema": schema},
    ).all()
    for table_name, column_name in undefaulted:
        op.execute(
            f'ALTER TABLE "{schema}"."{table_name}" '  # noqa: S608
            f'ALTER COLUMN "{column_name}" SET DEFAULT CURRENT_TIMESTAMP'
        )


def downgrade() -> None:
    """Deliberately does nothing.

    Dropping the defaults again would restore tables that cannot be inserted
    into, and there is no record of which ones were undefaulted before this
    ran. A migration whose reverse re-breaks the database is worse than one
    that does not reverse.
    """
