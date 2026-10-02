"""A batch's own MRP and selling price (backlog 79 row 7).

Captured on the receipt and kept on the batch, shown in the picker, printed on
the challan and the bill one row per batch, and no bill may charge more than
the MRP printed on the batch it ships -- tax included, freight left out.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.batch_serial.schemas import BatchSaleSettingsWrite
from app.batch_serial.services import BatchSalePolicyService, BatchSerialService
from app.core.exceptions import ValidationError
from app.sales_invoice.services.invoice_print_service import SalesInvoicePrintService
from tests.unit.test_counter_bill_batches import _Counter


def test_a_receipt_sets_a_new_batch_mrp_and_fills_one_without() -> None:
    """New batch: set. Existing with none: filled. Existing with one: kept."""
    shop = _Counter()
    service = BatchSerialService(shop.session)

    fresh = service.resolve_for_receipt(
        firm_scope=shop.firm.id,
        actor_id=shop.actor,
        product_id=shop.drug.id,
        batch_number="NEW",
        mrp=Decimal("120.00"),
        selling_price=Decimal("95.00"),
    )
    assert (fresh.mrp, fresh.selling_price) == (Decimal("120.00"), Decimal("95.00"))

    early = service.resolve_for_receipt(
        firm_scope=shop.firm.id,
        actor_id=shop.actor,
        product_id=shop.drug.id,
        batch_number="EARLY",
        mrp=Decimal("110.00"),
    )
    assert early.mrp == Decimal("110.00")

    again = service.resolve_for_receipt(
        firm_scope=shop.firm.id,
        actor_id=shop.actor,
        product_id=shop.drug.id,
        batch_number="EARLY",
        mrp=Decimal("999.00"),
    )
    assert again.mrp == Decimal("110.00"), "the print on a batch does not change"


def test_the_picker_shows_each_batch_mrp_and_rate() -> None:
    """Availability carries both, per batch."""
    shop = _Counter()
    shop.batches["LATE"].mrp = Decimal("130.00")
    shop.batches["LATE"].selling_price = Decimal("100.00")
    shop.session.commit()

    rows = BatchSerialService(shop.session).batch_availability(
        firm_scope=shop.firm.id,
        product_id=shop.drug.id,
        warehouse_id=shop.warehouse.id,
        as_of=date(2026, 8, 4),
    )
    late = next(row for row in rows if row.batch_number == "LATE")
    assert (late.mrp, late.selling_price) == (Decimal("130.00"), Decimal("100.00"))


def test_price_from_batch_is_a_firm_setting_off_by_default() -> None:
    """Off until the firm turns it on; saved and read back."""
    shop = _Counter()
    policy = BatchSalePolicyService(shop.session)
    assert policy.settings_response(shop.firm.id).price_from_batch is False

    policy.update_settings(
        BatchSaleSettingsWrite(
            near_expiry_days=30,
            near_expiry_policy="WARN",
            fefo_skip_policy="RECORD",
            near_expiry_below_floor=True,
            price_from_batch=True,
        ),
        firm_id=shop.firm.id,
        actor_id=shop.actor,
    )
    assert policy.settings_response(shop.firm.id).price_from_batch is True


def test_a_bill_above_the_batch_mrp_is_refused() -> None:
    """LATE says 90 on the pack; four at 100 cannot be billed."""
    shop = _Counter()
    shop.batches["LATE"].mrp = Decimal("90.00")
    shop.session.commit()
    draft = shop.bills.create_invoice(
        shop.bill([shop.pick("LATE")]), firm_id=shop.firm.id, actor_id=shop.actor
    )

    with pytest.raises(ValidationError, match="above the MRP of 90.00"):
        shop.bills.approve_invoice(
            draft.id, firm_scope=shop.firm.id, actor_id=shop.actor
        )


def test_a_batch_with_no_mrp_is_judged_on_the_products() -> None:
    """The product's MRP stands in for a batch that carries none."""
    shop = _Counter()
    shop.drug.mrp = Decimal("80.00")
    shop.session.commit()
    draft = shop.bills.create_invoice(
        shop.bill([shop.pick("LATE")]), firm_id=shop.firm.id, actor_id=shop.actor
    )

    with pytest.raises(ValidationError, match="above the MRP of 80.00"):
        shop.bills.approve_invoice(
            draft.id, firm_scope=shop.firm.id, actor_id=shop.actor
        )


def test_within_the_mrp_the_bill_goes_and_prints_it_per_batch() -> None:
    """Split across two batches with their own MRPs: one row each."""
    shop = _Counter()
    shop.batches["EARLY"].mrp = Decimal("110.00")
    shop.batches["LATE"].mrp = Decimal("120.00")
    shop.session.commit()
    draft = shop.bills.create_invoice(
        shop.bill([shop.pick("EARLY", "1"), shop.pick("LATE", "3")]),
        firm_id=shop.firm.id,
        actor_id=shop.actor,
    )
    bill = shop.bills.approve_invoice(
        draft.id, firm_scope=shop.firm.id, actor_id=shop.actor
    )

    document = SalesInvoicePrintService(shop.session)._document(
        bill, firm_scope=shop.firm.id
    )
    printed = [(line.batch, line.mrp) for line in document.lines]
    assert printed == [("EARLY", Decimal("110.00")), ("LATE", Decimal("120.00"))]
