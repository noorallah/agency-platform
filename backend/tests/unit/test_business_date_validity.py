"""A validity window is judged on the firm's own day (D-CFG-25).

"Has it expired", "has the period ended", "is it in force today" -- each read
the UTC day, which until 05:30 in India is yesterday: a batch going out of
date on the 6th still had "1 day" at 01:00 on the 6th, a contract that ended
on the 5th could still be approved, and a period that closed last night could
not be accrued until the morning.

Every case freezes the clock at 19:30 UTC on the 5th -- 01:00 on the 6th in
India -- for a firm whose country is ``IN``.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.batch_serial.api.router import batch_availability
from app.batch_serial.services.batch_serial_service import BatchSerialService
from app.commission.schemas.payout import CommissionPayoutAccrue
from app.commission.services.payout_service import CommissionPayoutService
from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.core.utils import dates
from app.einvoice.services.reporting_window import refuse_if_late
from app.inventory.models import InventoryRecord
from app.inventory.services import InventoryService
from app.loyalty.models import LoyaltyEntry, LoyaltyEntryKind
from app.loyalty.services.loyalty_service import LoyaltyService
from app.products.services.price_revisions import (
    PriceRevisionService,
    PriceRevisionWrite,
)
from app.rate_contracts.schemas import RateContractCreate
from app.rate_contracts.services.rate_contract_service import RateContractService
from app.trade_licences.schemas import TradeLicenceWrite
from app.trade_licences.services.trade_licence_service import TradeLicenceService
from app.vendors.services.supplier_catalogue import (
    SupplierCatalogueService,
    SupplierProductWrite,
)
from tests.unit.test_batch_picker import _Shop as _BatchShop
from tests.unit.test_customer_rebates import _accrue, _agreement, _bill
from tests.unit.test_customer_rebates import _books as _rebate_books
from tests.unit.test_einvoice import _Books as _EInvoiceBooks
from tests.unit.test_einvoice import _session_factory as _einvoice_session
from tests.unit.test_einvoice_reporting_window import _settings
from tests.unit.test_loyalty import _Books as _LoyaltyBooks
from tests.unit.test_loyalty import _session_factory as _loyalty_session
from tests.unit.test_purchase_chain_synthesis import _Firm

# Fixtures here type their document numbers; see conftest (D-CFG-2).
pytestmark = pytest.mark.typed_document_numbers

#: 19:30 UTC on the 5th: 01:00 on the 6th in India.
ONE_IN_THE_MORNING = datetime(2026, 10, 5, 19, 30, tzinfo=UTC)
THE_5TH = date(2026, 10, 5)
THE_6TH = date(2026, 10, 6)


@pytest.fixture(autouse=True)
def _one_in_the_morning(monkeypatch: pytest.MonkeyPatch) -> None:
    """Freeze the clock the business day is read from."""
    monkeypatch.setattr(dates, "utc_now", lambda: ONE_IN_THE_MORNING)


def _firm(code: str) -> _Firm:
    """Build the buying test firm on a fresh store."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return _Firm(sessionmaker(bind=engine, expire_on_commit=False)(), code=code)


def test_a_batch_expiring_today_has_no_days_left() -> None:
    """It read "1 day" at 01:00 on its last day, and tomorrow's read "2 days".

    Whether a batch dated today is *expired* is not this test's business: the
    picker says so on the day itself (``expired_condition`` is ``<=``) while
    dispatch passes a batch over only from the day after, and neither rule
    moved here. What moved is the day both are counted from.
    """
    shop = _BatchShop()
    shop.batches["MARCH"].expiry_date = THE_6TH
    shop.batches["JUNE"].expiry_date = THE_6TH + timedelta(days=1)
    shop.session.commit()

    rows = batch_availability(
        scope=SimpleNamespace(firm_id=shop.firm_id),  # type: ignore[arg-type]
        product_id=shop.product.id,
        warehouse_id=shop.warehouse_id,
        storage_node_id=None,
        as_of=None,
        quantity=Decimal("0"),
        sales_order_line_id=None,
        near_expiry_days=None,
        customer_id=None,
        db=shop.session,
    ).data

    assert rows is not None
    by_name = {row.batch_number: row for row in rows}
    # Expired ON its date is the picker's standing rule (seen live, kept).
    assert (by_name["MARCH"].days_to_expiry, by_name["MARCH"].expired) == (0, True)
    assert (by_name["JUNE"].days_to_expiry, by_name["JUNE"].expired) == (1, False)


def test_stock_that_went_out_of_date_yesterday_is_not_held_for_an_order() -> None:
    """Dispatch's rule: a batch dated the 5th is passed over on the 6th."""
    shop = _BatchShop()
    shop.batches["MARCH"].expiry_date = THE_5TH
    shop.batches["JUNE"].expiry_date = THE_6TH
    shop.session.commit()
    rows = list(
        shop.session.scalars(
            select(InventoryRecord).where(
                InventoryRecord.batch_id.in_(
                    [shop.batches["MARCH"].id, shop.batches["JUNE"].id]
                )
            )
        )
    )

    kept, expired, _ = InventoryService(shop.session)._without_expired(
        rows, firm_scope=shop.firm_id, as_of=None
    )

    assert {row.batch_id for row in kept} == {shop.batches["JUNE"].id}
    assert set(expired) == {shop.batches["MARCH"].id}


def test_the_expiry_dashboard_counts_today_as_the_firms_today() -> None:
    """Expired today is the batch dated the 6th, not the one dated the 5th."""
    shop = _BatchShop()
    shop.batches["MARCH"].expiry_date = THE_6TH
    shop.session.commit()

    dashboard = BatchSerialService(shop.session).expiry_dashboard(
        firm_scope=shop.firm_id
    )

    assert dashboard.expired_today == 1


