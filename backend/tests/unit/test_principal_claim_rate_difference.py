"""A principal's price cut is claimed on the stock in hand (rate difference).

A stockist holds ACME's goods bought at 60. ACME cuts its rate to 50 from
10 September, and owes the difference on what stood on the shelf when the
day before closed -- the claim Marg and Busy users write up from a stock
statement and a debit note, and which no claim kind here could carry.

The firm here:

* **TAB-1**, ACME's, bought at 60 and revised to 50 from the 10th. Ten came in
  on 1 August and three were sold on 5 September: **7** at the close of the
  9th. Five more received on the 10th and two sold on the 12th change nothing.
* **SYR-1**, ACME's and kept by batch: 10 in batch EARLY, 4 in batch LATE.
* **OWN-1**, nobody's, with the same revision: no part of ACME's claim.
* **TAB-2**, ACME's, revised *up* to 65: nothing to claim.

The claim is (60 - 50) x 7 = 70: Dr claims receivable, Cr purchase price
variance. The stock is not revalued. Every case runs on a request-shaped
session.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.batch_serial.models import BatchRecord
from app.common.firm_metadata import firm_today
from app.core.exceptions import ValidationError
from app.finance.services.control_accounts import ControlAccountPurpose
from app.inventory.models import ProductValuation
from app.inventory.services.inventory_service import InventoryService
from app.principal_claims.services import (
    PrincipalClaimReceiptWrite,
    PrincipalClaimService,
    PrincipalClaimWrite,
    RateDifferenceLineWrite,
)
from app.products.models import Product
from app.products.models.brand import Brand, Principal
from app.products.models.price_revision import ProductPriceRevision
from app.sales_invoice.schemas import SalesInvoiceCreate, SalesInvoiceLineWrite
from tests.unit.test_principal_claim_free_goods import _Agency

D = Decimal
CUT = date(2026, 9, 10)
VARIANCE = ControlAccountPurpose.PURCHASE_PRICE_VARIANCE
RECEIVABLE = ControlAccountPurpose.PRINCIPAL_CLAIM_RECEIVABLE


class _Stockist(_Agency):
    """ACME's stockist on the day ACME cuts its rates."""

    def __init__(self) -> None:
        """Stock TAB-1 as the module docstring says, and record the cut."""
        super().__init__()
        self.stock = InventoryService(self.session)
        self.tab = self.item("TAB-1", bought="60", revised="50")
        self.receive(self.tab, "10", date(2026, 8, 1))
        self.sell(self.tab, "3", date(2026, 9, 5))
        self.receive(self.tab, "5", CUT)
        self.sell(self.tab, "2", date(2026, 9, 12))

    def item(
        self,
        code: str,
        *,
        bought: str,
        revised: str | None,
        acme: bool = True,
        batched: bool = False,
    ) -> Product:
        """Add a product bought at one rate and revised to another from the cut."""
        row = Product(
            firm_id=self.firm_id,
            code=code,
            name=f"Product {code}",
            product_type="STOCK_ITEM",
            status="ACTIVE",
            brand_id=self.brand_id if acme else None,
            purchase_price=D(bought),
            track_batch=batched,
        )
        self.session.add(row)
        self.session.flush()
        if revised is not None:
            self.session.add(
                ProductPriceRevision(
                    firm_id=self.firm_id,
                    product_id=row.id,
                    effective_from=CUT,
                    purchase_price=D(revised),
                )
            )
        self.session.commit()
        return row

    def receive(
        self, product: Product, quantity: str, on: date, batch: str | None = None
    ) -> BatchRecord | None:
        """Receive stock at 60, into a named batch where one is given."""
        held = None
        if batch is not None:
            held = BatchRecord(
                firm_id=self.firm_id,
                product_id=product.id,
                batch_number=batch,
                status="AVAILABLE",
            )
            self.session.add(held)
            self.session.flush()
        self.stock.record_goods_receipt(
            firm_scope=self.firm_id,
            actor_id=self.actor,
            branch_id=self.setup.branch.id,
            warehouse_id=self.setup.warehouse.id,
            storage_node_id=None,
            product_id=product.id,
            reference_number=f"GRN-{product.code}-{batch or on.isoformat()}",
            transaction_date=on,
            total_quantity=D(quantity),
            unit_cost=D("60"),
            batch_id=None if held is None else held.id,
        )
        self.session.commit()
        return held

    def sell(self, product: Product, quantity: str, on: date) -> None:
        """Bill and ship some of a product on a day."""
        invoice = self.bills.create_invoice(
            SalesInvoiceCreate(
                customer_id=self.setup.customer.id,
                invoice_date=on,
                lines=[
                    SalesInvoiceLineWrite(
                        product_id=product.id,
                        line_number=1,
                        current_invoice_quantity=D(quantity),
                        unit_price=D("100"),
                    )
                ],
            ),
            firm_id=self.firm_id,
            actor_id=self.actor,
        )
        self.bills.approve_invoice(
            invoice.id, firm_scope=self.firm_id, actor_id=self.actor
        )

    def cut(
        self,
        lines: list[RateDifferenceLineWrite] | None = None,
        *,
        principal_id: UUID | None = None,
    ) -> PrincipalClaimWrite:
        """Describe the claim for the price cut of the 10th."""
        return PrincipalClaimWrite(
            principal_id=principal_id or self.principal.id,
            effective_date=CUT,
            claim_date=date(2026, 9, 15),
            kinds=["RATE_DIFFERENCE"],
            rate_lines=lines,
        )

    @property
    def claims(self) -> PrincipalClaimService:
        """Return the claim service on this firm's session."""
        return PrincipalClaimService(self.session)


