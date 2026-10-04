"""The GST purchase register and the HSN summary of purchases (§86 #17)."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.branches.models import Branch
from app.core.database.base import Base
from app.firms.models import Firm
from app.products.models import Product
from app.purchase_invoice.models import (
    PurchaseInvoice,
    PurchaseInvoiceLine,
    PurchaseInvoiceLineTax,
)
from app.purchase_invoice.services.gst_purchase_register import (
    GstPurchaseRegisterService,
)
from app.uom.models import Uom
from app.vendors.models import Vendor

DAY = date(2026, 8, 10)


def _session() -> Session:
    """Return a session on a fresh in-memory store holding every table."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


class _World:
    """A firm, a branch, two suppliers, three products and two units."""

    def __init__(self, session: Session) -> None:
        """Seed the masters every bill here refers to."""
        self.session = session
        self.firm = Firm(
            name="GST Firm",
            code="GST-FIRM",
            country="IN",
            currency_code="INR",
            financial_year_start=date(2026, 4, 1),
        )
        session.add(self.firm)
        session.flush()
        self.branch = Branch(
            firm_id=self.firm.id,
            code="BR-001",
            name="Branch",
            display_name="Branch",
            currency_code="INR",
            working_hours={"start": "09:00", "end": "18:00"},
            status="ACTIVE",
        )
        self.local = Vendor(
            firm_id=self.firm.id,
            code="VEN-L",
            name="Local Supplier",
            display_name="Local Supplier",
            status="ACTIVE",
            gstin="29ABCDE1234F1Z5",
        )
        self.interstate = Vendor(
            firm_id=self.firm.id,
            code="VEN-I",
            name="Interstate Supplier",
            display_name="Interstate Supplier",
            status="ACTIVE",
            gstin="27ABCDE1234F1Z5",
        )
        self.soap = Product(
            firm_id=self.firm.id,
            code="SOAP",
            name="Soap",
            product_type="STOCK_ITEM",
            status="ACTIVE",
            hsn_sac="3401",
        )
        self.car = Product(
            firm_id=self.firm.id,
            code="CAR",
            name="Motor car",
            product_type="STOCK_ITEM",
            status="ACTIVE",
            hsn_sac="8703",
        )
        self.bare = Product(
            firm_id=self.firm.id,
            code="BARE",
            name="No HSN",
            product_type="STOCK_ITEM",
            status="ACTIVE",
        )
        self.pcs = Uom(code="PCS", name="Pieces")
        self.box = Uom(code="BOX", name="Box")
        session.add_all(
            [
                self.branch,
                self.local,
                self.interstate,
                self.soap,
                self.car,
                self.bare,
                self.pcs,
                self.box,
            ]
        )
        session.commit()
        self._numbers = 0

    def bill(
        self,
        vendor: Vendor,
        lines: list[dict[str, Any]],
        *,
        status: str = "APPROVED",
        day: date = DAY,
        reverse_charge_tax: Decimal = Decimal("0"),
    ) -> PurchaseInvoice:
        """Write one bill whose lines carry the tax components given.

        Each line is ``product``, ``uom``, ``quantity``, ``taxable``,
        ``taxes`` (component code to amount) and optionally ``eligibility``.
        """
        self._numbers += 1
        taxable = sum((Decimal(line["taxable"]) for line in lines), Decimal("0"))
        tax = sum(
            (Decimal(a) for line in lines for a in line["taxes"].values()),
            Decimal("0"),
        )
        bill = PurchaseInvoice(
            firm_id=self.firm.id,
            vendor_id=vendor.id,
            branch_id=self.branch.id,
            invoice_number=f"PI-{self._numbers:03d}",
            invoice_date=day,
            supplier_invoice_number=f"SUP-{self._numbers:03d}",
            supplier_invoice_date=day,
            status=status,
            subtotal=taxable,
            tax_total=tax,
            grand_total=taxable + tax,
            reverse_charge_tax_total=reverse_charge_tax,
        )
        self.session.add(bill)
        self.session.flush()
        for number, spec in enumerate(lines, start=1):
            line_tax = sum((Decimal(a) for a in spec["taxes"].values()), Decimal("0"))
            line = PurchaseInvoiceLine(
                purchase_invoice_id=bill.id,
                firm_id=self.firm.id,
                line_number=number,
                source_document_type="GOODS_RECEIPT",
                source_document_id=uuid4(),
                source_document_number="GRN-1",
                source_document_line_id=uuid4(),
                source_document_line_number=number,
                product_id=spec["product"].id,
                received_quantity=Decimal(spec["quantity"]),
                current_invoice_quantity=Decimal(spec["quantity"]),
                gross_amount=Decimal(spec["taxable"]),
                tax_amount=line_tax,
                net_amount=Decimal(spec["taxable"]) + line_tax,
                invoice_uom_id=spec["uom"].id,
                itc_eligibility=spec.get("eligibility", "ELIGIBLE"),
            )
            self.session.add(line)
            self.session.flush()
            for sequence, (code, amount) in enumerate(spec["taxes"].items(), 1):
                self.session.add(
                    PurchaseInvoiceLineTax(
                        purchase_invoice_line_id=line.id,
                        firm_id=self.firm.id,
                        sequence=sequence,
                        component_code=code,
                        component_label=code,
                        amount=Decimal(amount),
                    )
                )
        self.session.commit()
        return bill

    def within_state(
        self, product: Product, uom: Uom, **extra: object
    ) -> dict[str, Any]:
        """Return a line of 1,000 taxed at 18% as CGST and SGST."""
        return {
            "product": product,
            "uom": uom,
            "quantity": "10",
            "taxable": "1000",
            "taxes": {"CGST": "90", "SGST": "90"},
            **extra,
        }


