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
from sqlalchemy import create_engine, func, select
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
from app.promotions.models import Promotion, PromotionAction, PromotionRedemption
from app.promotions.schemas import PromotionActionType, PromotionStatus
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
from app.sales_order.schemas import SalesOrderCreate, SalesOrderLineWrite
from app.sales_order.services.sales_order_service import SalesOrderService
from app.sales_return.models import sales_return as _sales_return_models  # noqa: F401
from app.tax.models import tax_framework as _tax_models  # noqa: F401
from app.uom.models import uom as _uom_models  # noqa: F401

# Fixtures here type their document numbers; see conftest (D-CFG-2).
pytestmark = pytest.mark.typed_document_numbers

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
        discount_percent: Decimal | None = None,
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


def test_a_conversion_that_fails_half_way_leaves_nothing_behind() -> None:
    """D-SELL-14: the order and the quotation's CONVERTED commit together.

    `create_order` committed the order and the CONVERTED move was a second
    commit, so a failure between them left an order beside a quotation still
    ACCEPTED -- and convertible again, into a second order for one agreement.
    """
    session = _session_factory()()
    setup = _Setup(session)
    row = setup.accepted()

    def _refuse(**_: object) -> None:
        """Fail the way anything after the order's write could."""
        raise RuntimeError("the lifecycle event could not be written")

    setup.service._record_event = _refuse  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        setup.service.convert_quotation(
            row.id, firm_scope=setup.firm.id, actor_id=setup.actor_id
        )
    session.rollback()

    assert session.scalar(select(func.count()).select_from(SalesOrder)) == 0
    session.refresh(row)
    assert row.status == QuotationStatus.ACCEPTED.value
    assert row.converted_sales_order_id is None


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
    assert (rows[0].expired_count, rows[0].open_count) == (0, 0)


def test_the_conversion_report_counts_what_lapsed() -> None:
    """An offer nobody answered before its date is lost too, and is counted.

    The report called every non-cancelled quotation "quoted" and counted only
    CONVERTED and DECLINED, so a SENT offer past `valid_until` was "quoted" and
    nothing else and "how many lapsed" -- the catalogue's own description --
    had no answer; the summary tile has counted it all along (D-RPT-12). A
    past date is refused at write, so it is set on the row here.
    """
    session = _session_factory()()
    setup = _Setup(session)
    lapsed = setup.service.create_quotation(
        setup.payload(quantity=Decimal("2")),
        firm_id=setup.firm.id,
        actor_id=setup.actor_id,
    )
    setup.service.send_quotation(
        lapsed.id, firm_scope=setup.firm.id, actor_id=setup.actor_id
    )
    lapsed.valid_until = date(2026, 1, 1)
    still_open = setup.service.create_quotation(
        setup.payload(quantity=Decimal("3")),
        firm_id=setup.firm.id,
        actor_id=setup.actor_id,
    )
    session.commit()

    [row] = setup.service.conversion_report(firm_scope=setup.firm.id)

    assert row.quoted_count == 2
    assert (row.expired_count, row.open_count) == (1, 1)
    assert (row.converted_count, row.declined_count) == (0, 0)
    assert still_open.valid_until > date(2026, 1, 1)


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


def test_the_register_names_the_customer_it_quoted() -> None:
    """A register of ids alone shows a screen of UUIDs (D-RPT-17)."""
    session = _session_factory()()
    setup = _Setup(session)
    setup.accepted()

    register = setup.service.register_report(firm_scope=setup.firm.id)

    assert register[0].customer_id == setup.customer.id
    assert register[0].customer_name == setup.customer.display_name


def test_the_register_says_whether_the_prices_still_stand() -> None:
    """D-RPT-19: expiry is a date, and the register only showed the status.

    A SENT offer past `valid_until` still reads SENT, so the register said
    nothing about whether it could still be acted on -- the one question a
    list of live offers is read to answer. `is_expired` rides beside the
    status, derived the way the document's own response derives it.
    """
    session = _session_factory()()
    setup = _Setup(session)
    row = setup.accepted()

    [record] = setup.service.register_report(firm_scope=setup.firm.id)
    assert record.is_expired is False

    row.valid_until = utc_now().date() - timedelta(days=1)
    session.commit()

    [lapsed] = setup.service.register_report(firm_scope=setup.firm.id)
    assert lapsed.is_expired is True
    assert lapsed.status == QuotationStatus.ACCEPTED, "the stored status is untouched"


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