def _line(
    product: Product,
    old: str | None = None,
    new: str | None = None,
    batch: BatchRecord | None = None,
) -> RateDifferenceLineWrite:
    """Name a product, a batch of it and the rates somebody typed."""
    return RateDifferenceLineWrite(
        product_id=product.id,
        batch_id=None if batch is None else batch.id,
        old_rate=None if old is None else D(old),
        new_rate=None if new is None else D(new),
    )


def test_the_stock_claimed_is_what_stood_at_the_close_of_the_day_before() -> None:
    """A sale before the cut reduces it; a receipt on and a sale after do not."""
    firm = _Stockist()

    preview = firm.claims.preview(firm.cut(), firm_id=firm.firm_id)

    assert [
        (
            line.kind,
            line.product_name,
            line.batch_number,
            line.quantity,
            line.old_rate,
            line.new_rate,
            line.amount,
            line.source_date,
        )
        for line in preview.lines
    ] == [
        (
            "RATE_DIFFERENCE",
            "Product TAB-1",
            None,
            D("7.0000"),
            D("60.0000"),
            D("50.0000"),
            D("70.00"),
            CUT,
        )
    ]
    assert (preview.rate_difference_amount, preview.total_amount) == (
        D("70.00"),
        D("70.00"),
    )
    assert (preview.period_from, preview.period_to) == (CUT, CUT)
    assert "price revision" in preview.lines[0].description


def test_a_sale_before_the_cut_moves_the_figure() -> None:
    """Two more sold on the 9th leave five to claim on."""
    firm = _Stockist()
    firm.sell(firm.tab, "2", CUT - timedelta(days=1))

    (line,) = firm.claims.preview(firm.cut(), firm_id=firm.firm_id).lines

    assert (line.quantity, line.amount) == (D("5.0000"), D("50.00"))


def test_the_rates_come_from_the_recorded_cut_and_can_be_corrected() -> None:
    """The circular is the authority: a typed rate replaces the recorded one."""
    firm = _Stockist()

    typed = firm.claims.preview(
        firm.cut([_line(firm.tab, old="62.50", new="50")]), firm_id=firm.firm_id
    )
    silent = firm.claims.preview(firm.cut([_line(firm.tab)]), firm_id=firm.firm_id)

    (line,) = typed.lines
    assert (line.quantity, line.old_rate, line.new_rate, line.amount) == (
        D("7.0000"),
        D("62.5000"),
        D("50.0000"),
        D("87.50"),
    )
    assert "typed" in line.description
    assert [(row.old_rate, row.new_rate) for row in silent.lines] == [
        (D("60.0000"), D("50.0000"))
    ]


