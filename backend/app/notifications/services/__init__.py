"""Work out what waits for a person, and keep what they have seen (PLT-2).

Each notification is a count over the documents it is about, offered only to
a person who could act on it: approvals to whoever may approve, failed
messages to whoever sends them, stock alerts to whoever watches stock. Each
is one grouped query, so the desktop can ask every minute.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.common.firm_metadata import firm_today
from app.core.security.authorization import Principal
from app.core.utils.dates import as_utc, utc_now
from app.inventory.models.adjustment_approval import StockAdjustmentRequest
from app.inventory.services.stock_alerts import stock_alerts
from app.messaging.models.messaging import MessagingOutbox
from app.notifications.models import NotificationRead
from app.purchase.models import PurchaseOrder
from app.purchase.models.requisition import PurchaseRequisition

_Counted = (
    type[PurchaseOrder]
    | type[PurchaseRequisition]
    | type[StockAdjustmentRequest]
    | type[MessagingOutbox]
)

#: How far back a failed message is still news.
FAILED_MESSAGE_DAYS = 7


@dataclass(frozen=True)
class Notification:
    """One thing waiting, before the person's read mark is applied."""

    key: str
    kind: str
    title: str
    detail: str
    count: int
    at: datetime | None


def _plural(count: int, one: str, many: str) -> str:
    """Return "1 order" or "3 orders"."""
    return f"{count} {one if count == 1 else many}"


