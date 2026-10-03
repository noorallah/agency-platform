"""A firm's own fields on its documents (MST-6, decision A132).

A supplier bill carries the firm's "Site name" field: saved with the bill,
read back with it, left alone by an update that does not mention it, and
printed because it is marked to print. A field on the purchase order the
chain raised carries to the bill by its name. A field defined for another
record is refused.
"""

# ruff: noqa: D103

from uuid import UUID

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.business.models.framework import AttributeDefinition, AttributeEntityType
from app.business.schemas import AttributeValueInput
from app.business.services import document_attributes
from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.purchase.models import PurchaseOrder
from app.purchase_invoice.schemas import PurchaseInvoiceCreate
from tests.unit.test_purchase_chain_synthesis import _Firm


@pytest.fixture
def firm() -> _Firm:
    """Build a firm with nothing billed yet."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    built = _Firm(sessionmaker(bind=engine, expire_on_commit=False)(), code="DOCF")
    built.stages(order=False, receipt=False)
    return built


def _field(
    firm: _Firm, entity: AttributeEntityType, code: str, *, prints: bool = False
) -> UUID:
    row = AttributeDefinition(
        firm_id=firm.firm.id,
        code=code,
        name="Site name",
        entity_type=entity.value,
        data_type="TEXT",
        show_on_print=prints,
    )
    firm.session.add(row)
    firm.session.commit()
    return row.id


def _bill(firm: _Firm, field_id: UUID, value: str) -> PurchaseInvoiceCreate:
    data = firm.product_bill("2", "100")
    return data.model_copy(
        update={
            "attributes": [
                AttributeValueInput(attribute_definition_id=field_id, value=value)
            ]
        }
    )


def test_a_bill_keeps_its_fields_and_prints_the_marked_ones(firm: _Firm) -> None:
    site = _field(firm, AttributeEntityType.PURCHASE_INVOICE, "PI_SITE", prints=True)
    bills = firm.bills()
    bill = bills.create_invoice(
        _bill(firm, site, "Plot 14, Peenya"),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    (view,) = bills.invoice_responses([bill])
    assert [(a.attribute_definition_id, a.value_text) for a in view.attributes] == [
        (site, "Plot 14, Peenya")
    ]
    assert document_attributes.printed(
        firm.session, AttributeEntityType.PURCHASE_INVOICE, bill.id
    ) == [("Site name", "Plot 14, Peenya")]


def test_a_field_for_another_record_is_refused(firm: _Firm) -> None:
    wrong = _field(firm, AttributeEntityType.CUSTOMER, "CUST_SITE")
    with pytest.raises(ValidationError):
        firm.bills().create_invoice(
            _bill(firm, wrong, "x"), firm_id=firm.firm.id, actor_id=firm.actor_id
        )


def test_a_field_carries_by_its_name_from_the_order(firm: _Firm) -> None:
    on_order = _field(firm, AttributeEntityType.PURCHASE_ORDER, "PO_SITE")
    on_bill = _field(firm, AttributeEntityType.PURCHASE_INVOICE, "PI_SITE")
    bills = firm.bills()
    bill = bills.create_invoice(
        firm.product_bill("2", "100"), firm_id=firm.firm.id, actor_id=firm.actor_id
    )
    order = firm.session.scalar(
        select(PurchaseOrder).where(PurchaseOrder.firm_id == firm.firm.id)
    )
    assert order is not None
    document_attributes.store(
        firm.session,
        AttributeEntityType.PURCHASE_ORDER,
        order.id,
        [AttributeValueInput(attribute_definition_id=on_order, value="Hosur depot")],
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    document_attributes.carry(
        firm.session,
        AttributeEntityType.PURCHASE_ORDER,
        order.id,
        AttributeEntityType.PURCHASE_INVOICE,
        bill.id,
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    firm.session.commit()
    (view,) = bills.invoice_responses([bill])
    assert [(a.attribute_definition_id, a.value_text) for a in view.attributes] == [
        (on_bill, "Hosur depot")
    ]
