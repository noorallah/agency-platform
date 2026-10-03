"""The bell (PLT-2, decision A123): what waits for a person, and what they saw.

Each notification is counted from the documents it is about and offered only
to someone who can act on it. Marking it seen holds until something new
arrives -- the key carries a fingerprint, so a new order rings the bell again.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from app.common.scope import ResolvedFirmScope
from app.core.enums import TokenType
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.inventory.models.adjustment_approval import StockAdjustmentRequest
from app.messaging.models.messaging import MessagingOutbox
from app.notifications.api.router import list_notifications, mark_notifications_read
from app.notifications.schemas import NotificationReadWrite, NotificationsRecord
from app.purchase.models import PurchaseOrder
from app.purchase.models.requisition import PurchaseRequisition
from tests.unit.test_reorder_suggestions import _Shop

_ACTOR = UUID("00000000-0000-0000-0000-0000000000c1")


def _scope(shop: _Shop, *codes: str, actor: UUID = _ACTOR) -> ResolvedFirmScope:
    return ResolvedFirmScope(
        principal=Principal(
            subject=actor,
            roles=frozenset(),
            permissions=frozenset(codes),
            claims=TokenClaims(
                sub=str(actor),
                type=TokenType.ACCESS,
                iat=1,
                exp=4_102_444_800,
                roles=[],
            ),
        ),
        firm_id=shop.firm.id,
    )


def _bell(shop: _Shop, *codes: str, actor: UUID = _ACTOR) -> NotificationsRecord:
    response = list_notifications(_scope(shop, *codes, actor=actor), shop.session)
    assert response.data is not None
    return response.data


def _submitted_order(shop: _Shop) -> None:
    shop.session.add(
        PurchaseOrder(
            firm_id=shop.firm.id,
            branch_id=shop.branch.id,
            warehouse_id=shop.warehouse.id,
            vendor_id=uuid4(),
            po_number=f"PO-{uuid4().hex[:6]}",
            purchase_date=date(2026, 9, 1),
            status="SUBMITTED",
        )
    )
    shop.session.commit()


def test_an_approver_sees_orders_and_requisitions_waiting() -> None:
    shop = _Shop()
    _submitted_order(shop)
    _submitted_order(shop)
    shop.session.add(
        PurchaseRequisition(
            firm_id=shop.firm.id,
            branch_id=shop.branch.id,
            warehouse_id=shop.warehouse.id,
            requisition_number="PR-1",
            requisition_date=date(2026, 9, 1),
            status="SUBMITTED",
        )
    )
    shop.session.commit()

    bell = _bell(shop, "PURCHASE_APPROVE")

    by_kind = {item.kind: item for item in bell.items}
    assert by_kind["purchase_order_approval"].count == 2
    assert by_kind["purchase_order_approval"].detail == (
        "2 orders are waiting for approval."
    )
    assert by_kind["requisition_approval"].count == 1
    assert bell.unread == 2


def test_nothing_is_offered_to_someone_who_cannot_act_on_it() -> None:
    shop = _Shop()
    _submitted_order(shop)

    assert _bell(shop, "PURCHASE_VIEW").items == []


def test_adjustments_failed_messages_and_stock_alerts() -> None:
    shop = _Shop()
    shop.session.add_all(
        [
            StockAdjustmentRequest(
                firm_id=shop.firm.id,
                kind="ADJUST",
                product_id=shop.product.id,
                warehouse_id=shop.warehouse.id,
                quantity=Decimal("-5"),
                estimated_value=Decimal("5000"),
                payload_json="{}",
                status="PENDING",
            ),
            MessagingOutbox(
                firm_id=shop.firm.id,
                event_code="INVOICE_APPROVED",
                channel="EMAIL",
                status="FAILED",
            ),
        ]
    )
    shop.session.commit()
    shop.stock(shop.product, available="0", reorder="4")

    bell = _bell(shop, "INVENTORY_ADJUST", "DOCUMENT_SEND", "INVENTORY_VIEW")

    kinds = {item.kind: item for item in bell.items}
    assert set(kinds) == {
        "stock_adjustment_approval",
        "message_failed",
        "stock_alert",
    }
    assert kinds["stock_alert"].detail == "1 product is out."
    # The undated stock alert sorts after the dated ones.
    assert bell.items[-1].kind == "stock_alert"


def test_seen_holds_until_something_new_arrives_and_is_per_person() -> None:
    shop = _Shop()
    _submitted_order(shop)
    [item] = _bell(shop, "PURCHASE_APPROVE").items

    mark_notifications_read(
        NotificationReadWrite(keys=[item.key, item.key]),
        _scope(shop, "PURCHASE_APPROVE"),
        shop.session,
    )
    seen = _bell(shop, "PURCHASE_APPROVE")
    assert seen.unread == 0 and seen.items[0].read
    # Another approver has not seen it.
    assert _bell(shop, "PURCHASE_APPROVE", actor=uuid4()).unread == 1

    _submitted_order(shop)
    again = _bell(shop, "PURCHASE_APPROVE")
    assert again.unread == 1
    assert again.items[0].count == 2


def test_marking_twice_is_harmless() -> None:
    shop = _Shop()
    _submitted_order(shop)
    [item] = _bell(shop, "PURCHASE_APPROVE").items
    scope = _scope(shop, "PURCHASE_APPROVE")

    mark_notifications_read(NotificationReadWrite(keys=[item.key]), scope, shop.session)
    mark_notifications_read(NotificationReadWrite(keys=[item.key]), scope, shop.session)

    assert _bell(shop, "PURCHASE_APPROVE").unread == 0
