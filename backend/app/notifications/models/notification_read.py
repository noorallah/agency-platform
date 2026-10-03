"""That a person has seen one notification (PLT-2, decision A123).

The notifications themselves are not stored: each is derived on every read
from the documents it is about -- orders awaiting approval, messages that
failed, stock below its level -- so it can never say something the books no
longer do, and no service has to remember to write one. Only the person's
"seen it" is kept, against the notification's key. The key carries a
fingerprint of what the notification said, so when something new arrives
the key changes and the bell rings again.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class NotificationRead(BaseEntity):
    """One person's mark that they have seen one notification."""

    __tablename__ = "notification_reads"
    __table_args__ = (
        Index(
            "UQ_notification_reads_key_active",
            "firm_id",
            "user_id",
            "notification_key",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
    )

    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    #: A bare id: ``users`` lives only in the platform store.
    user_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    notification_key: Mapped[str] = mapped_column(String(200), nullable=False)
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