def test_a_customers_standing_discount_fills_a_line_in() -> None:
    """The rate lives on the customer and reaches the quoted total by itself.

    Nothing client-side supplies it: there is no sales-order or sales-invoice
    line editor at all, conversions happen on the server, and an API client
    would otherwise bypass the arrangement entirely.
    """
    session = _session_factory()()
    setup = _Setup(session)
    setup.customer.default_discount_percent = Decimal("10")
    session.commit()

    row = setup.service.create_quotation(
        setup.payload(), firm_id=setup.firm.id, actor_id=setup.actor_id
    )

    assert row.line_discount_total == Decimal("40.0000")
    assert row.grand_total == Decimal("360.0000")
    # And the document says what the standing rate was, so a line that
    # overrode it is still readable as a decision a year later.
    assert row.customer_discount_percent == Decimal("10.0000")
    line = session.scalar(select(SalesQuotationLine))
    assert line is not None
    assert line.discount_percent == Decimal("10.0000")


def test_a_line_can_refuse_the_standing_discount() -> None:
    """An explicit zero is an instruction, not a silence."""
    session = _session_factory()()
    setup = _Setup(session)
    setup.customer.default_discount_percent = Decimal("10")
    session.commit()

    row = setup.service.create_quotation(
        setup.payload(discount_percent=Decimal("0")),
        firm_id=setup.firm.id,
        actor_id=setup.actor_id,
    )

    assert row.line_discount_total == Decimal("0.0000")
    assert row.grand_total == Decimal("400.0000")
    # The snapshot still records what the customer was on.
    assert row.customer_discount_percent == Decimal("10.0000")


def test_a_discount_larger_than_the_line_is_refused() -> None:
    """It used to produce a negative taxable value and zero tax on top."""
    session = _session_factory()()
    setup = _Setup(session)

    payload = setup.payload()
    payload.lines[0].discount_amount = Decimal("5000")

    with pytest.raises(ValidationError, match="cannot exceed"):
        setup.service.create_quotation(
            payload, firm_id=setup.firm.id, actor_id=setup.actor_id
        )


def test_a_bill_discount_comes_off_the_whole_document() -> None:
    """One discount negotiated once, rather than typed on every line."""
    session = _session_factory()()
    setup = _Setup(session)

    payload = setup.payload()
    payload.bill_discount_percent = Decimal("10")

    row = setup.service.create_quotation(
        payload, firm_id=setup.firm.id, actor_id=setup.actor_id
    )

    # 4 x 100 = 400, less 10% of the whole = 40.
    assert row.bill_discount_amount == Decimal("40.0000")
    assert row.bill_discount_percent == Decimal("10.0000")
    assert row.subtotal == Decimal("360.0000")
    assert row.grand_total == Decimal("360.0000")


def test_the_bill_discount_reaches_every_line() -> None:
    """Stored on the line, because it is what the tax was computed on.

    A document-level deduction that never touches a taxable value reduces no
    tax at all -- which is what `header_discount_amount` does on a purchase
    order, and the reason that shape was not copied here.
    """
    session = _session_factory()()
    setup = _Setup(session)

    payload = setup.payload()
    payload.lines.append(
        QuotationLineWrite(
            line_number=2,
            product_id=setup.product.id,
            quantity=Decimal("4"),
            unit_price=PRICE,
        )
    )
    payload.bill_discount_amount = Decimal("80")

    setup.service.create_quotation(
        payload, firm_id=setup.firm.id, actor_id=setup.actor_id
    )

    shares = [
        line.bill_discount_amount
        for line in session.scalars(
            select(SalesQuotationLine).order_by(SalesQuotationLine.line_number)
        ).all()
    ]
    # Two lines of equal value, so half each, and the two sum to the whole.
    assert shares == [Decimal("40.0000"), Decimal("40.0000")]


def test_a_bill_discount_comes_off_what_the_lines_discounted_to() -> None:
    """Never off the gross.

    Off the gross, each discount is computed as though the other had not
    happened, and the two together take off more than either was agreed to.
    """
    session = _session_factory()()
    setup = _Setup(session)

    payload = setup.payload(discount_percent=Decimal("10"))
    payload.bill_discount_percent = Decimal("10")

    row = setup.service.create_quotation(
        payload, firm_id=setup.firm.id, actor_id=setup.actor_id
    )

    # 400 gross, 40 off the line leaves 360, then 36 off that -- not 40 and 40.
    assert row.line_discount_total == Decimal("40.0000")
    assert row.bill_discount_amount == Decimal("36.0000")
    assert row.subtotal == Decimal("324.0000")