def test_a_product_nobody_recorded_a_cut_for_is_added_with_its_rates_typed() -> None:
    """Added by product; with no rates and no record there is nothing to go on."""
    firm = _Stockist()
    plain = firm.item("TAB-3", bought="40", revised=None)
    firm.receive(plain, "6", date(2026, 8, 1))

    preview = firm.claims.preview(
        firm.cut([_line(firm.tab), _line(plain, old="40", new="38")]),
        firm_id=firm.firm_id,
    )

    assert [(line.product_name, line.amount) for line in preview.lines] == [
        ("Product TAB-1", D("70.00")),
        ("Product TAB-3", D("12.00")),
    ]
    with pytest.raises(ValidationError, match="TAB-3.*type the old and the new"):
        firm.claims.preview(firm.cut([_line(plain)]), firm_id=firm.firm_id)


def test_a_line_with_no_drop_claims_nothing() -> None:
    """A rise is left out of what is proposed, and refused where it is typed."""
    firm = _Stockist()
    dearer = firm.item("TAB-2", bought="60", revised="65")
    firm.receive(dearer, "10", date(2026, 8, 1))

    proposed = firm.claims.preview(firm.cut(), firm_id=firm.firm_id)

    assert [line.product_name for line in proposed.lines] == ["Product TAB-1"]
    for old, new in (("60", "60"), ("60", "65"), (None, None)):
        with pytest.raises(ValidationError, match="TAB-2.*not lower"):
            firm.claims.preview(
                firm.cut([_line(dearer, old=old, new=new)]), firm_id=firm.firm_id
            )


def test_a_product_with_nothing_on_the_shelf_claims_nothing() -> None:
    """No stock at the close of the day before: left out, or refused if named."""
    firm = _Stockist()
    late = firm.item("TAB-4", bought="60", revised="50")
    firm.receive(late, "9", CUT)

    proposed = firm.claims.preview(firm.cut(), firm_id=firm.firm_id)

    assert [line.product_name for line in proposed.lines] == ["Product TAB-1"]
    with pytest.raises(ValidationError, match="TAB-4.*no stock"):
        firm.claims.preview(firm.cut([_line(late)]), firm_id=firm.firm_id)


def test_another_principals_products_are_left_out() -> None:
    """A cut on a product that is not ACME's is no part of ACME's claim."""
    firm = _Stockist()
    own = firm.item("OWN-1", bought="60", revised="50", acme=False)
    firm.receive(own, "10", date(2026, 8, 1))
    rival = Principal(firm_id=firm.firm_id, code="ZED", name="Zed Ltd")
    firm.session.add(rival)
    firm.session.flush()
    brand = Brand(firm_id=firm.firm_id, name="Zed", principal_id=rival.id)
    firm.session.add(brand)
    firm.session.flush()
    theirs = firm.item("ZED-1", bought="60", revised="50", acme=False)
    theirs.brand_id = brand.id
    firm.session.commit()
    firm.receive(theirs, "4", date(2026, 8, 1))

    acme = firm.claims.preview(firm.cut(), firm_id=firm.firm_id)
    zed = firm.claims.preview(firm.cut(principal_id=rival.id), firm_id=firm.firm_id)

    assert [line.product_name for line in acme.lines] == ["Product TAB-1"]
    assert [(line.product_name, line.amount) for line in zed.lines] == [
        ("Product ZED-1", D("40.00"))
    ]
    with pytest.raises(ValidationError, match="ZED-1.*not one of Acme Ltd"):
        firm.claims.preview(firm.cut([_line(theirs)]), firm_id=firm.firm_id)


def test_a_batch_tracked_product_is_claimed_batch_by_batch() -> None:
    """Each batch with stock is a line; one batch can carry its own rates."""
    firm = _Stockist()
    syrup = firm.item("SYR-1", bought="60", revised="50", batched=True)
    early = firm.receive(syrup, "10", date(2026, 8, 1), batch="EARLY")
    late = firm.receive(syrup, "4", date(2026, 8, 2), batch="LATE")
    firm.receive(syrup, "8", CUT, batch="AFTER")
    assert early is not None and late is not None

    proposed = firm.claims.preview(firm.cut(), firm_id=firm.firm_id)
    one = firm.claims.preview(
        firm.cut([_line(syrup, old="58", new="50", batch=late)]),
        firm_id=firm.firm_id,
    )
    spread = firm.claims.preview(
        firm.cut([_line(syrup, old="58", new="50", batch=late), _line(syrup)]),
        firm_id=firm.firm_id,
    )

    assert [
        (line.product_name, line.batch_number, line.quantity, line.amount)
        for line in proposed.lines
    ] == [
        ("Product SYR-1", "EARLY", D("10.0000"), D("100.00")),
        ("Product SYR-1", "LATE", D("4.0000"), D("40.00")),
        ("Product TAB-1", None, D("7.0000"), D("70.00")),
    ]
    assert {line.batch_id for line in proposed.lines} == {early.id, late.id, None}
    assert len({line.source_id for line in proposed.lines}) == 3
    assert [(line.batch_number, line.amount) for line in one.lines] == [
        ("LATE", D("32.00"))
    ]
    # A line naming no batch covers every batch another line does not name.
    assert [(line.batch_number, line.amount) for line in spread.lines] == [
        ("EARLY", D("100.00")),
        ("LATE", D("32.00")),
    ]


