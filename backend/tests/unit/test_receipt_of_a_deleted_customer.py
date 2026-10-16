"""D-FIN-37: a receipt still names a customer deleted after it was written."""

from decimal import Decimal

from app.settlements.api.router import _to_responses
from app.settlements.schemas import SettlementCreate, SettlementMethodEnum
from app.settlements.services import ReceiptService
from tests.unit.test_settlements import WHEN, _Books, _session_factory


def test_a_receipt_page_names_a_customer_deleted_since() -> None:
    """The page answers, with the customer's name, rather than a 404."""
    books = _Books(_session_factory()())
    service = ReceiptService(books.session)
    row = service.create(
        SettlementCreate(
            party_id=books.customer.id,
            settlement_date=WHEN,
            amount=Decimal("100.00"),
            method=SettlementMethodEnum.BANK,
            allocations=[],
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.customer.is_deleted = True
    books.session.commit()

    page = _to_responses(service, [row])

    assert page[0].party_name == books.customer.name
    assert service.party_of(row).id == books.customer.id
