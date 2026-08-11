"""Let a firm name the server its storage lives on, and record when it was built.

``firm_storage_mappings`` described *what* a firm's storage is called --
deployment mode, database, schema -- and never *where* it is. The connection was
always rebuilt from the platform database's own host and credentials, so a
"dedicated database" firm was a second database on the platform server and
nothing else. ``AGENCY_TENANCY_CONNECTION_PROFILES`` has existed as configuration
the whole time and was discarded on the first line of both consumers.

``connection_profile`` names an entry in that configuration. NULL means the
platform server, which is what every existing firm is, so no existing row
changes meaning.

``provisioned_at`` and ``provisioning_error`` exist because building dedicated
storage stops happening inline during firm creation. A remote server that is
slow or unreachable must not fail the creation of the firm record, so the firm
now exists before its tables do, and the tenant resolver refuses to route to a
firm that has not been provisioned.

**Every existing dedicated mapping is backfilled as provisioned.** Their storage
was built inline at creation under the old behaviour, so leaving them NULL would
switch on the new readiness gate against firms that are already serving
traffic -- the migration would take working firms offline. Only rows still at the
default are touched, so a replay cannot overwrite a real value.

``firm_storage_mappings`` is firm-registry data and lives only in the platform
schema.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260810_0064"
down_revision: str | Sequence[str] | None = "20260810_0063"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "firm_storage_mappings"


def upgrade() -> None:
    """Add the connection target and provisioning state columns."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # The firm registry exists only in the platform schema.
    if not inspector.has_table(_TABLE):
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if "connection_profile" not in columns:
        op.add_column(
            _TABLE, sa.Column("connection_profile", sa.String(length=64), nullable=True)
        )
    if "provisioned_at" not in columns:
        op.add_column(
            _TABLE,
            sa.Column("provisioned_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "provisioning_error" not in columns:
        op.add_column(_TABLE, sa.Column("provisioning_error", sa.Text(), nullable=True))

    # Anything that already exists was provisioned inline when it was created.
    # Stamp created_at rather than now(): it is the closest true record of when
    # that storage was built, and it keeps a replay idempotent.
    op.execute(
        sa.text(
            f"UPDATE {_TABLE} SET provisioned_at = created_at "  # noqa: S608
            "WHERE provisioned_at IS NULL"
        )
    )


def downgrade() -> None:
    """Drop the connection target and provisioning state columns."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    for column in ("provisioning_error", "provisioned_at", "connection_profile"):
        if column in columns:
            op.drop_column(_TABLE, column)