def test_the_claim_is_owed_by_the_principal_and_credits_the_price_variance() -> None:
    """Dr claims receivable, Cr purchase price variance; the stock keeps its cost."""
    firm = _Stockist()
    before = firm.balance(VARIANCE)
    stock_before = firm.balance(ControlAccountPurpose.INVENTORY)
    cost_before = (
        firm.session.query(ProductValuation.average_cost)
        .filter(ProductValuation.product_id == firm.tab.id)
        .scalar()
    )

    claim = firm.claims.raise_claim(
        firm.cut(), firm_id=firm.firm_id, actor_id=firm.actor
    )

    (view,) = firm.claims.responses([claim])
    assert (
        view.rate_difference_amount,
        view.scheme_amount,
        view.total_amount,
        view.outstanding,
        view.status,
    ) == (D("70.00"), D("0"), D("70.00"), D("70.00"), "RAISED")
    assert (view.period_from, view.period_to) == (CUT, CUT)
    assert [
        (
            line.kind,
            line.product_name,
            line.quantity,
            line.old_rate,
            line.new_rate,
            line.amount,
        )
        for line in view.lines
    ] == [
        (
            "RATE_DIFFERENCE",
            "Product TAB-1",
            D("7.0000"),
            D("60.0000"),
            D("50.0000"),
            D("70.00"),
        )
    ]
    assert firm.balance(RECEIVABLE) == D("70")
    assert firm.balance(VARIANCE) == before - D("70")
    assert firm.balance(ControlAccountPurpose.INVENTORY) == stock_before
    assert (
        firm.session.query(ProductValuation.average_cost)
        .filter(ProductValuation.product_id == firm.tab.id)
        .scalar()
        == cost_before
    )


def test_the_same_stock_is_claimed_once_for_one_cut_until_the_claim_is_cancelled() -> (
    None
):
    """A second claim is refused by the first one's number; a cancel frees it."""
    firm = _Stockist()
    first = firm.claims.raise_claim(
        firm.cut(), firm_id=firm.firm_id, actor_id=firm.actor
    )

    assert firm.claims.preview(firm.cut(), firm_id=firm.firm_id).lines == []
    with pytest.raises(ValidationError, match="Nothing is left to claim"):
        firm.claims.raise_claim(firm.cut(), firm_id=firm.firm_id, actor_id=firm.actor)
    firm.session.rollback()
    with pytest.raises(
        ValidationError, match=f"TAB-1.*already claimed.*{first.claim_number}"
    ):
        firm.claims.raise_claim(
            firm.cut([_line(firm.tab, old="61", new="50")]),
            firm_id=firm.firm_id,
            actor_id=firm.actor,
        )
    firm.session.rollback()

    firm.claims.cancel(
        first.id, "wrong circular", firm_id=firm.firm_id, actor_id=firm.actor
    )

    assert firm.balance(RECEIVABLE) == D("0")
    again = firm.claims.raise_claim(
        firm.cut(), firm_id=firm.firm_id, actor_id=firm.actor
    )
    assert again.total_amount == D("70.00")
    # What the cancelled claim held is still shown on it.
    (cancelled,) = firm.claims.responses([first])
    assert (cancelled.status, len(cancelled.lines)) == ("CANCELLED", 1)


