"""Enforce append-only audit logs in every schema, not just the platform one.

Revision ``20260801_0010`` created ``reject_audit_log_mutation`` and
``TR_audit_logs_append_only`` without a schema qualifier, so they were installed
only in the schema Alembic happened to target. Firm schemas -- which hold the
audit trail for all business activity -- were left writable: their rows could be
updated or deleted with no error.

This revision installs the guard in every schema that has an ``audit_logs``
table, and is safe to replay.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260809_0043"
down_revision: str | Sequence[str] | None = "20260809_0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FUNCTION = "reject_audit_log_mutation"
_TRIGGER = "TR_audit_logs_append_only"


def _audit_schemas(bind: sa.engine.Connection) -> list[str]:
    """Return every schema in this database that owns an audit_logs table."""
    result = bind.execute(
        sa.text(
            "SELECT DISTINCT table_schema "
            "FROM information_schema.tables "
            "WHERE table_name = 'audit_logs' "
            "  AND table_schema NOT IN ('pg_catalog','information_schema') "
            "ORDER BY 1"
        )
    )
    return [row[0] for row in result.fetchall()]


def upgrade() -> None:
    """Install the append-only guard in every schema holding audit_logs."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # SQLAlchemy event listeners on the AuditLog model cover other backends.
        return
    for schema in _audit_schemas(bind):
        bind.execute(
            sa.text(
                f'CREATE OR REPLACE FUNCTION "{schema}".{_FUNCTION}() '
                "RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN "
                "RAISE EXCEPTION 'audit_logs is append-only'; END; $$"
            )
        )
        bind.execute(
            sa.text(f'DROP TRIGGER IF EXISTS "{_TRIGGER}" ON "{schema}".audit_logs')
        )
        # 20260801_0010 created the trigger with an unquoted name, which
        # PostgreSQL folded to lower case. Drop that spelling too so a replay
        # cannot leave two guards attached to the same table.
        bind.execute(
            sa.text(
                f'DROP TRIGGER IF EXISTS {_TRIGGER.lower()} ON "{schema}".audit_logs'
            )
        )
        bind.execute(
            sa.text(
                f'CREATE TRIGGER "{_TRIGGER}" '
                f'BEFORE UPDATE OR DELETE ON "{schema}".audit_logs '
                f'FOR EACH ROW EXECUTE FUNCTION "{schema}".{_FUNCTION}()'
            )
        )


def downgrade() -> None:
    """Remove the guard from every schema that carries it."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for schema in _audit_schemas(bind):
        bind.execute(
            sa.text(f'DROP TRIGGER IF EXISTS "{_TRIGGER}" ON "{schema}".audit_logs')
        )
        bind.execute(sa.text(f'DROP FUNCTION IF EXISTS "{schema}".{_FUNCTION}()'))