def test_a_bill_discount_larger_than_the_document_is_refused() -> None:
    """The same refusal a line gets, for the same reason."""
    session = _session_factory()()
    setup = _Setup(session)

    payload = setup.payload()
    payload.bill_discount_amount = Decimal("5000")

    with pytest.raises(ValidationError, match="cannot exceed"):
        setup.service.create_quotation(
            payload, firm_id=setup.firm.id, actor_id=setup.actor_id
        )


def test_a_converted_order_carries_the_deal_not_the_shares() -> None:
    """The order re-splits it across whatever lines it ends up with.

    Copying each line's share instead would agree only for as long as the two
    documents held the same lines.
    """
    session = _session_factory()()
    setup = _Setup(session)
    payload = setup.payload()
    payload.bill_discount_percent = Decimal("10")
    quote = setup.service.create_quotation(
        payload, firm_id=setup.firm.id, actor_id=setup.actor_id
    )
    setup.service.send_quotation(
        quote.id, firm_scope=setup.firm.id, actor_id=setup.actor_id
    )
    setup.service.accept_quotation(
        quote.id, firm_scope=setup.firm.id, actor_id=setup.actor_id
    )

    _, order = setup.service.convert_quotation(
        quote.id, firm_scope=setup.firm.id, actor_id=setup.actor_id
    )

    assert order.bill_discount_amount == Decimal("40.0000")
    assert order.subtotal == Decimal("360.0000")
    line = session.scalar(
        select(SalesOrderLine).where(SalesOrderLine.sales_order_id == order.id)
    )
    assert line is not None
    assert line.bill_discount_amount == Decimal("40.0000")


def test_a_line_records_where_its_rate_came_from() -> None:
    """Typed and resolved rates look alike on the line; the source tells them apart.

    A revision keeps a rate somebody typed and prices an inherited one
    afresh, which needs the document to say which it was. Found on the
    2026-09-13 manual pass (plan item 9.2): the desktop re-sent every stored
    rate as typed, so a line moved from 12 to 18 units kept the 2% of the
    first ladder step instead of taking the 6.75% of the third.
    """
    session = _session_factory()()
    setup = _Setup(session)
    setup.customer.default_discount_percent = Decimal("10")
    session.commit()

    inherited = setup.service.create_quotation(
        setup.payload(), firm_id=setup.firm.id, actor_id=setup.actor_id
    )
    typed = setup.service.create_quotation(
        setup.payload(discount_percent=Decimal("4")),
        firm_id=setup.firm.id,
        actor_id=setup.actor_id,
    )
    sources = {
        row.id: [
            line.discount_source
            for line in session.scalars(
                select(SalesQuotationLine).where(
                    SalesQuotationLine.sales_quotation_id == row.id
                )
            )
        ]
        for row in (inherited, typed)
    }
    assert sources[inherited.id] == ["customer"]
    assert sources[typed.id] == ["percent"]


def test_a_promotion_reaches_a_quotation_line() -> None:
    """A quotation quotes the firm's live offers, as an order would apply them.

    Found on the 2026-09-13 manual pass (plan item 9.4): a 30-unit line for
    a customer on a 9.25% negotiated list still quoted 9.25%, where the same
    line on a direct order took the BULK5 promotion's 7.5% -- the quotation
    service priced with the price list and the standing rate only and never
    asked the promotion engine. And the conversion carries the quoted rate
    onto the order as agreed, so no promotion could ever reach an order that
    began as a quotation. A quotation claims nothing: the engine is asked and
    no redemption is staged.
    """
    session = _session_factory()()
    setup = _Setup(session)
    promotion = Promotion(
        firm_id=setup.firm.id,
        code="TENOFF",
        name="Ten percent off",
        priority=10,
        status=PromotionStatus.ACTIVE.value,
        allow_stacking=True,
        version_group_id=uuid4(),
        version_number=1,
    )
    session.add(promotion)
    session.flush()
    session.add(
        PromotionAction(
            firm_id=setup.firm.id,
            promotion_id=promotion.id,
            sequence=1,
            action_type=PromotionActionType.LINE_DISCOUNT_PERCENT.value,
            parameters={"percent": "10"},
        )
    )
    session.commit()

    row = setup.service.create_quotation(
        setup.payload(), firm_id=setup.firm.id, actor_id=setup.actor_id
    )

    line = session.scalar(
        select(SalesQuotationLine).where(
            SalesQuotationLine.sales_quotation_id == row.id
        )
    )
    assert line is not None
    assert line.discount_percent == Decimal("10.0000")
    assert line.discount_source == "promotion"
    assert row.line_discount_total == Decimal("40.0000")
    # An offer is not a claim: nothing is staged against the promotion.
    assert session.scalar(select(func.count()).select_from(PromotionRedemption)) == 0