class NotificationService:
    """List a person's notifications and mark them seen."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the firm's store session."""
        self._session = session

    def for_person(
        self, firm_id: UUID, principal: Principal, user_id: UUID
    ) -> list[tuple[Notification, bool]]:
        """Return the person's notifications, newest first, each with "seen"."""
        sources: list[tuple[tuple[str, ...], Callable[[UUID], Notification | None]]] = [
            (("PURCHASE_APPROVE",), self._orders_awaiting_approval),
            (("PURCHASE_APPROVE",), self._requisitions_awaiting_approval),
            (("INVENTORY_ADJUST",), self._adjustments_awaiting_approval),
            (("DOCUMENT_SEND", "SETTINGS_VIEW"), self._failed_messages),
            (("INVENTORY_VIEW",), self._stock_alerts),
            (("SALES_APPROVE", "PURCHASE_APPROVE"), self._chains_awaiting_sign_off),
        ]
        found = [
            item
            for codes, source in sources
            if any(principal.has_permission(code) for code in codes)
            for item in [source(firm_id)]
            if item is not None
        ]
        seen = self._seen(firm_id, user_id, [item.key for item in found])
        # Dated ones newest first, then the undated (the day's stock alert).
        now = utc_now()
        found.sort(key=lambda item: (item.at is not None, item.at or now), reverse=True)
        return [(item, item.key in seen) for item in found]

    def mark_read(self, firm_id: UUID, user_id: UUID, keys: list[str]) -> None:
        """Mark these keys seen by the person; a key already seen is left; commit."""
        already = self._seen(firm_id, user_id, keys)
        now = utc_now()
        for key in dict.fromkeys(keys):
            if key in already:
                continue
            self._session.add(
                NotificationRead(
                    firm_id=firm_id,
                    user_id=user_id,
                    notification_key=key[:200],
                    read_at=now,
                    created_by=user_id,
                    updated_by=user_id,
                )
            )
        self._session.commit()

    # ------------------------------------------------------------------

    def _seen(self, firm_id: UUID, user_id: UUID, keys: list[str]) -> set[str]:
        if not keys:
            return set()
        return set(
            self._session.scalars(
                select(NotificationRead.notification_key).where(
                    NotificationRead.firm_id == firm_id,
                    NotificationRead.user_id == user_id,
                    NotificationRead.is_deleted.is_(False),
                    NotificationRead.notification_key.in_(keys),
                )
            ).all()
        )

    def _count(
        self, model: _Counted, *where: ColumnElement[bool]
    ) -> tuple[int, datetime | None]:
        """Count the rows and find the newest change among them."""
        count, newest = self._session.execute(
            select(func.count(model.id), func.max(model.updated_at)).where(
                model.is_deleted.is_(False), *where
            )
        ).one()
        return int(count or 0), (as_utc(newest) if newest is not None else None)

    @staticmethod
    def _key(kind: str, count: int, newest: datetime | None) -> str:
        """Fingerprint what a notification says, so news changes the key."""
        stamp = newest.strftime("%Y%m%d%H%M%S%f") if newest else "-"
        return f"{kind}:{count}:{stamp}"

    def _orders_awaiting_approval(self, firm_id: UUID) -> Notification | None:
        count, newest = self._count(
            PurchaseOrder,
            PurchaseOrder.firm_id == firm_id,
            PurchaseOrder.status == "SUBMITTED",
        )
        if not count:
            return None
        kind = "purchase_order_approval"
        return Notification(
            self._key(kind, count, newest),
            kind,
            "Purchase orders to approve",
            _plural(count, "order is", "orders are") + " waiting for approval.",
            count,
            newest,
        )

    def _chains_awaiting_sign_off(self, firm_id: UUID) -> Notification | None:
        """Documents signed at one level and waiting for the next (PLT-1)."""
        from app.approvals.models import ApprovalDecision
        from app.approvals.services import ApprovalChainService

        count = ApprovalChainService(self._session).awaiting_count(firm_id)
        if not count:
            return None
        newest = self._session.scalar(
            select(func.max(ApprovalDecision.decided_at)).where(
                ApprovalDecision.firm_id == firm_id,
                ApprovalDecision.is_deleted.is_(False),
            )
        )
        at = as_utc(newest) if newest is not None else None
        kind = "approval_chain"
        return Notification(
            self._key(kind, count, at),
            kind,
            "Documents awaiting the next sign-off",
            _plural(count, "document is", "documents are")
            + " signed at one level and waiting for the next.",
            count,
            at,
        )

    def _requisitions_awaiting_approval(self, firm_id: UUID) -> Notification | None:
        count, newest = self._count(
            PurchaseRequisition,
            PurchaseRequisition.firm_id == firm_id,
            PurchaseRequisition.status == "SUBMITTED",
        )
        if not count:
            return None
        kind = "requisition_approval"
        return Notification(
            self._key(kind, count, newest),
            kind,
            "Requisitions to approve",
            _plural(count, "requisition is", "requisitions are")
            + " waiting for approval.",
            count,
            newest,
        )

    def _adjustments_awaiting_approval(self, firm_id: UUID) -> Notification | None:
        count, newest = self._count(
            StockAdjustmentRequest,
            StockAdjustmentRequest.firm_id == firm_id,
            StockAdjustmentRequest.status == "PENDING",
        )
        if not count:
            return None
        kind = "stock_adjustment_approval"
        return Notification(
            self._key(kind, count, newest),
            kind,
            "Stock adjustments to approve",
            _plural(count, "adjustment is", "adjustments are")
            + " waiting for approval.",
            count,
            newest,
        )

    def _failed_messages(self, firm_id: UUID) -> Notification | None:
        since = utc_now() - timedelta(days=FAILED_MESSAGE_DAYS)
        count, newest = self._count(
            MessagingOutbox,
            MessagingOutbox.firm_id == firm_id,
            MessagingOutbox.status == "FAILED",
            MessagingOutbox.updated_at >= since,
        )
        if not count:
            return None
        kind = "message_failed"
        return Notification(
            self._key(kind, count, newest),
            kind,
            "Messages that failed",
            _plural(count, "message", "messages")
            + f" could not be sent in the last {FAILED_MESSAGE_DAYS} days.",
            count,
            newest,
        )

    def _stock_alerts(self, firm_id: UUID) -> Notification | None:
        today = firm_today(self._session, firm_id)
        alerts = stock_alerts(self._session, firm_id, on=today)
        count = alerts.out + alerts.low
        if not count:
            return None
        kind = "stock_alert"
        parts = []
        if alerts.out:
            parts.append(_plural(alerts.out, "product is", "products are") + " out")
        if alerts.low:
            parts.append(
                _plural(alerts.low, "product is", "products are")
                + " below the reorder level"
            )
        return Notification(
            # Once a day at most: the counts move with every sale.
            f"{kind}:{today.isoformat()}:{alerts.out}:{alerts.low}",
            kind,
            "Stock running out",
            "; ".join(parts) + ".",
            count,
            None,
        )


__all__ = ["FAILED_MESSAGE_DAYS", "Notification", "NotificationService"]
