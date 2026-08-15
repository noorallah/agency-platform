"""Quotation lifecycle, expiry and conversion tests.

The point of a quotation is what it does *not* do: it reserves no stock, moves
no customer balance and writes no journal. Everything the firm promises happens
at conversion, on the order, so these tests are mostly about the boundary --
what an offer leaves untouched, and what happens when one is converted after
its prices have lapsed.
"""

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.batch_serial.models import batch_serial as _batch_serial_models  # noqa: F401
from app.branches.models import Branch, Warehouse
from app.business.models import framework as _business_models  # noqa: F401
from app.common.audit.models import AuditLog
from app.core.database.base import Base
from app.core.exceptions import ConflictError, ValidationError
from app.core.utils.dates import utc_now
from app.customers.models import Customer
from app.document_framework.models import DocumentTypeDefinition
from app.finance.models import JournalEntry
from app.firms.models import Firm
from app.identity.models import identity as _identity_models  # noqa: F401
from app.inventory.models import InventoryTransaction
from app.inventory.models import inventory as _inventory_models  # noqa: F401
from app.products.models import Product
from app.quotation.models import SalesQuotation, SalesQuotationLine
from app.quotation.schemas import (
    QuotationCreate,
    QuotationImportRequest,
    QuotationLineWrite,
    QuotationStatus,
)
from app.quotation.services import QuotationService
from app.sales.models import territory as _sales_models  # noqa: F401
from app.sales_order.models import SalesOrder, SalesOrderLine
from app.sales_return.models import sales_return as _sales_return_models  # noqa: F401
from app.tax.models import tax_framework as _tax_models  # noqa: F401
from app.uom.models import uom as _uom_models  # noqa: F401

PRICE = Decimal("100")