def _limited_offer(setup: _Setup, *, max_redemptions: int) -> Promotion:
    """Publish a ten-percent offer that may be claimed so many times."""
    promotion = Promotion(
        firm_id=setup.firm.id,
        code="TENOFF",
        name="Ten percent off",
        priority=10,
        status=PromotionStatus.ACTIVE.value,
        allow_stacking=True,
        max_redemptions=max_redemptions,
        version_group_id=uuid4(),
        version_number=1,
    )
    setup.session.add(promotion)
    setup.session.flush()
    setup.session.add(
        PromotionAction(
            firm_id=setup.firm.id,
            promotion_id=promotion.id,
            sequence=1,
            action_type=PromotionActionType.LINE_DISCOUNT_PERCENT.value,
            parameters={"percent": "10"},
        )
    )
    setup.session.commit()
    return promotion


def test_a_converted_order_claims_the_offer_it_was_quoted() -> None:
    """D-SELL-9: an order from a quotation claims like one raised directly.

    Each line was handed to the order with both its percentage and its
    amount, so the order took it as priced by hand: the engine skipped it, no
    claim was staged, nothing was counted at approval, and the order read
    `amount` / `typed` (driven on fixture store `fx_t09196pwr_s`:
    QT-2026-2027-000002 took BULK5's 7.5% and became SO-2026-2027-000003 with
    no `promotion_redemptions` row). Two orders converted from quotations for
    an offer limited to one now meet the same refusal two direct orders do.
    """
    session = _session_factory()()
    setup = _Setup(session)
    _limited_offer(setup, max_redemptions=1)
    first = setup.accepted()
    second = setup.accepted()

    _, order = setup.service.convert_quotation(
        first.id, firm_scope=setup.firm.id, actor_id=setup.actor_id
    )
    _, other = setup.service.convert_quotation(
        second.id, firm_scope=setup.firm.id, actor_id=setup.actor_id
    )

    line = session.scalar(
        select(SalesOrderLine).where(SalesOrderLine.sales_order_id == order.id)
    )
    assert line is not None
    assert line.discount_source == "promotion"
    assert line.discount_amount == Decimal("40.0000"), "the quoted price stands"
    assert order.bill_discount_source == "none"
    pending = session.scalars(
        select(PromotionRedemption).where(
            PromotionRedemption.document_id == order.id,
            PromotionRedemption.is_deleted.is_(False),
        )
    ).all()
    assert [row.status for row in pending] == ["PENDING"]

    orders = SalesOrderService(session)
    orders.approve_order(order.id, firm_scope=setup.firm.id, actor_id=setup.actor_id)
    assert pending[0].status == "CLAIMED"
    with pytest.raises(ValidationError, match="TENOFF"):
        orders.approve_order(
            other.id, firm_scope=setup.firm.id, actor_id=setup.actor_id
        )


def test_a_discount_typed_on_the_quotation_carries_over_as_typed() -> None:
    """What somebody typed is the agreement, and says so on the order."""
    session = _session_factory()()
    setup = _Setup(session)
    _limited_offer(setup, max_redemptions=5)
    row = setup.accepted(discount_percent=Decimal("5"))

    _, order = setup.service.convert_quotation(
        row.id, firm_scope=setup.firm.id, actor_id=setup.actor_id
    )

    line = session.scalar(
        select(SalesOrderLine).where(SalesOrderLine.sales_order_id == order.id)
    )
    assert line is not None
    assert line.discount_source == "percent"
    assert line.discount_percent == Decimal("5.0000")
    assert (
        session.scalar(
            select(func.count())
            .select_from(PromotionRedemption)
            .where(PromotionRedemption.is_deleted.is_(False))
        )
        == 0
    ), "a line priced by hand takes no offer, so claims none"


