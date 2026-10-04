"""PG-12 part B (§86 #5): the Bill of Entry, customs duty and IGST on import.

A supplier abroad bills 10 units at 100 USD at 83 (PG-12 part A): the bill
raises its own receipt, so 10 units sit in stock at 8,300 each. Customs
assesses them at 85,000 with 10% basic duty, the 10% surcharge on that and
18% IGST on the lot:

* BCD 8,500, SWS 850 -- a cost of 9,350, with no credit, landed on the stock
  (the average rises from 8,300 to 9,235);
* IGST on 85,000 + 8,500 + 850 = 94,350 at 18% = 16,983, claimed as input tax
  and reported in GSTR-3B 4(A)(1) for August;
* Cr Customs Duty Payable 26,333.

Sessions are shaped like a request's (no autoflush), as in the PG-12 part A
tests.
"""

# ruff: noqa: D103

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi.routing import APIRoute
from sqlalchemy import event, func, select

from app.bill_of_entry.api.router import list_bills_of_entry
from app.bill_of_entry.api.router import router as boe_router
from app.bill_of_entry.models import BillOfEntry
from app.bill_of_entry.schemas import BillOfEntryCreate, BillOfEntryUpdate
from app.bill_of_entry.services import BillOfEntryService, compute_line_duty
from app.common.scope import ResolvedFirmScope
from app.core.exceptions import ValidationError
from app.finance.models import JournalEntry, JournalLine
from app.finance.services.control_accounts import ControlAccountPurpose
from app.gst_returns.services.gstr_service import GstReturnService
from app.identity.system_seed import PERMISSION_GROUPS, ROLE_PERMISSION_CODES
from app.inventory.services.inventory_service import InventoryService
from app.purchase_invoice.models import PurchaseInvoice
from tests.unit.test_cash_purchase import _chain_firm
from tests.unit.test_foreign_currency_bills import _usd_bill
from tests.unit.test_purchase_chain_synthesis import _Firm

pytestmark = pytest.mark.typed_document_numbers

D = Decimal
ON = date(2026, 8, 20)
GSTIN = "29AAACA1234A1Z5"


# -- the duty arithmetic ----------------------------------------------------


def test_bcd_then_sws_on_bcd_then_igst_on_the_lot() -> None:
    duty = compute_line_duty(
        assessable_value=D("100000"), bcd_rate=D("10"), igst_rate=D("18")
    )
    assert duty.bcd_amount == D("10000.00")
    assert duty.sws_rate == D("10")
    assert duty.sws_amount == D("1000.00")
    assert duty.igst_base == D("111000.00")
    assert duty.igst_amount == D("19980.00")
    assert duty.cess_amount == D("0")
    assert duty.customs_duty == D("11000.00")
    assert duty.total_duty == D("30980.00")


def test_a_typed_amount_wins_over_its_rate() -> None:
    duty = compute_line_duty(
        assessable_value=D("100000"),
        bcd_rate=D("10"),
        bcd_amount=D("9999"),
        sws_rate=D("0"),
        igst_rate=D("18"),
        cess_amount=D("250"),
    )
    assert duty.bcd_amount == D("9999.00")
    # A surcharge rate of zero is a typed answer, not "take the default".
    assert duty.sws_amount == D("0.00")
    assert duty.igst_base == D("109999.00")
    assert duty.igst_amount == D("19799.82")
    typed = compute_line_duty(
        assessable_value=D("100000"),
        bcd_rate=D("10"),
        sws_amount=D("1001"),
        igst_rate=D("18"),
        igst_amount=D("20000"),
    )
    assert typed.sws_amount == D("1001.00")
    assert typed.igst_amount == D("20000.00")
    assert typed.total_duty == D("10000.00") + D("1001.00") + D("20000.00")


# -- the document ------------------------------------------------------------


def _firm() -> _Firm:
    firm = _chain_firm()
    firm.firm.gst_number = GSTIN
    firm.session.commit()
    return firm


