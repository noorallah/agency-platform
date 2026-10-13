"""A supplier company with branches (backlog 127, row M9).

A supplier company is one main office with a supplier per branch under it.
Each branch keeps its own GST number. An order on the main office is
received from a branch and billed by it, and a payment to the main office
clears a branch's bills, while each office's account still closes on what
that office is owed.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.party_merge import PartyMergeService, PartyMergeWrite
from app.common.scope import ResolvedFirmScope
from app.core.exceptions import ConflictError, ValidationError
from app.finance.services.control_accounts import ControlAccountPurpose
from app.goods_receipt.models import GoodsReceipt, GoodsReceiptLine
from app.goods_receipt.schemas import GoodsReceiptUpdate
from app.goods_receipt.services import GoodsReceiptService
from app.purchase.models import PurchaseOrder
from app.purchase_invoice.models import PurchaseInvoice
from app.purchase_invoice.schemas import (
    PurchaseInvoiceCreate,
    PurchaseInvoiceLineWrite,
    PurchaseInvoiceSourceType,
)
from app.purchase_invoice.services import PurchaseInvoiceService
from app.settlements.api.router import _to_responses, vendor_outstanding_invoices
from app.settlements.models import Settlement
from app.settlements.schemas import SettlementCreate
from app.settlements.services import PaymentService
from app.vendors.api.router import _responses, vendor_family
from app.vendors.models import Vendor
from app.vendors.schemas import VendorCreate, VendorUpdate
from app.vendors.services import VendorService
from app.vendors.services.statement_service import SupplierStatementService
from tests.unit.test_goods_receipt import (
    _control_balance,
    _Fixture,
    _principal,
    _session_factory,
)

pytestmark = pytest.mark.typed_document_numbers

YEAR = (date(2026, 4, 1), date(2027, 3, 31))


def _fixture(code: str = "M9") -> _Fixture:
    return _Fixture(_session_factory()(), code)


def _supplier(
    fixture: _Fixture, code: str, parent: UUID | None = None, **fields: object
) -> Vendor:
    return VendorService(fixture.session).create(
        VendorCreate.model_validate(
            {"code": code, "name": f"Supplier {code}", "parent_vendor_id": parent}
            | fields
        ),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )


def _edit(fixture: _Fixture, vendor: Vendor, **fields: object) -> Vendor:
    return VendorService(fixture.session).update(
        vendor.id,
        VendorUpdate.model_validate(
            {"code": vendor.code, "name": vendor.name} | fields
        ),
        firm_scope=fixture.firm.id,
        actor_id=fixture.actor_id,
    )


def _receive(fixture: _Fixture, quantity: str = "10", **over: object) -> GoodsReceipt:
    service = GoodsReceiptService(fixture.session)
    receipt = service.create_receipt(
        fixture.receipt_payload(quantity, **over),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    return service.complete_receipt(
        receipt.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )


def _bill_payload(
    fixture: _Fixture,
    receipt: GoodsReceipt,
    *,
    vendor_id: UUID | None,
    quantity: str = "10",
) -> PurchaseInvoiceCreate:
    line = fixture.session.scalars(
        select(GoodsReceiptLine).where(GoodsReceiptLine.goods_receipt_id == receipt.id)
    ).first()
    assert line is not None
    return PurchaseInvoiceCreate(
        vendor_id=vendor_id,
        supplier_invoice_number=f"SUP-{receipt.grn_number}",
        supplier_invoice_date=date(2026, 8, 6),
        invoice_date=date(2026, 8, 6),
        source_documents=[
            {
                "source_document_type": PurchaseInvoiceSourceType.GOODS_RECEIPT,
                "source_document_id": receipt.id,
            }
        ],
        lines=[
            PurchaseInvoiceLineWrite(
                source_document_type=PurchaseInvoiceSourceType.GOODS_RECEIPT,
                source_document_id=receipt.id,
                source_document_line_id=line.id,
                line_number=1,
                current_invoice_quantity=Decimal(quantity),
                unit_price=Decimal("100"),
            )
        ],
    )


def _bill(
    fixture: _Fixture,
    receipt: GoodsReceipt,
    *,
    vendor_id: UUID | None = None,
    quantity: str = "10",
) -> PurchaseInvoice:
    service = PurchaseInvoiceService(fixture.session)
    invoice = service.create_invoice(
        _bill_payload(fixture, receipt, vendor_id=vendor_id, quantity=quantity),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    return service.approve_invoice(
        invoice.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )


def _pay(
    fixture: _Fixture,
    vendor: Vendor,
    amount: str,
    *bills: tuple[PurchaseInvoice, str],
    when: str = "2026-08-07",
) -> Settlement:
    return PaymentService(fixture.session).create(
        SettlementCreate.model_validate(
            {
                "party_id": vendor.id,
                "settlement_date": when,
                "amount": amount,
                "method": "BANK",
                "allocations": [
                    {"invoice_id": bill.id, "amount": part} for bill, part in bills
                ],
            }
        ),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )


def _closing(fixture: _Fixture, vendor: Vendor) -> Decimal:
    return (
        SupplierStatementService(fixture.session)
        .statement(
            vendor.id, firm_scope=fixture.firm.id, from_date=YEAR[0], to_date=YEAR[1]
        )
        .closing_balance
    )


def _lines(fixture: _Fixture, vendor: Vendor) -> list[tuple[str, Decimal, Decimal]]:
    statement = SupplierStatementService(fixture.session).statement(
        vendor.id, firm_scope=fixture.firm.id, from_date=YEAR[0], to_date=YEAR[1]
    )
    return [(row.transaction_type, row.debit, row.credit) for row in statement.lines]


def _payables(fixture: _Fixture) -> Decimal:
    """Return what the payables account holds: credits less debits."""
    return -_control_balance(
        fixture.session,
        fixture.firm.id,
        ControlAccountPurpose.ACCOUNTS_PAYABLE.value,
    ).quantize(Decimal("0.01"))


def _owed(session: Session, firm_id: UUID, vendor: Vendor) -> Decimal:
    return sum(
        (
            row.outstanding_amount
            for row in PaymentService(session).outstanding_invoices(
                firm_id=firm_id, party_id=vendor.id
            )
        ),
        Decimal("0.00"),
    )


def _billed_by_a_branch(fixture: _Fixture) -> tuple[Vendor, PurchaseInvoice]:
    """Order on the main office; a branch delivers the goods and bills them."""
    branch = _supplier(fixture, "BR-KKP", fixture.vendor.id)
    receipt = _receive(fixture, vendor_id=branch.id)
    return branch, _bill(fixture, receipt, vendor_id=branch.id)


# ---- the supplier master -----------------------------------------------------


def test_a_main_office_with_branches_each_with_its_own_gst_number() -> None:
    fixture = _fixture()
    main = _supplier(
        fixture, "HUL", gstin="29ABCDE1234F1Z5", pan="ABCDE1234F", gst_registration=True
    )
    kkp = _supplier(
        fixture,
        "HUL-KKP",
        main.id,
        gstin="36ABCDE1234F1Z0",
        pan="ABCDE1234F",
        gst_registration=True,
    )
    plain = _supplier(fixture, "HUL-MYP", main.id)

    assert kkp.parent_vendor_id == main.id
    # Nothing is copied: a branch is registered in its own state.
    assert kkp.gstin == "36ABCDE1234F1Z0"
    assert plain.gstin is None
    # The key that was already there still holds a number to one supplier.
    with pytest.raises(ConflictError):
        _supplier(
            fixture,
            "HUL-DUP",
            main.id,
            gstin="36ABCDE1234F1Z0",
            pan="ABCDE1234F",
            gst_registration=True,
        )


def test_branches_sit_one_level_under_a_main_office() -> None:
    fixture = _fixture()
    main = _supplier(fixture, "MAIN")
    branch = _supplier(fixture, "BRANCH", main.id)
    other = _supplier(fixture, "OTHER")

    with pytest.raises(ValidationError, match="itself a branch of MAIN"):
        _supplier(fixture, "DEEP", branch.id)
    with pytest.raises(ConflictError, match="main office of 1 branch"):
        _edit(fixture, main, parent_vendor_id=other.id)
    with pytest.raises(ValidationError, match="its own main office"):
        _edit(fixture, other, parent_vendor_id=other.id)
    with pytest.raises(ValidationError, match="not one of this firm"):
        _edit(fixture, other, parent_vendor_id=fixture.firm.id)


def test_an_edit_that_does_not_name_the_main_office_leaves_it() -> None:
    fixture = _fixture()
    main = _supplier(fixture, "MAIN")
    branch = _supplier(fixture, "BRANCH", main.id)

    branch = _edit(fixture, branch, phone="+919000000001")
    assert branch.parent_vendor_id == main.id

    branch = _edit(fixture, branch, parent_vendor_id=None)
    assert branch.parent_vendor_id is None


def test_a_main_office_with_branches_is_not_deleted_or_merged_away() -> None:
    fixture = _fixture()
    main = _supplier(fixture, "MAIN")
    branch = _supplier(fixture, "BRANCH", main.id)
    other = _supplier(fixture, "OTHER")
    service = VendorService(fixture.session)

    with pytest.raises(ConflictError, match="main office of 1 branch"):
        service.delete(main.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id)
    with pytest.raises(ValidationError, match="main office of 1 branch"):
        PartyMergeService(fixture.session).merge(
            "VENDOR",
            other.id,
            PartyMergeWrite(duplicate_id=main.id, reason="the same company"),
            firm_id=fixture.firm.id,
            actor_id=fixture.actor_id,
        )

    # A branch goes, and comes back only while its main office is there.
    service.delete(branch.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id)
    service.delete(main.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id)
    with pytest.raises(ConflictError, match="Restore the main office first"):
        service.restore(
            branch.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
        )


def test_a_list_row_names_its_main_office_and_counts_its_branches() -> None:
    fixture = _fixture()
    main = _supplier(fixture, "MAIN")
    branch = _supplier(fixture, "BRANCH", main.id)

    facts = VendorService(fixture.session).family_facts([main, branch])

    assert facts[main.id].branch_count == 1
    assert facts[main.id].parent_code is None
    assert (facts[branch.id].parent_code, facts[branch.id].parent_name) == (
        "MAIN",
        "Supplier MAIN",
    )
    assert facts[branch.id].branch_count == 0


# ---- an order on the main office, received from a branch and billed by it ----


def test_an_order_on_the_main_office_is_received_from_a_branch_and_billed_by_it() -> (
    None
):
    fixture = _fixture()
    branch, bill = _billed_by_a_branch(fixture)

    receipt = fixture.session.scalars(select(GoodsReceipt)).one()
    order = fixture.session.get(PurchaseOrder, fixture.order.id)
    assert order is not None
    # The order stays the main office's; the goods and the bill are the
    # branch's, and the order is received all the same.
    assert order.vendor_id == fixture.vendor.id
    assert receipt.vendor_id == branch.id
    assert bill.vendor_id == branch.id
    assert order.status == "RECEIVED"
    assert _owed(fixture.session, fixture.firm.id, branch) == Decimal("1000.00")
    assert _owed(fixture.session, fixture.firm.id, fixture.vendor) == Decimal("0.00")


def test_a_receipt_that_names_no_office_is_the_orders_supplier() -> None:
    fixture = _fixture()
    _supplier(fixture, "BR-KKP", fixture.vendor.id)

    receipt = _receive(fixture)

    assert receipt.vendor_id == fixture.vendor.id


def test_an_order_on_a_branch_is_received_from_the_main_office_or_a_sibling() -> None:
    fixture = _fixture()
    main = _supplier(fixture, "MAIN")
    sibling = _supplier(fixture, "SIBLING", main.id)
    # The fixture's order is on its vendor: make that vendor a branch.
    _edit(fixture, fixture.vendor, parent_vendor_id=main.id)

    first = _receive(fixture, "4", vendor_id=main.id)
    second = _receive(fixture, "6", vendor_id=sibling.id)

    assert (first.vendor_id, second.vendor_id) == (main.id, sibling.id)


def test_a_receipt_from_a_supplier_outside_the_company_is_refused() -> None:
    fixture = _fixture()
    _supplier(fixture, "BR-KKP", fixture.vendor.id)
    stranger = _supplier(fixture, "STRANGER")

    with pytest.raises(ValidationError, match="its main office or one of its"):
        _receive(fixture, vendor_id=stranger.id)


def test_an_edit_moves_a_draft_receipt_to_another_office_and_no_further() -> None:
    fixture = _fixture()
    branch = _supplier(fixture, "BR-KKP", fixture.vendor.id)
    stranger = _supplier(fixture, "STRANGER")
    service = GoodsReceiptService(fixture.session)
    receipt = service.create_receipt(
        fixture.receipt_payload("10"),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )

    def edit(**over: object) -> GoodsReceipt:
        return service.update_receipt(
            receipt.id,
            GoodsReceiptUpdate.model_validate(
                fixture.receipt_payload("10").model_dump(exclude_unset=True) | over
            ),
            firm_scope=fixture.firm.id,
            actor_id=fixture.actor_id,
        )

    assert edit(vendor_id=branch.id).vendor_id == branch.id
    # An edit that says nothing about the office keeps it.
    assert edit(remarks="Two cartons short.").vendor_id == branch.id
    with pytest.raises(ValidationError, match="its main office or one of its"):
        edit(vendor_id=stranger.id)


def test_a_bill_from_another_office_of_the_receipts_company_is_taken() -> None:
    fixture = _fixture()
    branch = _supplier(fixture, "BR-KKP", fixture.vendor.id)
    # Received in the main office's name, billed by the branch.
    receipt = _receive(fixture)

    bill = _bill(fixture, receipt, vendor_id=branch.id)

    assert bill.vendor_id == branch.id


def test_a_bill_that_names_no_supplier_is_the_receipts() -> None:
    fixture = _fixture()
    branch = _supplier(fixture, "BR-KKP", fixture.vendor.id)
    receipt = _receive(fixture, vendor_id=branch.id)

    bill = _bill(fixture, receipt)

    assert bill.vendor_id == branch.id


def test_a_bill_from_outside_the_company_is_refused_on_create_and_on_edit() -> None:
    fixture = _fixture()
    branch = _supplier(fixture, "BR-KKP", fixture.vendor.id)
    stranger = _supplier(fixture, "STRANGER")
    receipt = _receive(fixture, vendor_id=branch.id)
    service = PurchaseInvoiceService(fixture.session)

    with pytest.raises(ValidationError, match="must match all source documents"):
        service.create_invoice(
            _bill_payload(fixture, receipt, vendor_id=stranger.id),
            firm_id=fixture.firm.id,
            actor_id=fixture.actor_id,
        )

    draft = service.create_invoice(
        _bill_payload(fixture, receipt, vendor_id=branch.id),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    # The edit used to take any supplier at all.
    with pytest.raises(ValidationError, match="must match all source documents"):
        service.update_invoice(
            draft.id,
            _bill_payload(fixture, receipt, vendor_id=stranger.id),
            firm_scope=fixture.firm.id,
            actor_id=fixture.actor_id,
        )
    moved = service.update_invoice(
        draft.id,
        _bill_payload(fixture, receipt, vendor_id=fixture.vendor.id),
        firm_scope=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    assert moved.vendor_id == fixture.vendor.id


# ---- payment to the main office or to a branch -------------------------------


def test_a_payment_to_the_main_office_clears_a_branchs_bill() -> None:
    fixture = _fixture()
    branch, bill = _billed_by_a_branch(fixture)
    main = fixture.vendor

    payment = _pay(fixture, main, "1300.00", (bill, "1000.00"))

    # One payment, the main office's; the branch's bill is paid.
    assert payment.vendor_id == main.id
    assert _owed(fixture.session, fixture.firm.id, branch) == Decimal("0.00")
    # Each office's account closes on what that office is owed: nothing to
    # the branch, and 300 paid ahead to the main office.
    assert _lines(fixture, branch) == [
        ("BILL", Decimal("0.00"), Decimal("1000.00")),
        ("PAYMENT_TRANSFER", Decimal("1000.00"), Decimal("0.00")),
    ]
    assert _lines(fixture, main) == [
        ("PAYMENT", Decimal("1300.00"), Decimal("0.00")),
        ("PAYMENT_TRANSFER", Decimal("0.00"), Decimal("1000.00")),
    ]
    assert _closing(fixture, branch) == Decimal("0.00")
    assert _closing(fixture, main) == Decimal("-300.00")
    # The two lines net to nothing, so the accounts still sum to payables.
    assert _closing(fixture, branch) + _closing(fixture, main) == _payables(fixture)

    answer = _to_responses(PaymentService(fixture.session), [payment])[0]
    assert [
        (item.party_id, item.party_code, item.party_name) for item in answer.allocations
    ] == [(branch.id, "BR-KKP", "Supplier BR-KKP")]


def test_the_list_for_a_main_office_names_whose_each_bill_is() -> None:
    fixture = _fixture()
    branch, bill = _billed_by_a_branch(fixture)
    scope = ResolvedFirmScope(
        principal=_principal(fixture.actor_id, {"PAYMENT_VIEW", "VENDOR_VIEW"}),
        firm_id=fixture.firm.id,
    )

    alone = vendor_outstanding_invoices(
        fixture.vendor.id, scope, with_branches=False, db=fixture.session
    ).data
    together = vendor_outstanding_invoices(
        fixture.vendor.id, scope, with_branches=True, db=fixture.session
    ).data

    assert alone == []
    assert together is not None
    assert [(row.invoice_id, row.party_code) for row in together] == [
        (bill.id, "BR-KKP")
    ]

    family = vendor_family(fixture.vendor.id, scope, db=fixture.session).data
    assert family is not None
    assert family.parent_id == fixture.vendor.id
    assert [(item.code, item.is_parent, item.balance) for item in family.members] == [
        (fixture.vendor.code, True, Decimal("0.00")),
        ("BR-KKP", False, Decimal("1000.00")),
    ]
    assert family.total_balance == Decimal("1000.00")
    # Asked of the branch, the same company.
    again = vendor_family(branch.id, scope, db=fixture.session).data
    assert again is not None and again.parent_id == fixture.vendor.id

    rows = _responses([fixture.vendor, branch], fixture.session, scope)
    assert [(row.branch_count, row.parent_code) for row in rows] == [
        (1, None),
        (0, fixture.vendor.code),
    ]


def test_a_branch_is_paid_directly_and_pays_for_nobody_else() -> None:
    fixture = _fixture()
    branch, bill = _billed_by_a_branch(fixture)
    sibling = _supplier(fixture, "BR-MYP", fixture.vendor.id)

    with pytest.raises(ValidationError, match="does not belong to this party"):
        _pay(fixture, sibling, "1000.00", (bill, "1000.00"))

    _pay(fixture, branch, "400.00", (bill, "400.00"))

    assert _owed(fixture.session, fixture.firm.id, branch) == Decimal("600.00")
    assert _lines(fixture, branch) == [
        ("BILL", Decimal("0.00"), Decimal("1000.00")),
        ("PAYMENT", Decimal("400.00"), Decimal("0.00")),
    ]
    assert _lines(fixture, fixture.vendor) == []


def test_money_paid_ahead_to_the_main_office_is_set_against_a_branchs_bill() -> None:
    fixture = _fixture()
    branch, bill = _billed_by_a_branch(fixture)
    main = fixture.vendor
    advance = _pay(fixture, main, "700.00", when="2026-08-01")
    assert _closing(fixture, main) == Decimal("-700.00")

    PaymentService(fixture.session).allocate(
        advance.id,
        invoice_id=bill.id,
        amount=Decimal("700.00"),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )

    assert _owed(fixture.session, fixture.firm.id, branch) == Decimal("300.00")
    assert _closing(fixture, main) == Decimal("0.00")
    assert _closing(fixture, branch) == Decimal("300.00")
    assert _closing(fixture, branch) + _closing(fixture, main) == _payables(fixture)


def test_reversing_the_main_offices_payment_puts_the_branchs_bill_back() -> None:
    fixture = _fixture()
    branch, bill = _billed_by_a_branch(fixture)
    main = fixture.vendor
    payment = _pay(fixture, main, "1300.00", (bill, "1000.00"))

    PaymentService(fixture.session).reverse(
        payment.id,
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
        reason="Paid from the wrong bank.",
        on=date(2026, 8, 9),
    )

    assert _owed(fixture.session, fixture.firm.id, branch) == Decimal("1000.00")
    assert _lines(fixture, branch) == [
        ("BILL", Decimal("0.00"), Decimal("1000.00")),
        ("PAYMENT_TRANSFER", Decimal("1000.00"), Decimal("0.00")),
        ("PAYMENT_TRANSFER_REVERSAL", Decimal("0.00"), Decimal("1000.00")),
    ]
    assert _closing(fixture, branch) == Decimal("1000.00")
    assert _closing(fixture, main) == Decimal("0.00")
    assert _closing(fixture, branch) + _closing(fixture, main) == _payables(fixture)
    balances = SupplierStatementService(fixture.session).balances(
        firm_scope=fixture.firm.id, as_of=YEAR[1]
    )
    assert balances == {branch.id: Decimal("1000.00")}