def test_a_rate_contract_that_ended_yesterday_is_not_approved() -> None:
    """Ended on the 5th: at 01:00 on the 6th it could still be approved."""
    firm = _firm("RCNT")
    service = RateContractService(firm.session)

    def contract(valid_to: date) -> object:
        return service.create(
            RateContractCreate.model_validate(
                {
                    "vendor_id": firm.vendor.id,
                    "valid_from": "2026-09-01",
                    "valid_to": valid_to.isoformat(),
                    "reference": f"AGR-{valid_to.day}",
                    "lines": [{"product_id": firm.product.id, "rate": "70"}],
                }
            ),
            firm_id=firm.firm.id,
            actor_id=firm.actor_id,
        )

    ended = contract(THE_5TH)
    with pytest.raises(ValidationError, match="ended on 2026-10-05"):
        service.approve(ended.id, firm_id=firm.firm.id, actor_id=firm.actor_id)  # type: ignore[attr-defined]
    firm.session.rollback()

    running = contract(THE_6TH)
    approved = service.approve(
        running.id, firm_id=firm.firm.id, actor_id=firm.actor_id  # type: ignore[attr-defined]
    )
    assert service.responses([approved])[0].status == "ACTIVE"


def test_a_price_revision_from_today_is_the_one_in_force() -> None:
    """New rates from the 6th are current at 01:00 on the 6th."""
    firm = _firm("PRNT")
    service = PriceRevisionService(firm.session)
    service.add(
        firm.product.id,
        PriceRevisionWrite(
            effective_from=THE_6TH,
            selling_price=Decimal("120"),
            purchase_price=Decimal("95"),
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )

    [row] = service.list_for(firm.product.id, firm_id=firm.firm.id)

    assert row.is_current


def test_a_suppliers_quote_from_today_is_in_force() -> None:
    """The catalogue row effective the 6th is the current one."""
    firm = _firm("CATNT")
    service = SupplierCatalogueService(firm.session)
    service.add(
        firm.vendor.id,
        SupplierProductWrite(
            product_id=firm.product.id,
            supplier_product_code="BR-W1",
            unit_price=Decimal("10"),
            pack_size=Decimal("12"),
            effective_from=THE_6TH,
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )

    rows = service.list_rows(firm.vendor.id, firm_id=firm.firm.id)

    assert [row.effective_from for row in rows] == [THE_6TH]


def test_a_licence_that_ran_out_yesterday_reads_expired() -> None:
    """Valid to the 5th: expired on the 6th, one day ago."""
    firm = _firm("LICNT")
    service = TradeLicenceService(firm.session)
    types = {row.code: row for row in service.list_types(firm.firm.id, firm.actor_id)}
    service.create_licence(
        TradeLicenceWrite.model_validate(
            {
                "licence_type_id": types["FSSAI"].id,
                "holder_type": "FIRM",
                "licence_number": "LIC-1",
                "valid_to": THE_5TH,
            }
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )

    [listed] = service.list_licences(firm_id=firm.firm.id)

    assert (listed.standing, listed.days_to_expiry) == ("EXPIRED", -1)


def test_a_rebate_period_that_ended_yesterday_can_be_accrued() -> None:
    """The period ran to the 5th; the morning of the 6th is "after that"."""
    books = _rebate_books()
    _bill(books, "SI-1", "5000", on=date(2026, 9, 20))
    row = _agreement(books, period=(date(2026, 9, 6), THE_5TH))

    accrued = _accrue(books, row)

    assert accrued.status == "ACCRUED"


def test_a_commission_period_that_ended_yesterday_can_be_accrued() -> None:
    """And one ending on the 6th has not ended yet."""
    books = _rebate_books()
    service = CommissionPayoutService(books.session)

    service._assert_period_has_ended(
        CommissionPayoutAccrue(period_start=date(2026, 9, 6), period_end=THE_5TH),
        firm_id=books.firm.id,
    )
    with pytest.raises(ValidationError, match="has not ended"):
        service._assert_period_has_ended(
            CommissionPayoutAccrue(period_start=date(2026, 9, 6), period_end=THE_6TH),
            firm_id=books.firm.id,
        )


def test_points_that_ran_out_yesterday_lapse_in_tonights_sweep() -> None:
    """Good until the 5th; a sweep with no date at 01:00 on the 6th takes them."""
    books = _LoyaltyBooks(_loyalty_session()())
    earned = books.earn(books.invoice("SI-1", total="1000"))
    assert earned is not None
    earned.expires_on = THE_5TH
    books.session.commit()

    lapsed = LoyaltyService(books.session).expire(
        firm_scope=books.firm.id, actor_id=uuid4()
    )

    assert lapsed == 1
    taken = books.session.scalar(
        select(LoyaltyEntry).where(LoyaltyEntry.kind == LoyaltyEntryKind.EXPIRED.value)
    )
    assert taken is not None and taken.earned_on == THE_6TH


def test_the_thirty_day_limit_counts_from_the_firms_today() -> None:
    """A bill whose last day was the 5th is refused at 01:00 on the 6th."""
    books = _EInvoiceBooks(_einvoice_session()())
    _settings(books, einvoice_from=date(2020, 1, 1), thirty_from=date(2020, 1, 1))

    refuse_if_late(
        books.session,
        firm_scope=books.firm.id,
        number="SI-ON-TIME",
        on=THE_6TH - timedelta(days=30),
    )
    with pytest.raises(ValidationError, match="05 Oct 2026"):
        refuse_if_late(
            books.session,
            firm_scope=books.firm.id,
            number="SI-LATE",
            on=THE_5TH - timedelta(days=30),
        )
