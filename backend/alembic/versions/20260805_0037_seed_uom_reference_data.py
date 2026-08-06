"""Seed baseline UOM, packaging, and profile default reference data.

Revision ID: 20260805_0037
Revises: 20260805_0036
Create Date: 2026-08-05
"""

from collections.abc import Sequence

from sqlalchemy.orm import Session

from alembic import op
from app.uom.system_seed import seed_uom_reference_data

revision: str = "20260805_0037"
down_revision: str | None = "20260805_0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Ensure baseline UOM reference data exists."""
    with Session(bind=op.get_bind()) as session:
        seed_uom_reference_data(session)
        session.flush()


def downgrade() -> None:
    """Keep seeded UOM reference rows in place on downgrade."""