def test_a_rate_difference_claim_is_settled_like_any_other(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The principal's payment brings what is owed down, then closes it."""
    firm = _Stockist()
    # A payment's journal reference is stamped to the second, and these two
    # are recorded in the same one: give each its own instant.
    instants = iter(datetime(2026, 9, 20, 10, 0, second) for second in range(60))
    monkeypatch.setattr("app.principal_claims.services.utc_now", lambda: next(instants))
    claim = firm.claims.raise_claim(
        firm.cut(), firm_id=firm.firm_id, actor_id=firm.actor
    )
    from app.contra.services.contra_service import ContraVoucherService

    bank = ContraVoucherService(firm.session).money_accounts(firm.firm_id)[0]

    for amount, owed, status in (
        ("30", D("40.00"), "PART_SETTLED"),
        ("40", D("0.00"), "SETTLED"),
    ):
        firm.claims.record_receipt(
            claim.id,
            PrincipalClaimReceiptWrite(
                received_on=date(2026, 9, 20),
                amount=D(amount),
                money_account_id=bank.id,
            ),
            firm_id=firm.firm_id,
            actor_id=firm.actor,
        )
        (view,) = firm.claims.responses([claim])
        assert (view.outstanding, view.status) == (owed, status)
    assert firm.balance(RECEIVABLE) == D("0")


def test_kinds_selects_it_and_a_period_claim_leaves_it_out() -> None:
    """Asked for by name and alone; the period's claim never gathers it."""
    firm = _Stockist()

    period = firm.claims.preview(firm.write(), firm_id=firm.firm_id)

    assert period.rate_difference_amount == D("0")
    assert all(line.kind != "RATE_DIFFERENCE" for line in period.lines)
    assert "RATE_DIFFERENCE" not in firm.write().kinds
    with pytest.raises(PydanticValidationError, match="stands on its own"):
        PrincipalClaimWrite(
            principal_id=firm.principal.id,
            effective_date=CUT,
            period_from=CUT,
            period_to=CUT,
            claim_date=CUT,
            kinds=["SCHEME", "RATE_DIFFERENCE"],
        )
    with pytest.raises(PydanticValidationError, match="date the new rates"):
        PrincipalClaimWrite(
            principal_id=firm.principal.id,
            period_from=CUT,
            period_to=CUT,
            claim_date=CUT,
            kinds=["RATE_DIFFERENCE"],
        )
    with pytest.raises(PydanticValidationError, match="only a rate difference"):
        PrincipalClaimWrite(
            principal_id=firm.principal.id,
            period_from=CUT,
            period_to=CUT,
            claim_date=CUT,
            effective_date=CUT,
        )
    with pytest.raises(PydanticValidationError, match="more than once"):
        firm.cut([_line(firm.tab), _line(firm.tab, old="60", new="55")])


def test_a_cut_that_has_not_taken_effect_cannot_be_claimed() -> None:
    """Tomorrow's cut: today's stock is not yet what closes the day before."""
    firm = _Stockist()
    tomorrow = firm_today(firm.session, firm.firm_id) + timedelta(days=1)

    with pytest.raises(ValidationError, match="has not taken effect"):
        firm.claims.preview(
            PrincipalClaimWrite(
                principal_id=firm.principal.id,
                effective_date=tomorrow,
                claim_date=tomorrow,
                kinds=["RATE_DIFFERENCE"],
            ),
            firm_id=firm.firm_id,
        )


def test_the_list_and_the_statement_carry_the_rate_difference() -> None:
    """The claims list shows the kind's total; the PDF draws its own table."""
    firm = _Stockist()
    syrup = firm.item("SYR-1", bought="60", revised="50", batched=True)
    firm.receive(syrup, "10", date(2026, 8, 1), batch="EARLY")
    claim = firm.claims.raise_claim(
        firm.cut(), firm_id=firm.firm_id, actor_id=firm.actor
    )

    (row,) = firm.claims.responses(firm.claims.list_rows(firm.firm_id))
    pdf, filename = firm.claims.render_statement(claim.id, firm_id=firm.firm_id)

    assert (row.rate_difference_amount, row.total_amount) == (D("170.00"), D("170.00"))
    assert [(line.batch_number, line.amount) for line in row.lines] == [
        ("EARLY", D("100.00")),
        (None, D("70.00")),
    ]
    assert pdf.startswith(b"%PDF") and filename.endswith(".pdf")
    tables = firm.claims.statement_tables(row)
    assert [(table.heading, table.columns) for table in tables] == [
        (
            "Rate difference on stock in hand",
            ("Item", "Batch", "Quantity", "Old rate", "New rate", "Amount"),
        )
    ]
    assert tables[0].rows == [
        ("Product SYR-1", "EARLY", "10", "60.00", "50.00", "100.00"),
        ("Product TAB-1", "", "7", "60.00", "50.00", "70.00"),
    ]