def _create(
    firm: _Firm,
    *,
    bills: list[PurchaseInvoice] | None = None,
    boe_number: str = "1234567",
    **line: object,
) -> BillOfEntry:
    data = BillOfEntryCreate.model_validate(
        {
            "boe_number": boe_number,
            "boe_date": ON.isoformat(),
            "port_code": "innsa1",
            "vendor_id": firm.vendor.id,
            "currency_code": "usd",
            "exchange_rate": "84.5",
            "purchase_invoice_ids": [bill.id for bill in bills or []],
            "lines": [
                {
                    "product_id": firm.product.id,
                    "quantity": "10",
                    "assessable_value": "85000",
                    "bcd_rate": "10",
                    "igst_rate": "18",
                    **line,
                }
            ],
        }
    )
    return BillOfEntryService(firm.session).create(
        data, firm_id=firm.firm.id, actor_id=firm.actor_id
    )


def _post(firm: _Firm, row: BillOfEntry) -> BillOfEntry:
    return BillOfEntryService(firm.session).post(
        row.id, firm_id=firm.firm.id, actor_id=firm.actor_id
    )


def _average(firm: _Firm) -> Decimal:
    return D(
        str(
            InventoryService(firm.session)
            .valuation_for(firm_scope=firm.firm.id, product_id=firm.product.id)
            .average_cost
        )
    ).quantize(D("0.01"))


def _import_itc(firm: _Firm, first: date, last: date) -> dict[str, Any]:
    summary = GstReturnService(firm.session).gstr3b(
        firm_scope=firm.firm.id, from_date=first, to_date=last
    )
    section = summary["itc_import_goods"]
    assert isinstance(section, dict)
    net = summary["net_itc"]
    assert isinstance(net, dict)
    return {**section, "net_igst": net["integrated_tax"]}


def test_a_draft_works_the_duty_out_and_links_the_foreign_bill() -> None:
    firm = _firm()
    bill = _usd_bill(firm)
    row = _create(firm, bills=[bill])

    assert row.status == "DRAFT"
    assert row.document_number
    assert (row.port_code, row.currency_code) == ("INNSA1", "USD")
    assert row.basic_customs_duty == D("8500.00")
    assert row.social_welfare_surcharge == D("850.00")
    assert row.igst_amount == D("16983.00")
    assert row.total_duty == D("26333.00")
    (view,) = BillOfEntryService(firm.session).responses([row])
    assert view.customs_duty == D("9350.00")
    assert view.lines[0].igst_base == D("94350.00")
    (linked,) = view.purchase_invoices
    assert (linked.currency_code, linked.exchange_rate) == ("USD", D("83"))
    assert linked.base_grand_total == D("83000.00")
    # The receipt the bill raised for itself is reached through the bill.
    (receipt,) = view.goods_receipts
    assert receipt.via_invoice is True
    assert receipt.status == "COMPLETED"
    # Nothing is booked, and nothing is claimed, until it is posted.
    assert firm.balance(ControlAccountPurpose.CUSTOMS_PAYABLE) == 0
    assert _import_itc(firm, date(2026, 8, 1), date(2026, 8, 31))[
        "integrated_tax"
    ] == pytest.approx(0)


def test_posting_lands_the_duty_on_stock_and_claims_the_igst() -> None:
    firm = _firm()
    bill = _usd_bill(firm)
    assert _average(firm) == D("8300.00")
    inventory_before = firm.balance(ControlAccountPurpose.INVENTORY)
    row = _post(firm, _create(firm, bills=[bill]))

    assert row.status == "POSTED"
    assert (row.inventory_amount, row.cogs_amount, row.expense_amount) == (
        D("9350.00"),
        D("0"),
        D("0"),
    )
    assert _average(firm) == D("9235.00")
    assert firm.balance(ControlAccountPurpose.INVENTORY) - inventory_before == D(
        "9350.00"
    )
    assert firm.balance(ControlAccountPurpose.INPUT_TAX_IGST) == D("16983.00")
    assert firm.balance(ControlAccountPurpose.CUSTOMS_PAYABLE) == D("-26333.00")
    assert firm.balance(ControlAccountPurpose.CUSTOMS_DUTY) == 0
    debit, credit = firm.session.execute(
        select(func.sum(JournalLine.debit_amount), func.sum(JournalLine.credit_amount))
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
        .where(JournalEntry.id == row.journal_entry_id)
    ).one()
    assert D(str(debit)) == D(str(credit)) == D("26333.00")
    with pytest.raises(ValidationError, match="Only a draft"):
        _post(firm, row)


