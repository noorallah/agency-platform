"""A user's date format defaults to dd-MM-yyyy (backlog 73, My preferences).

``user_preferences.date_format`` defaulted to ``yyyy-MM-dd`` from the day it
was created, and no screen ever offered a choice, so every stored value is
the default rather than a decision. The phase 2 screens write
``dd-MM-yyyy``, the Indian convention; now that My preferences applies the
stored format, the old default would turn every date on every screen into
ISO. Rows still at it move to the new one -- no row can hold a choice yet.

Platform-owned; a store without the table is skipped. Idempotent.

Revision ID: 20261004_0299
Revises: 20261003_0298
Create Date: 2026-10-04

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261004_0299"
down_revision: str | Sequence[str] | None = "20261003_0298"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Change the column default and move rows still at the old one."""
    if not sa.inspect(op.get_bind()).has_table("user_preferences"):
        return
    op.alter_column("user_preferences", "date_format", server_default="dd-MM-yyyy")
    op.execute(
        "UPDATE user_preferences SET date_format = 'dd-MM-yyyy' "
        "WHERE date_format = 'yyyy-MM-dd'"
    )


def downgrade() -> None:
    """Restore the ISO default; stored values are left as they are."""
    if not sa.inspect(op.get_bind()).has_table("user_preferences"):
        return
    op.alter_column("user_preferences", "date_format", server_default="yyyy-MM-dd")