def _offers_on_the_bill(setup: _Setup) -> Product:
    """Publish an offer on the bill, free shipping and a gift; return the gift.

    The three benefits a quotation used to leave out while the order it
    became took all three (D-SELL-32).
    """
    gift = Product(
        firm_id=setup.firm.id,
        code="MUG-001",
        name="Mug MUG-001",
        product_type="STOCK_ITEM",
        status="ACTIVE",
    )
    setup.session.add(gift)
    setup.session.flush()
    for priority, code, action_type, parameters in (
        (10, "BILL20", PromotionActionType.BILL_DISCOUNT_AMOUNT, {"amount": "20"}),
        (20, "FREESHIP", PromotionActionType.FREE_SHIPPING, {}),
        (
            30,
            "MUG",
            PromotionActionType.FREE_PRODUCT,
            {"free_product_id": str(gift.id), "free_quantity": "1"},
        ),
    ):
        promotion = Promotion(
            firm_id=setup.firm.id,
            code=code,
            name=code.title(),
            priority=priority,
            status=PromotionStatus.ACTIVE.value,
            allow_stacking=True,
            version_group_id=uuid4(),
            version_number=1,
        )
        setup.session.add(promotion)
        setup.session.flush()
        setup.session.add(
            PromotionAction(
                firm_id=setup.firm.id,
                promotion_id=promotion.id,
                sequence=1,
                action_type=action_type.value,
                parameters=parameters,
            )
        )
    setup.session.commit()
    return gift


def test_a_quotation_shows_the_offers_an_order_would_take() -> None:
    """D-SELL-32: the bill discount, free shipping and a gift reach the quote.

    Driven 2026-09-19 on ``fx_t0919q38d_s``: 60 detergent at 84 with 150
    freight quoted 5,678.16 as QT-2026-2027-000001, while the same order
    raised directly read 5,265.16 -- BIGORDER's 200 off the bill, FREESHIP's
    150 and three MUGGIFT mugs were the order's alone. The quotation now
    prices through the same offers and claims none of them.
    """
    session = _session_factory()()
    setup = _Setup(session)
    gift = _offers_on_the_bill(setup)
    payload = setup.payload()
    payload.freight_amount = Decimal("50")

    quote = setup.service.create_quotation(
        payload, firm_id=setup.firm.id, actor_id=setup.actor_id
    )
    order = SalesOrderService(session).create_order(
        SalesOrderCreate(
            customer_id=setup.customer.id,
            branch_id=setup.branch.id,
            warehouse_id=setup.warehouse.id,
            order_date=quote.quotation_date,
            freight_amount=Decimal("50"),
            lines=[
                SalesOrderLineWrite(
                    line_number=1,
                    product_id=setup.product.id,
                    quantity=Decimal("4"),
                    unit_price=PRICE,
                )
            ],
        ),
        firm_id=setup.firm.id,
        actor_id=setup.actor_id,
    )

    assert quote.bill_discount_amount == Decimal("20.0000")
    assert quote.bill_discount_source == "promotion"
    assert quote.freight_amount == Decimal("0.0000")
    assert quote.freight_waived_amount == Decimal("50.0000")
    lines = session.scalars(
        select(SalesQuotationLine)
        .where(SalesQuotationLine.sales_quotation_id == quote.id)
        .order_by(SalesQuotationLine.line_number)
    ).all()
    assert [(line.product_id, line.quantity, line.free_quantity) for line in lines] == [
        (setup.product.id, Decimal("4.0000"), Decimal("0.0000")),
        (gift.id, Decimal("0.0000"), Decimal("1.0000")),
    ]
    assert quote.grand_total == order.grand_total == Decimal("380.0000")
    # An offer is not a claim: only the order staged anything.
    assert (
        session.scalar(
            select(func.count())
            .select_from(PromotionRedemption)
            .where(PromotionRedemption.document_id == quote.id)
        )
        == 0
    )


def test_a_converted_order_finds_the_quoted_offers_again() -> None:
    """The order is handed what was typed, and asks the offers itself.

    The bill discount, the waived delivery and the gift are the offers', so
    the order re-derives them on its own date and stages their claims, as
    D-SELL-9 settled for line discounts -- rather than inheriting them as
    typed, which would keep them after an offer had run out.
    """
    session = _session_factory()()
    setup = _Setup(session)
    gift = _offers_on_the_bill(setup)
    payload = setup.payload()
    payload.freight_amount = Decimal("50")
    quote = setup.service.create_quotation(
        payload, firm_id=setup.firm.id, actor_id=setup.actor_id
    )
    setup.service.send_quotation(
        quote.id, firm_scope=setup.firm.id, actor_id=setup.actor_id
    )
    setup.service.accept_quotation(
        quote.id, firm_scope=setup.firm.id, actor_id=setup.actor_id
    )

    _, order = setup.service.convert_quotation(
        quote.id, firm_scope=setup.firm.id, actor_id=setup.actor_id
    )

    assert order.bill_discount_source == "promotion"
    assert order.bill_discount_amount == Decimal("20.0000")
    assert order.freight_amount == Decimal("0.0000")
    lines = session.scalars(
        select(SalesOrderLine)
        .where(SalesOrderLine.sales_order_id == order.id)
        .order_by(SalesOrderLine.line_number)
    ).all()
    assert [(line.product_id, line.free_quantity) for line in lines] == [
        (setup.product.id, Decimal("0.0000")),
        (gift.id, Decimal("1.0000")),
    ], "the gift is the order's own, once"
    assert order.grand_total == quote.grand_total
    staged = session.scalars(
        select(PromotionRedemption).where(
            PromotionRedemption.document_id == order.id,
            PromotionRedemption.is_deleted.is_(False),
        )
    ).all()
    assert sorted(row.status for row in staged) == ["PENDING"] * 3


