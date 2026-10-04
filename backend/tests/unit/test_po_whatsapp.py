"""A purchase order goes to its supplier on WhatsApp (PG-7, backlog 86 #3).

Through the same send-document service as every hand-sent document, so a firm
with messaging off is refused; under the template the firm names for
"Purchase order sent to the supplier"; to the supplier's own mobile unless one
is typed; and the order is marked sent by WhatsApp afterwards.
"""

# ruff: noqa: D103, F811

from uuid import UUID

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.messaging.models import MessagingOutbox
from app.messaging.schemas import (
    ChannelAccountWrite,
    EventChannelWrite,
    EventConfigWrite,
    ManualSendRequest,
    MessagingSettingsWrite,
)
from app.messaging.services import MessagingService
from tests.unit.test_messaging import SECRET, _fakes  # noqa: F401
from tests.unit.test_purchase_chain_synthesis import _Firm


class _Buyer:
    """A purchasing firm with an approved order and a supplier to send it to."""

    def __init__(self) -> None:
        """Build the firm and give the supplier a mobile number."""
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.firm = _Firm(sessionmaker(bind=engine, expire_on_commit=False)())
        self.firm.vendor.mobile = "+919800000001"
        self.firm.session.commit()
        self.actor_id = self.firm.actor_id
        self.firm_id: UUID = self.firm.firm.id
        self.order = self.firm.approved_order()
        self.messaging = MessagingService(self.firm.session)

    def switch_on(self, *, template: bool = True) -> None:
        """Turn messaging and WhatsApp on, naming the template unless told not."""
        self.messaging.update_settings(
            MessagingSettingsWrite(
                is_enabled=True,
                due_soon_days=3,
                overdue_every_days=7,
                overdue_stop_after_days=90,
            ),
            firm_id=self.firm_id,
            actor_id=self.actor_id,
        )
        self.messaging.save_account(
            "WHATSAPP",
            ChannelAccountWrite(
                provider="FAKE_WHATSAPP",
                settings={"account": "acct-1", "api_key": SECRET},
            ),
            firm_id=self.firm_id,
            actor_id=self.actor_id,
        )
        self.messaging.test_channel(
            "WHATSAPP", firm_id=self.firm_id, actor_id=self.actor_id
        )
        self.messaging.set_channel_enabled(
            "WHATSAPP", True, firm_id=self.firm_id, actor_id=self.actor_id
        )
        if template:
            self.messaging.save_event_config(
                "PURCHASE_ORDER_SENT",
                EventConfigWrite(
                    channels=[
                        EventChannelWrite(channel="WHATSAPP", template_name="po_tpl")
                    ]
                ),
                firm_id=self.firm_id,
                actor_id=self.actor_id,
            )

    def send(self, recipient: str | None = None) -> MessagingOutbox:
        """Send the order on WhatsApp."""
        return self.messaging.send_document(
            ManualSendRequest(
                document_type="PURCHASE_ORDER",
                document_id=self.order.id,
                channel="WHATSAPP",
                recipient=recipient,
            ),
            firm_id=self.firm_id,
            actor_id=self.actor_id,
        )


@pytest.fixture
def buyer() -> _Buyer:
    return _Buyer()


def test_refused_while_messaging_is_off(buyer: _Buyer) -> None:
    with pytest.raises(ValidationError, match="Messaging is off"):
        buyer.send()


def test_refused_until_a_template_is_named(buyer: _Buyer) -> None:
    buyer.switch_on(template=False)
    with pytest.raises(ValidationError, match="template"):
        buyer.send()


def test_queued_to_the_suppliers_mobile_and_marked_sent(buyer: _Buyer) -> None:
    buyer.switch_on()
    row = buyer.send()
    assert row.channel == "WHATSAPP" and row.status == "QUEUED"
    assert row.document_type == "PURCHASE_ORDER"
    assert row.document_number == buyer.order.po_number
    assert row.recipient == "+919800000001"
    assert row.template_name == "po_tpl"
    assert row.variables[1] == buyer.order.po_number
    buyer.firm.session.refresh(buyer.order)
    assert buyer.order.sent_via == "WHATSAPP" and buyer.order.sent_at is not None


def test_a_typed_number_replaces_the_suppliers(buyer: _Buyer) -> None:
    buyer.switch_on()
    assert buyer.send("+919811111111").recipient == "+919811111111"