def _by_number(rows: list[Any]) -> dict[str, Any]:
    """Index register rows by the firm's bill number."""
    return {row.invoice_number: row for row in rows}


def test_a_bill_is_read_by_tax_head() -> None:
    """Within the state is CGST + SGST; across it, IGST; taxable is net of tax."""
    session = _session()
    world = _World(session)
    local = world.bill(world.local, [world.within_state(world.soap, world.pcs)])
    interstate = world.bill(
        world.interstate,
        [
            {
                "product": world.soap,
                "uom": world.pcs,
                "quantity": "5",
                "taxable": "500",
                "taxes": {"IGST": "90"},
            }
        ],
    )

    rows = _by_number(GstPurchaseRegisterService(session).register(world.firm.id))

    first = rows[local.invoice_number]
    assert first.vendor_name == "Local Supplier"
    assert first.vendor_gstin == "29ABCDE1234F1Z5"
    assert first.taxable_value == Decimal("1000.00")
    assert (first.cgst, first.sgst, first.igst) == (
        Decimal("90.00"),
        Decimal("90.00"),
        Decimal("0.00"),
    )
    assert first.total_tax == Decimal("180.00")
    assert first.invoice_total == Decimal("1180.00")
    assert first.itc_not_claimable == Decimal("0.00")
    second = rows[interstate.invoice_number]
    assert (second.igst, second.cgst, second.sgst) == (
        Decimal("90.00"),
        Decimal("0.00"),
        Decimal("0.00"),
    )
    assert second.taxable_value == Decimal("500.00")


def test_a_blocked_credit_line_counts_as_not_claimable() -> None:
    """Only the blocked line's tax is not claimable; the heads keep all of it."""
    session = _session()
    world = _World(session)
    bill = world.bill(
        world.local,
        [
            world.within_state(world.soap, world.pcs),
            world.within_state(world.car, world.pcs, eligibility="BLOCKED"),
        ],
        reverse_charge_tax=Decimal("25"),
    )

    (row,) = GstPurchaseRegisterService(session).register(world.firm.id)

    assert row.invoice_number == bill.invoice_number
    assert row.total_tax == Decimal("360.00")
    assert row.itc_not_claimable == Decimal("180.00")
    assert row.reverse_charge_tax == Decimal("25.00")


