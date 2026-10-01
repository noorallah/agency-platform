"""Where a person usually works in a firm: their branch and warehouse (44).

A counter clerk at STORE2, a salesman at the head office: each new document
they raise opens with their branch and warehouse filled in, ahead of the
firm's own default. It is where someone usually works, never where they may
work -- limiting a person to some branches is access control, and does not
belong here.

Kept in the firm's own store, beside the branches it names, so the foreign
keys hold and a person in two firms has a default in each.
"""

from uuid import UUID

from sqlalchemy import ForeignKey, Index, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class UserWorkDefault(BaseEntity):
    """One person's usual branch and warehouse in one firm."""

    __tablename__ = "user_work_defaults"
    __table_args__ = (
        Index(
            "UQ_user_work_defaults_firm_user_active",
            "firm_id",
            "user_id",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
    )

    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    #: The person; `users` lives in the platform store, so no key is declared.
    user_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    branch_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("branches.id", ondelete="RESTRICT")
    )
    warehouse_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("warehouses.id", ondelete="RESTRICT")
    )
