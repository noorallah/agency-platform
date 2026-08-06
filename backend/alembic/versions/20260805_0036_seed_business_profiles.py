"""Refresh baseline distributor-oriented business profile seeds.

Revision ID: 20260805_0036
Revises: 20260805_0035
Create Date: 2026-08-05
"""

from collections.abc import Sequence

from sqlalchemy.orm import Session

from alembic import op
from app.business.system_seed import seed_business_profiles

revision: str = "20260805_0036"
down_revision: str | None = "20260805_0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Ensure baseline business profiles exist with distributor-oriented defaults."""
    with Session(bind=op.get_bind()) as session:
        seed_business_profiles(session)
        session.flush()


def downgrade() -> None:
    """Keep seeded business profile records in place on downgrade."""