def test_a_draft_and_a_cancelled_bill_are_left_out() -> None:
    """Only approved and closed bills have claimed anything."""
    session = _session()
    world = _World(session)
    approved = world.bill(world.local, [world.within_state(world.soap, world.pcs)])
    closed = world.bill(
        world.local, [world.within_state(world.soap, world.pcs)], status="CLOSED"
    )
    for status in ("DRAFT", "CANCELLED"):
        world.bill(
            world.local, [world.within_state(world.soap, world.pcs)], status=status
        )
    service = GstPurchaseRegisterService(session)

    numbers = {row.invoice_number for row in service.register(world.firm.id)}
    (hsn,) = service.hsn_summary(world.firm.id)

    assert numbers == {approved.invoice_number, closed.invoice_number}
    assert hsn.bills == 2
    assert hsn.quantity == Decimal("20")


def test_the_hsn_summary_folds_by_code_and_unit() -> None:
    """Two units of one HSN are two rows; a product with no HSN shows the gap."""
    session = _session()
    world = _World(session)
    world.bill(
        world.local,
        [
            world.within_state(world.soap, world.pcs),
            world.within_state(world.soap, world.box),
            world.within_state(world.bare, world.pcs),
        ],
    )
    world.bill(world.local, [world.within_state(world.soap, world.pcs)])

    rows = GstPurchaseRegisterService(session).hsn_summary(world.firm.id)

    assert [(row.hsn_code, row.unit) for row in rows] == [
        ("", "PCS"),
        ("3401", "BOX"),
        ("3401", "PCS"),
    ]
    soap_pieces = rows[2]
    assert soap_pieces.quantity == Decimal("20")
    assert soap_pieces.taxable_value == Decimal("2000.00")
    assert (soap_pieces.cgst, soap_pieces.sgst) == (
        Decimal("180.00"),
        Decimal("180.00"),
    )
    assert soap_pieces.total_tax == Decimal("360.00")
    assert soap_pieces.bills == 2
    assert rows[0].description == "No HSN"
    assert rows[1].bills == 1


def test_the_routes_take_a_window_and_a_page() -> None:
    """Both reports read the bill's own date and count matches, not the page."""
    from app.purchase_invoice.api.router import (
        gst_purchase_register,
        hsn_purchase_summary,
        router,
    )
    from tests.unit.report_windows import assert_page_size_is_bounded, report_scope

    session = _session()
    world = _World(session)
    days = [date(2026, 8, 2), date(2026, 8, 3), date(2026, 8, 4)]
    for day in days:
        world.bill(world.local, [world.within_state(world.soap, world.pcs)], day=day)
    scope = report_scope(world.firm.id)

    page = gst_purchase_register(
        scope=scope,
        db=session,
        from_date=days[1],
        to_date=days[2],
        page=1,
        page_size=1,
    )
    hsn = hsn_purchase_summary(
        scope=scope,
        db=session,
        from_date=days[1],
        to_date=days[2],
        page=1,
        page_size=50,
    )

    assert page.pagination.total_records == 2
    assert [row.invoice_date for row in page.data] == [days[2]]
    assert [row.bills for row in hsn.data] == [2]
    for path in ("gst-register", "hsn-summary"):
        assert_page_size_is_bounded(router, f"/api/v1/purchase-invoices/reports/{path}")


@contextmanager
def _counting(session: Session) -> Iterator[list[str]]:
    """Collect every statement the session's engine executes."""
    seen: list[str] = []

    def record(*args: Any) -> None:  # noqa: ANN401
        """Keep the statement text."""
        seen.append(args[2])

    engine = session.get_bind()
    event.listen(engine, "before_cursor_execute", record)
    try:
        yield seen
    finally:
        event.remove(engine, "before_cursor_execute", record)


def _statements(bills: int) -> tuple[int, int]:
    """Return the statements each report reads over ``bills`` bills."""
    session = _session()
    world = _World(session)
    for index in range(bills):
        vendor = world.local if index % 2 else world.interstate
        world.bill(vendor, [world.within_state(world.soap, world.pcs)])
    session.expire_all()
    service = GstPurchaseRegisterService(session)
    firm_id: UUID = world.firm.id
    with _counting(session) as register:
        service.register(firm_id)
    with _counting(session) as hsn:
        service.hsn_summary(firm_id)
    return len(register), len(hsn)


def test_the_statements_do_not_grow_with_the_bills() -> None:
    """Two bills and twelve cost the same number of statements."""
    assert _statements(2) == _statements(12)
