"""Optional user profile enrichment fields (Phase 9 UX sprint).

Adds nullable, additive columns to ``users`` for HR-style profile data
(contact, employment, address, and document metadata). None of these
columns are consulted by authentication or authorization, which continue
to rely solely on ``email``/``password_hash``/role assignments.

Revision ID: 20260803_0023
Revises: 20260802_0022
Create Date: 2026-08-03
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260803_0023"
down_revision: str | Sequence[str] | None = "20260802_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_SCALAR_COLUMNS: list[sa.Column[object]] = [
    sa.Column("personal_mobile", sa.String(length=32), nullable=True),
    sa.Column("alternate_mobile", sa.String(length=32), nullable=True),
    sa.Column("personal_email", sa.String(length=320), nullable=True),
    sa.Column("office_email", sa.String(length=320), nullable=True),
    sa.Column("emergency_contact_name", sa.String(length=200), nullable=True),
    sa.Column("emergency_mobile", sa.String(length=32), nullable=True),
    sa.Column("emergency_relationship", sa.String(length=100), nullable=True),
    sa.Column("employee_code", sa.String(length=64), nullable=True),
    sa.Column("joining_date", sa.DateTime(timezone=True), nullable=True),
    sa.Column("leaving_date", sa.DateTime(timezone=True), nullable=True),
    sa.Column("department", sa.String(length=200), nullable=True),
    sa.Column("designation", sa.String(length=200), nullable=True),
    sa.Column("reporting_manager", sa.String(length=200), nullable=True),
    sa.Column("employment_type", sa.String(length=100), nullable=True),
    sa.Column("cost_center", sa.String(length=100), nullable=True),
    sa.Column("profile_photo_url", sa.String(length=1000), nullable=True),
    sa.Column("profile_addresses", sa.JSON(), nullable=True),
    sa.Column("profile_documents", sa.JSON(), nullable=True),
]


def upgrade() -> None:
    """Add optional profile enrichment columns to ``users``."""
    for column in _SCALAR_COLUMNS:
        op.add_column("users", column.copy())


def downgrade() -> None:
    """Remove the optional profile enrichment columns from ``users``."""
    for column in reversed(_SCALAR_COLUMNS):
        op.drop_column("users", column.name)
