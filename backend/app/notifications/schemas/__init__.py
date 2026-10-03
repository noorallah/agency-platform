"""Notification request and response models."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NotificationRecord(BaseModel):
    """One thing waiting for the person."""

    #: Changes when what the notification says changes; a read mark is
    #: held against it.
    key: str
    #: What it is about -- the desktop opens the matching screen:
    #: ``purchase_order_approval``, ``requisition_approval``,
    #: ``stock_adjustment_approval``, ``message_failed``, ``stock_alert``.
    kind: str
    title: str
    detail: str
    count: int
    #: The newest thing it counts, where it has one.
    at: datetime | None
    read: bool


class NotificationsRecord(BaseModel):
    """Everything waiting for the person, and how many they have not seen."""

    items: list[NotificationRecord]
    unread: int


class NotificationReadWrite(BaseModel):
    """Mark notifications seen, by key."""

    model_config = ConfigDict(extra="forbid")

    keys: list[str] = Field(min_length=1, max_length=50)


__all__ = ["NotificationReadWrite", "NotificationRecord", "NotificationsRecord"]