@pytest.mark.parametrize(
    ("status", "words"),
    [
        ("INACTIVE", "is inactive"),
        ("DRAFT", "is still a draft"),
        ("ARCHIVED", "is archived"),
    ],
)
def test_a_product_that_is_not_active_is_not_quoted(status: str, words: str) -> None:
    """D-MST-12: the product half of the rule #562 gave the customer.

    Nothing on the sales side read ``products.status``, so a product withdrawn
    from sale was still offered. It is refused by code and name, and no offer
    is written.
    """
    session = _session_factory()()
    setup = _Setup(session)
    setup.product.status = status
    session.commit()

    with pytest.raises(ValidationError) as refused:
        setup.service.create_quotation(
            setup.payload(), firm_id=setup.firm.id, actor_id=setup.actor_id
        )
    session.rollback()

    assert setup.product.code in str(refused.value)
    assert words in str(refused.value)
    assert "new quotation" in str(refused.value)
    assert session.scalar(select(SalesQuotation.id)) is None


def test_an_offer_already_made_is_edited_but_takes_no_withdrawn_line() -> None:
    """An edit keeping the product saves; one adding a withdrawn one does not."""
    session = _session_factory()()
    setup = _Setup(session)
    quotation = setup.service.create_quotation(
        setup.payload(), firm_id=setup.firm.id, actor_id=setup.actor_id
    )
    withdrawn = Product(
        firm_id=setup.firm.id,
        code="SKU-GONE",
        name="Withdrawn",
        product_type="STOCK_ITEM",
        status="INACTIVE",
    )
    session.add(withdrawn)
    session.commit()

    kept = setup.service.update_quotation(
        quotation.id, setup.payload(), firm_scope=setup.firm.id, actor_id=uuid4()
    )
    assert kept.id == quotation.id

    payload = setup.payload()
    payload.lines.append(
        QuotationLineWrite(
            line_number=2,
            product_id=withdrawn.id,
            quantity=Decimal("1"),
            unit_price=PRICE,
        )
    )
    with pytest.raises(ValidationError, match="is inactive"):
        setup.service.update_quotation(
            quotation.id, payload, firm_scope=setup.firm.id, actor_id=uuid4()
        )


def test_the_quotation_reports_take_a_window_and_a_page() -> None:
    """D-RPT-18: every report was the firm's whole history.

    Both are read on the quotation's own `quotation_date`, both ends
    inclusive, with `total_records` counting the matches rather than the page,
    and a page above the cap refused with a 422.
    """
    from app.quotation.api.router import (
        quotation_conversion,
        quotation_register,
        router,
    )
    from tests.unit.report_windows import assert_page_size_is_bounded, report_scope

    session = _session_factory()()
    setup = _Setup(session)
    today = utc_now().date()
    days = [today - timedelta(days=2), today - timedelta(days=1), today]
    for day in days:
        setup.service.create_quotation(
            setup.payload(quotation_date=day),
            firm_id=setup.firm.id,
            actor_id=setup.actor_id,
        )
    scope = report_scope(setup.firm.id)

    page = quotation_register(
        scope=scope,
        db=session,
        from_date=days[1],
        to_date=days[2],
        page=1,
        page_size=1,
    )
    assert page.pagination.total_records == 2
    assert [row.quotation_date for row in page.data] == [days[2]]

    [row] = quotation_conversion(
        scope=scope, db=session, from_date=days[0], to_date=days[1]
    ).data
    assert row.quoted_count == 2

    assert_page_size_is_bounded(
        router,
        "/api/v1/quotations/reports/register",
        "/api/v1/quotations/reports/conversion",
    )
