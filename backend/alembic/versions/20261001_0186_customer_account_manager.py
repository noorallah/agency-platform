"""A customer's account manager (backlog 67 row 2).

``customers.salesman_id``: the firm member who looks after the customer, and
the salesman a sales document raised for them takes when it names none. A
platform user id with no foreign key -- ``users`` lives only in the platform
store -- checked through ``FirmMetadataReader`` when it is set. NULL on every
existing customer, which leaves documents to the territory's salesperson as
before.

Idempotent; firm-owned, so it runs per store
(``scripts/migrate_all_stores.py``).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261001_0186"
down_revision: str | Sequence[str] | None = "20261001_0184"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the column where customers live."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("customers"):
        return
    columns = {item["name"] for item in inspector.get_columns("customers")}
    if "salesman_id" not in columns:
        op.add_column("customers", sa.Column("salesman_id", UUIDType(), nullable=True))


def downgrade() -> None:
    """Drop it."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("customers"):
        return
    columns = {item["name"] for item in inspector.get_columns("customers")}
    if "salesman_id" in columns:
        op.drop_column("customers", "salesman_id")