def test_duty_with_no_receipt_to_carry_it_is_an_expense() -> None:
    firm = _firm()
    row = _post(firm, _create(firm, igst_rate="0"))

    assert (row.inventory_amount, row.expense_amount) == (D("0"), D("9350.00"))
    assert firm.balance(ControlAccountPurpose.CUSTOMS_DUTY) == D("9350.00")
    assert firm.balance(ControlAccountPurpose.CUSTOMS_PAYABLE) == D("-9350.00")


def test_3b_4a1_claims_the_igst_in_the_bill_of_entry_month_only() -> None:
    firm = _firm()
    bill = _usd_bill(firm)
    _post(firm, _create(firm, bills=[bill], cess_amount="120"))

    august = _import_itc(firm, date(2026, 8, 1), date(2026, 8, 31))
    assert august["integrated_tax"] == pytest.approx(16983.00)
    assert august["cess"] == pytest.approx(120.00)
    assert august["bill_of_entry_count"] == 1
    assert august["net_igst"] == pytest.approx(16983.00)
    september = _import_itc(firm, date(2026, 9, 1), date(2026, 9, 30))
    assert september["integrated_tax"] == pytest.approx(0)
    assert september["bill_of_entry_count"] == 0


def test_cancelling_reverses_the_posting_and_drops_it_from_3b() -> None:
    firm = _firm()
    bill = _usd_bill(firm)
    inventory_before = firm.balance(ControlAccountPurpose.INVENTORY)
    row = _post(firm, _create(firm, bills=[bill]))
    service = BillOfEntryService(firm.session)

    with pytest.raises(ValidationError, match="Say why"):
        service.cancel(row.id, "  ", firm_id=firm.firm.id, actor_id=firm.actor_id)
    row = service.cancel(
        row.id, "Wrong port", firm_id=firm.firm.id, actor_id=firm.actor_id
    )

    assert (row.status, row.cancel_reason) == ("CANCELLED", "Wrong port")
    assert _average(firm) == D("8300.00")
    assert firm.balance(ControlAccountPurpose.INVENTORY) == inventory_before
    assert firm.balance(ControlAccountPurpose.INPUT_TAX_IGST) == 0
    assert firm.balance(ControlAccountPurpose.CUSTOMS_PAYABLE) == 0
    august = _import_itc(firm, date(2026, 8, 1), date(2026, 8, 31))
    assert august["integrated_tax"] == pytest.approx(0)
    assert august["bill_of_entry_count"] == 0
    # Customs' number is free again once the first is cancelled.
    _post(firm, _create(firm, bills=[bill]))


def test_customs_numbers_one_bill_of_entry_once() -> None:
    firm = _firm()
    _post(firm, _create(firm))
    second = _create(firm)
    with pytest.raises(ValidationError, match="already"):
        _post(firm, second)