def _session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _firm(session: Session) -> Firm:
    row = Firm(
        name="Quoting Firm",
        code="QT-FIRM",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(row)
    session.commit()
    return row


def _branch(session: Session, *, firm_id: UUID) -> Branch:
    row = Branch(
        firm_id=firm_id,
        code="BR-001",
        name="Branch BR-001",
        display_name="Branch BR-001",
        currency_code="INR",
        working_hours={"start": "09:00", "end": "18:00"},
        status="ACTIVE",
    )
    session.add(row)
    session.commit()
    return row


def _warehouse(session: Session, *, firm_id: UUID, branch_id: UUID) -> Warehouse:
    row = Warehouse(
        firm_id=firm_id,
        branch_id=branch_id,
        code="WH-001",
        name="Warehouse WH-001",
        display_name="Warehouse WH-001",
        status="ACTIVE",
    )
    session.add(row)
    session.commit()
    return row


def _customer(session: Session, *, firm_id: UUID) -> Customer:
    row = Customer(
        firm_id=firm_id,
        code="CUS-001",
        customer_type="RETAIL",
        name="Customer CUS-001",
        display_name="Customer CUS-001",
        currency_code="INR",
        status="ACTIVE",
        credit_limit=Decimal("500000"),
        opening_balance=Decimal("0"),
    )
    session.add(row)
    session.commit()
    return row


def _product(session: Session, *, firm_id: UUID) -> Product:
    row = Product(
        firm_id=firm_id,
        code="SKU-001",
        name="Product SKU-001",
        product_type="STOCK_ITEM",
        status="ACTIVE",
    )
    session.add(row)
    session.commit()
    return row


class _Setup:
    """A firm with a customer and a product, ready to be quoted."""

    def __init__(self, session: Session) -> None:
        """Build the masters a quotation needs and nothing else."""
        self.session = session
        self.actor_id = uuid4()
        self.firm = _firm(session)
        self.branch = _branch(session, firm_id=self.firm.id)
        self.warehouse = _warehouse(
            session, firm_id=self.firm.id, branch_id=self.branch.id
        )
        self.customer = _customer(session, firm_id=self.firm.id)
        self.product = _product(session, firm_id=self.firm.id)
        self.service = QuotationService(session)

    def payload(
        self,
        *,
        quantity: Decimal = Decimal("4"),
        valid_until: date | None = None,
        quotation_date: date | None = None,
        discount_percent: Decimal = Decimal("0"),
    ) -> QuotationCreate:
        """Build a one-line quotation."""
        quoted_on = quotation_date or utc_now().date()
        return QuotationCreate(
            customer_id=self.customer.id,
            branch_id=self.branch.id,
            warehouse_id=self.warehouse.id,
            quotation_date=quoted_on,
            valid_until=valid_until or quoted_on + timedelta(days=30),
            payment_terms="30 days",
            lines=[
                QuotationLineWrite(
                    line_number=1,
                    product_id=self.product.id,
                    quantity=quantity,
                    unit_price=PRICE,
                    discount_percent=discount_percent,
                )
            ],
        )

    def accepted(self, **kwargs: object) -> SalesQuotation:
        """Create, send and accept a quotation."""
        row = self.service.create_quotation(
            self.payload(**kwargs),  # type: ignore[arg-type]
            firm_id=self.firm.id,
            actor_id=self.actor_id,
        )
        self.service.send_quotation(
            row.id, firm_scope=self.firm.id, actor_id=self.actor_id
        )
        return self.service.accept_quotation(
            row.id, firm_scope=self.firm.id, actor_id=self.actor_id
        )


def test_a_quotation_commits_nothing() -> None:
    """The defining property: an offer moves no stock, no balance, no ledger."""
    session = _session_factory()()
    setup = _Setup(session)

    row = setup.service.create_quotation(
        setup.payload(), firm_id=setup.firm.id, actor_id=setup.actor_id
    )

    assert row.status == QuotationStatus.DRAFT.value
    assert row.quotation_number.startswith("QT")
    assert row.grand_total == Decimal("400.0000")
    # Nothing was reserved, nothing was owed, nothing was posted.
    assert session.scalar(select(InventoryTransaction)) is None
    assert session.scalar(select(JournalEntry)) is None
    session.refresh(setup.customer)
    assert Decimal(str(setup.customer.current_outstanding)) == Decimal("0")
    assert session.scalar(select(AuditLog.id)) is not None
    assert (
        session.scalar(
            select(DocumentTypeDefinition).where(
                DocumentTypeDefinition.firm_id == setup.firm.id,
                DocumentTypeDefinition.code == "SALES_QUOTATION",
            )
        )
        is not None
    )


def test_a_discount_reaches_the_total() -> None:
    """The quoted total is the number the customer is being shown."""
    session = _session_factory()()
    setup = _Setup(session)

    row = setup.service.create_quotation(
        setup.payload(discount_percent=Decimal("10")),
        firm_id=setup.firm.id,
        actor_id=setup.actor_id,
    )

    assert row.line_discount_total == Decimal("40.0000")
    assert row.subtotal == Decimal("360.0000")
    assert row.grand_total == Decimal("360.0000")


def test_the_lifecycle_runs_draft_to_accepted() -> None:
    """Sending and accepting are separate facts about the same offer."""
    session = _session_factory()()
    setup = _Setup(session)

    row = setup.accepted()

    assert row.status == QuotationStatus.ACCEPTED.value
    assert row.sent_at is not None
    assert row.decided_at is not None
    actions = [
        event.action
        for event in setup.service.timeline(row.id, firm_scope=setup.firm.id)
    ]
    assert actions == ["CREATED", "SENT", "ACCEPTED"]


def test_a_decline_keeps_the_reason() -> None:
    """Losing a quote is a fact no total records; the reason has to be kept."""
    session = _session_factory()()
    setup = _Setup(session)
    row = setup.service.create_quotation(
        setup.payload(), firm_id=setup.firm.id, actor_id=setup.actor_id
    )

    declined = setup.service.decline_quotation(
        row.id,
        firm_scope=setup.firm.id,
        actor_id=setup.actor_id,
        reason="Competitor was cheaper",
    )

    assert declined.status == QuotationStatus.DECLINED.value
    assert declined.decline_reason == "Competitor was cheaper"


def test_an_expired_quotation_cannot_be_accepted() -> None:
    """A price offered in April is not a price offered in December."""
    session = _session_factory()()
    setup = _Setup(session)
    yesterday = utc_now().date() - timedelta(days=1)
    row = setup.service.create_quotation(
        setup.payload(
            quotation_date=yesterday - timedelta(days=10), valid_until=yesterday
        ),
        firm_id=setup.firm.id,
        actor_id=setup.actor_id,
    )

    with pytest.raises(ValidationError, match="expired"):
        setup.service.accept_quotation(
            row.id, firm_scope=setup.firm.id, actor_id=setup.actor_id
        )


def test_an_expired_quotation_cannot_be_converted() -> None:
    """Accepted in time, converted too late: the prices have still lapsed."""
    session = _session_factory()()
    setup = _Setup(session)
    row = setup.accepted()
    # Backdate it the way a month passing would.
    row.valid_until = utc_now().date() - timedelta(days=1)
    session.commit()

    with pytest.raises(ValidationError, match="expired"):
        setup.service.convert_quotation(
            row.id, firm_scope=setup.firm.id, actor_id=setup.actor_id
        )

    assert session.scalar(select(SalesOrder)) is None


def test_converting_builds_a_real_sales_order() -> None:
    """Through SalesOrderService, so the order is subject to an order's rules."""
    session = _session_factory()()
    setup = _Setup(session)
    row = setup.accepted()

    converted, order = setup.service.convert_quotation(
        row.id, firm_scope=setup.firm.id, actor_id=setup.actor_id
    )

    assert converted.status == QuotationStatus.CONVERTED.value
    assert converted.converted_sales_order_id == order.id
    assert converted.converted_sales_order_number == order.order_number
    assert order.order_number.startswith("SO")
    # The order carries its own numbering, and points back at the offer.
    assert order.reference_number == row.quotation_number
    line = session.scalar(
        select(SalesOrderLine).where(SalesOrderLine.sales_order_id == order.id)
    )
    assert line is not None
    assert line.quantity == Decimal("4.0000")
    assert line.unit_price == Decimal("100.0000")
    assert order.grand_total == Decimal("400.0000")


def test_a_quotation_converts_once() -> None:
    """A second conversion would be a second order for one agreement."""
    session = _session_factory()()
    setup = _Setup(session)
    row = setup.accepted()
    _converted, order = setup.service.convert_quotation(
        row.id, firm_scope=setup.firm.id, actor_id=setup.actor_id
    )

    with pytest.raises(ValidationError, match=order.order_number):
        setup.service.convert_quotation(
            row.id, firm_scope=setup.firm.id, actor_id=setup.actor_id
        )


def test_only_an_accepted_quotation_converts() -> None:
    """A sent offer nobody has agreed to is not an order waiting to happen."""
    session = _session_factory()()
    setup = _Setup(session)
    row = setup.service.create_quotation(
        setup.payload(), firm_id=setup.firm.id, actor_id=setup.actor_id
    )
    setup.service.send_quotation(
        row.id, firm_scope=setup.firm.id, actor_id=setup.actor_id
    )

    with pytest.raises(ValidationError, match="accepted quotation"):
        setup.service.convert_quotation(
            row.id, firm_scope=setup.firm.id, actor_id=setup.actor_id
        )


def test_a_converted_quotation_cannot_be_cancelled() -> None:
    """The order exists; cancelling the offer would leave it orphaned."""
    session = _session_factory()()
    setup = _Setup(session)
    row = setup.accepted()
    setup.service.convert_quotation(
        row.id, firm_scope=setup.firm.id, actor_id=setup.actor_id
    )

    with pytest.raises(ValidationError, match="cancel the order instead"):
        setup.service.cancel_quotation(
            row.id, firm_scope=setup.firm.id, actor_id=setup.actor_id, reason="oops"
        )


def test_a_sent_quotation_can_still_be_revised() -> None:
    """A customer asking for a better price is the ordinary case."""
    session = _session_factory()()
    setup = _Setup(session)
    row = setup.service.create_quotation(
        setup.payload(), firm_id=setup.firm.id, actor_id=setup.actor_id
    )
    setup.service.send_quotation(
        row.id, firm_scope=setup.firm.id, actor_id=setup.actor_id
    )

    revised = setup.service.update_quotation(
        row.id,
        setup.payload(quantity=Decimal("6")),
        firm_scope=setup.firm.id,
        actor_id=setup.actor_id,
    )

    assert revised.status == QuotationStatus.SENT.value
    assert revised.grand_total == Decimal("600.0000")
    # Revising reconciles the line rather than replacing it, so anything
    # holding its id still points at something.
    lines = list(
        session.scalars(
            select(SalesQuotationLine).where(
                SalesQuotationLine.sales_quotation_id == row.id
            )
        ).all()
    )
    assert len(lines) == 1
    assert lines[0].quantity == Decimal("6.0000")


def test_an_accepted_quotation_can_no_longer_be_edited() -> None:
    """It has become a record of what was agreed."""
    session = _session_factory()()
    setup = _Setup(session)
    row = setup.accepted()

    with pytest.raises(ValidationError, match="draft or sent"):
        setup.service.update_quotation(
            row.id,
            setup.payload(quantity=Decimal("9")),
            firm_scope=setup.firm.id,
            actor_id=setup.actor_id,
        )


def test_validity_cannot_end_before_the_offer_begins() -> None:
    """A quotation that expired on the day it was written offers nothing."""
    with pytest.raises(ValueError, match="valid_until"):
        QuotationCreate(
            customer_id=uuid4(),
            branch_id=uuid4(),
            warehouse_id=uuid4(),
            quotation_date=date(2026, 8, 14),
            valid_until=date(2026, 8, 13),
            lines=[
                QuotationLineWrite(
                    line_number=1, product_id=uuid4(), quantity=Decimal("1")
                )
            ],
        )


def test_only_a_draft_can_be_deleted() -> None:
    """A sent offer is a record of what the customer was told."""
    session = _session_factory()()
    setup = _Setup(session)
    row = setup.service.create_quotation(
        setup.payload(), firm_id=setup.firm.id, actor_id=setup.actor_id
    )
    setup.service.send_quotation(
        row.id, firm_scope=setup.firm.id, actor_id=setup.actor_id
    )

    with pytest.raises(ValidationError, match="draft quotation can be deleted"):
        setup.service.delete_quotation(
            row.id, firm_scope=setup.firm.id, actor_id=setup.actor_id
        )


def test_the_summary_counts_expiry_as_a_date_not_a_status() -> None:
    """A sent quotation that lapsed on Friday is both sent and expired."""
    session = _session_factory()()
    setup = _Setup(session)
    live = setup.service.create_quotation(
        setup.payload(), firm_id=setup.firm.id, actor_id=setup.actor_id
    )
    setup.service.send_quotation(
        live.id, firm_scope=setup.firm.id, actor_id=setup.actor_id
    )
    lapsed = setup.service.create_quotation(
        setup.payload(), firm_id=setup.firm.id, actor_id=setup.actor_id
    )
    setup.service.send_quotation(
        lapsed.id, firm_scope=setup.firm.id, actor_id=setup.actor_id
    )
    lapsed.valid_until = utc_now().date() - timedelta(days=1)
    session.commit()

    summary = setup.service.summary(firm_scope=setup.firm.id)

    assert summary.total_quotations == 2
    assert summary.sent_quotations == 2
    assert summary.expired_quotations == 1
    assert summary.total_quoted_value == Decimal("800.0000")


def test_the_conversion_report_joins_what_was_offered_to_what_was_sold() -> None:
    """No other report can: a register says one half and an order the other."""
    session = _session_factory()()
    setup = _Setup(session)
    won = setup.accepted()
    setup.service.convert_quotation(
        won.id, firm_scope=setup.firm.id, actor_id=setup.actor_id
    )
    lost = setup.service.create_quotation(
        setup.payload(quantity=Decimal("2")),
        firm_id=setup.firm.id,
        actor_id=setup.actor_id,
    )
    setup.service.decline_quotation(
        lost.id,
        firm_scope=setup.firm.id,
        actor_id=setup.actor_id,
        reason="Too expensive",
    )

    rows = setup.service.conversion_report(firm_scope=setup.firm.id)

    assert len(rows) == 1
    assert rows[0].customer_name == "Customer CUS-001"
    assert rows[0].quoted_count == 2
    assert rows[0].quoted_value == Decimal("600.0000")
    assert rows[0].converted_count == 1
    assert rows[0].converted_value == Decimal("400.0000")
    assert rows[0].declined_count == 1


def test_the_register_says_what_became_of_each_offer() -> None:
    """The order number is the answer to "did we win it"."""
    session = _session_factory()()
    setup = _Setup(session)
    row = setup.accepted()
    _converted, order = setup.service.convert_quotation(
        row.id, firm_scope=setup.firm.id, actor_id=setup.actor_id
    )

    register = setup.service.register_report(firm_scope=setup.firm.id)

    assert len(register) == 1
    assert register[0].quotation_number == row.quotation_number
    assert register[0].converted_sales_order_number == order.order_number
    assert register[0].status == QuotationStatus.CONVERTED


def test_the_response_answers_whether_it_can_still_be_converted() -> None:
    """Answered by the server so a client cannot disagree with it."""
    session = _session_factory()()
    setup = _Setup(session)
    row = setup.accepted()

    assert setup.service.quotation_response(row).can_convert is True
    assert setup.service.quotation_response(row).is_expired is False

    row.valid_until = utc_now().date() - timedelta(days=1)
    session.commit()

    assert setup.service.quotation_response(row).can_convert is False
    assert setup.service.quotation_response(row).is_expired is True


def test_a_quotation_is_visible_only_inside_its_own_firm() -> None:
    """Firm scope is the boundary every read here goes through."""
    session = _session_factory()()
    setup = _Setup(session)
    row = setup.service.create_quotation(
        setup.payload(), firm_id=setup.firm.id, actor_id=setup.actor_id
    )

    with pytest.raises(Exception, match="not found"):
        setup.service.get_quotation(row.id, firm_scope=uuid4())

    assert (
        session.scalar(select(SalesQuotation).where(SalesQuotation.id == row.id))
        is not None
    )


def test_a_batch_import_lands_whole() -> None:
    """Two quotations arrive in one transaction, each with its own number."""
    session = _session_factory()()
    setup = _Setup(session)

    rows = setup.service.import_quotations(
        QuotationImportRequest(
            records=[
                setup.payload(quantity=Decimal("2")),
                setup.payload(quantity=Decimal("5")),
            ]
        ),
        firm_scope=setup.firm.id,
        actor_id=setup.actor_id,
    )

    assert len(rows) == 2
    # The second record has to see the counter the first one advanced, which it
    # only does because both are staged on one session before anything commits.
    assert len({row.quotation_number for row in rows}) == 2
    assert session.query(SalesQuotation).count() == 2
    # A quotation still commits nothing, imported or not.
    assert session.query(JournalEntry).count() == 0
    assert session.query(InventoryTransaction).count() == 0


def test_a_refused_batch_leaves_nothing_behind() -> None:
    """A batch that is refused can be corrected and sent again as it stands.

    Both records carry the same number here, so the second is refused at the
    flush -- after its own header has been staged. A loop over
    ``create_quotation`` would leave the first one committed and the second
    half-written on the session, and the corrected file would then fail on the
    first as a duplicate.
    """
    session = _session_factory()()
    setup = _Setup(session)

    first = setup.payload(quantity=Decimal("2"))
    first.quotation_number = "QT-DUP-1"
    second = setup.payload(quantity=Decimal("3"))
    second.quotation_number = "QT-DUP-1"

    with pytest.raises(ConflictError):
        setup.service.import_quotations(
            QuotationImportRequest(records=[first, second]),
            firm_scope=setup.firm.id,
            actor_id=setup.actor_id,
        )

    assert session.query(SalesQuotation).count() == 0
    assert session.query(SalesQuotationLine).count() == 0


def test_the_export_says_whether_the_prices_have_lapsed() -> None:
    """``is_expired`` is its own column, because the status does not say it.

    A quotation reads SENT the day before and the day after its prices lapse,
    so a pipeline exported on status alone cannot tell the two apart.
    """
    session = _session_factory()()
    setup = _Setup(session)
    today = utc_now().date()
    live = setup.service.create_quotation(
        setup.payload(valid_until=today + timedelta(days=30)),
        firm_id=setup.firm.id,
        actor_id=setup.actor_id,
    )
    lapsed = setup.service.create_quotation(
        setup.payload(
            quotation_date=today - timedelta(days=60),
            valid_until=today - timedelta(days=1),
        ),
        firm_id=setup.firm.id,
        actor_id=setup.actor_id,
    )

    content = setup.service.export_quotations_csv(firm_scope=setup.firm.id)

    lines = [line for line in content.splitlines() if line.strip()]
    assert lines[0].startswith("quotation_number,quotation_date,valid_until")
    by_number = {line.split(",")[0]: line for line in lines[1:]}
    assert by_number[live.quotation_number].split(",")[6] == "false"
    assert by_number[lapsed.quotation_number].split(",")[6] == "true"
    # Both are still DRAFT: the status column cannot answer this question.
    assert by_number[live.quotation_number].split(",")[5] == "DRAFT"
    assert by_number[lapsed.quotation_number].split(",")[5] == "DRAFT"