def test_an_update_leaves_out_what_it_does_not_send() -> None:
    firm = _firm()
    row = _create(firm)
    service = BillOfEntryService(firm.session)

    row = service.update(
        row.id,
        BillOfEntryUpdate.model_validate({"remarks": "Clearing agent: ABC"}),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    assert row.remarks == "Clearing agent: ABC"
    assert (row.currency_code, row.exchange_rate) == ("USD", D("84.5"))
    assert row.total_duty == D("26333.00")
    row = service.update(
        row.id,
        BillOfEntryUpdate.model_validate(
            {
                "lines": [
                    {
                        "product_id": str(firm.product.id),
                        "quantity": "10",
                        "assessable_value": "85000",
                        "bcd_amount": "8000",
                    }
                ]
            }
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    assert (row.basic_customs_duty, row.social_welfare_surcharge) == (
        D("8000.00"),
        D("800.00"),
    )
    assert row.igst_amount == D("0")
    with pytest.raises(ValidationError, match="rate customs assessed"):
        service.update(
            row.id,
            BillOfEntryUpdate.model_validate({"currency_code": "EUR"}),
            firm_id=firm.firm.id,
            actor_id=firm.actor_id,
        )


def test_a_bill_from_another_supplier_is_refused() -> None:
    firm = _firm()
    bill = _usd_bill(firm)
    from app.vendors.models import Vendor

    other = Vendor(
        firm_id=firm.firm.id,
        code="VEN-OTHER",
        name="Other",
        display_name="Other",
        status="ACTIVE",
    )
    firm.session.add(other)
    firm.session.commit()
    data = BillOfEntryCreate.model_validate(
        {
            "boe_number": "7654321",
            "boe_date": ON.isoformat(),
            "port_code": "INMAA1",
            "vendor_id": other.id,
            "purchase_invoice_ids": [bill.id],
            "lines": [
                {
                    "product_id": firm.product.id,
                    "quantity": "1",
                    "assessable_value": "100",
                }
            ],
        }
    )
    with pytest.raises(ValidationError, match="another supplier"):
        BillOfEntryService(firm.session).create(
            data, firm_id=firm.firm.id, actor_id=firm.actor_id
        )


# -- permissions --------------------------------------------------------------


def _route_codes(method: str, suffix: str) -> set[str]:
    route = next(
        item
        for item in boe_router.routes
        if isinstance(item, APIRoute)
        and method in item.methods
        and item.path.endswith(suffix)
    )
    assert isinstance(route, APIRoute)
    codes: set[str] = set()
    pending = list(route.dependant.dependencies)
    while pending:
        dependency = pending.pop()
        code = getattr(dependency.call, "permission_code", None)
        if code:
            codes.add(code)
        pending.extend(dependency.dependencies)
    return codes


def test_posting_needs_purchase_approve_and_typing_needs_manage() -> None:
    assert {"BILL_OF_ENTRY_VIEW", "BILL_OF_ENTRY_MANAGE"} <= set(
        PERMISSION_GROUPS["purchase"]
    )
    assert _route_codes("GET", "/bills-of-entry") == {"BILL_OF_ENTRY_VIEW"}
    assert _route_codes("POST", "/bills-of-entry") == {"BILL_OF_ENTRY_MANAGE"}
    assert _route_codes("PUT", "/{boe_id}") == {"BILL_OF_ENTRY_MANAGE"}
    assert _route_codes("POST", "/{boe_id}/post") == {"PURCHASE_APPROVE"}
    assert _route_codes("POST", "/{boe_id}/cancel") == {"PURCHASE_APPROVE"}
    # A buyer types it; only an approver books the duty.
    executive = ROLE_PERMISSION_CODES["PURCHASE_EXECUTIVE"]
    assert "BILL_OF_ENTRY_MANAGE" in executive
    assert "PURCHASE_APPROVE" not in executive


# -- the list -----------------------------------------------------------------


@contextmanager
def _counted(firm: _Firm) -> Iterator[list[str]]:
    statements: list[str] = []
    engine = firm.session.get_bind()

    def count(*args: object) -> None:
        statements.append(str(args[2]))

    event.listen(engine, "before_cursor_execute", count)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", count)


def test_the_list_page_costs_the_same_at_any_length() -> None:
    firm = _firm()
    bill = _usd_bill(firm)
    # The list reads only the firm off its scope.
    scope = cast(ResolvedFirmScope, SimpleNamespace(firm_id=firm.firm.id))

    def page_cost() -> tuple[int, int]:
        firm.session.expire_all()
        with _counted(firm) as statements:
            answer = list_bills_of_entry(
                scope=scope,
                page=1,
                page_size=50,
                search=None,
                status_filter=None,
                vendor_id=None,
                from_date=None,
                to_date=None,
                db=firm.session,
            )
        return len(statements), len(answer.data)

    for number in range(2):
        _create(firm, bills=[bill], boe_number=f"10{number}")
    small, rows = page_cost()
    assert rows == 2
    for number in range(2, 8):
        _create(firm, bills=[bill], boe_number=f"10{number}")
    large, rows = page_cost()
    assert rows == 8
    assert large <= small + 1
    filtered = list_bills_of_entry(
        scope=scope,
        page=1,
        page_size=50,
        search="105",
        status_filter="draft",
        vendor_id=firm.vendor.id,
        from_date=ON,
        to_date=ON,
        db=firm.session,
    )
    assert [row.boe_number for row in filtered.data] == ["105"]
