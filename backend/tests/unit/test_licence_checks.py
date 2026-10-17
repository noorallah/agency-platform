"""Sales and purchases checked against trade licences (backlog 54, steps 2, 3, 5).

A product needs a licence type when it names one or any category above it
does; a sale is judged against the customer and the selling branch on the
document's own date, a purchase against the vendor. Warn by default; block
if the firm chooses, the sale side only; override by permission, recorded.
"""

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError as SchemaError
from sqlalchemy import select

from app.common.audit.models import AuditLog
from app.common.scope import ResolvedFirmScope
from app.core.exceptions import AuthorizationError, ConflictError, ValidationError
from app.document_framework.models import DocumentLifecycleEvent
from app.inventory.models import InventoryTransaction
from app.products.models import ProductCategory
from app.products.schemas import ProductCategoryUpdate
from app.products.services import ProductService
from app.sales_invoice.api.router import create_sales_invoice
from app.sales_invoice.schemas import SalesInvoiceStatus
from app.sales_invoice.services import SalesInvoiceService
from app.sales_order.api.router import create_sales_order
from app.sales_order.schemas import SalesOrderCreate, SalesOrderLineWrite
from app.sales_order.services import SalesOrderService
from app.trade_licences.api.override import authorised_override
from app.trade_licences.models import TradeLicence, TradeLicenceType
from app.trade_licences.schemas import (
    LicenceEnforcement,
    LicenceParty,
    LicenceShortfall,
    TradeLicenceSettingsWrite,
)
from app.trade_licences.services import TradeLicenceService
from app.trade_licences.services.licence_check import (
    LicenceCheckService,
    LicenceDocument,
    LicenceLine,
)
from app.vendors.models import Vendor
from tests.unit.test_sales_chain_synthesis import _Firm, _session_factory

ORDER_DATE = date(2026, 8, 4)


class _Pharma(_Firm):
    """The counter-selling firm, trading one product that needs a licence."""

    def __init__(self) -> None:
        """Build the firm and make its product a wholesale-drug line."""
        super().__init__(_session_factory()())
        self.actor_id = uuid4()
        self.types = {
            row.code: row
            for row in TradeLicenceService(self.session).list_types(
                self.firm.id, self.actor_id
            )
        }
        self.drug = self.types["DRUG_WHOLESALE"]
        self.category = ProductCategory(
            firm_id=self.firm.id,
            code="SCHED-H",
            name="Schedule H",
            path="SCHED-H",
            required_licence_type_ids=[self.drug.id],
        )
        self.session.add(self.category)
        self.session.flush()
        self.product.category_id = self.category.id
        self.session.commit()
        self.checks = LicenceCheckService(self.session)

    def hold(
        self,
        *,
        customer: bool = False,
        branch: bool = False,
        valid_from: date | None = None,
        valid_to: date | None = date(2027, 3, 31),
        licence_type: TradeLicenceType | None = None,
    ) -> None:
        """Record a licence for the customer or the firm (per branch)."""
        self.session.add(
            TradeLicence(
                firm_id=self.firm.id,
                licence_type_id=(licence_type or self.drug).id,
                holder_type="CUSTOMER" if customer else "FIRM",
                customer_id=self.customer.id if customer else None,
                branch_id=self.branch.id if branch else None,
                licence_number="DL-C" if customer else "DL-F",
                valid_from=valid_from,
                valid_to=valid_to,
            )
        )
        self.session.commit()

    def policy(
        self,
        sale: LicenceEnforcement,
        purchase: LicenceEnforcement = LicenceEnforcement.WARN,
    ) -> None:
        """Set the firm's licence-check policy."""
        self.checks.update_settings(
            TradeLicenceSettingsWrite(
                sale_enforcement=sale, purchase_enforcement=purchase
            ),
            firm_id=self.firm.id,
            actor_id=self.actor_id,
        )

    def sale(self, on: date = ORDER_DATE) -> None:
        """Judge a one-line sale of the product, keeping the result."""
        result = self.checks.check_sale(
            firm_id=self.firm.id,
            customer_id=self.customer.id,
            branch_id=self.branch.id,
            on=on,
            lines=[LicenceLine(1, self.product.id)],
        )
        self.last = result

    def order(self) -> UUID:
        """Raise a draft sales order for one unit of the product."""
        row = SalesOrderService(self.session).create_order(
            SalesOrderCreate(
                customer_id=self.customer.id,
                branch_id=self.branch.id,
                warehouse_id=self.warehouse.id,
                order_date=ORDER_DATE,
                lines=[
                    SalesOrderLineWrite(
                        line_number=1,
                        product_id=self.product.id,
                        quantity=Decimal("1"),
                        unit_price=Decimal("100"),
                    )
                ],
            ),
            firm_id=self.firm.id,
            actor_id=self.actor_id,
        )
        return row.id

    def approval_event(self, document_id: UUID) -> DocumentLifecycleEvent:
        """Return the APPROVED event on a document's timeline."""
        event = self.session.scalar(
            select(DocumentLifecycleEvent).where(
                DocumentLifecycleEvent.source_document_id == document_id,
                DocumentLifecycleEvent.action == "APPROVED",
            )
        )
        assert event is not None
        return event


@pytest.fixture
def pharma() -> _Pharma:
    """Build a pharma firm whose product needs a wholesale drug licence."""
    return _Pharma()


# -- what a product needs -----------------------------------------------------


def test_a_product_needs_its_own_type_else_the_nearest_category_s(
    pharma: _Pharma,
) -> None:
    """Own beats category; a sub-category without one takes its parent's."""
    child = ProductCategory(
        firm_id=pharma.firm.id,
        code="SCHED-H-TAB",
        name="Tablets",
        parent_id=pharma.category.id,
        level=1,
        path="SCHED-H/SCHED-H-TAB",
    )
    pharma.session.add(child)
    pharma.session.flush()
    pharma.product.category_id = child.id
    pharma.session.commit()
    needed = pharma.checks.required_types(pharma.firm.id, {pharma.product.id})
    assert needed == {pharma.product.id: (pharma.drug.id,)}

    pharma.product.required_licence_type_ids = [pharma.types["DRUG_SCHEDULE_X"].id]
    pharma.session.commit()
    needed = pharma.checks.required_types(pharma.firm.id, {pharma.product.id})
    assert needed == {pharma.product.id: (pharma.types["DRUG_SCHEDULE_X"].id,)}

    pharma.product.required_licence_type_ids = []
    pharma.product.category_id = None
    pharma.session.commit()
    assert pharma.checks.required_types(pharma.firm.id, {pharma.product.id}) == {}


def test_a_category_edit_that_omits_the_field_keeps_the_requirement(
    pharma: _Pharma,
) -> None:
    """A client that predates the field must not clear it by saving a name."""
    ProductService(pharma.session).update_category(
        pharma.category.id,
        ProductCategoryUpdate(code="SCHED-H", name="Schedule H drugs"),
        firm_scope=pharma.firm.id,
        actor_id=pharma.actor_id,
    )
    assert pharma.category.required_licence_type_ids == [pharma.drug.id]
    with pytest.raises(ValidationError, match="Licence type not found"):
        ProductService(pharma.session).update_category(
            pharma.category.id,
            ProductCategoryUpdate(
                code="SCHED-H",
                name="Schedule H",
                required_licence_type_ids=[uuid4()],
            ),
            firm_scope=pharma.firm.id,
            actor_id=pharma.actor_id,
        )


def test_a_type_goods_need_cannot_be_deleted(pharma: _Pharma) -> None:
    """A soft delete never reaches the foreign key, so the service counts."""
    with pytest.raises(ConflictError, match="need a Drug licence"):
        TradeLicenceService(pharma.session).delete_type(
            pharma.drug.id, firm_id=pharma.firm.id, actor_id=pharma.actor_id
        )


# -- the judgement ------------------------------------------------------------


def test_nobody_holding_it_names_both_parties_and_the_line(pharma: _Pharma) -> None:
    """Missing for the customer and for the firm, with the line and product."""
    pharma.sale()
    result = pharma.last
    assert result.enforcement is LicenceEnforcement.WARN
    assert not result.would_block
    assert [(f.party, f.shortfall) for f in result.findings] == [
        (LicenceParty.CUSTOMER, LicenceShortfall.MISSING),
        (LicenceParty.SELLER, LicenceShortfall.MISSING),
    ]
    assert result.findings[0].line_numbers == [1]
    assert result.message is not None
    assert "Line 1 (Product SKU-001)" in result.message
    assert "Customer CUS-001 holds no Drug licence, wholesale" in result.message


def test_the_firm_s_licence_counts_for_its_branch_or_the_whole_firm(
    pharma: _Pharma,
) -> None:
    """A branch licence covers that branch; with the customer's, all is clear."""
    pharma.hold(branch=True)
    pharma.hold(customer=True)
    pharma.sale()
    assert pharma.last.findings == []


def test_it_is_judged_on_the_document_s_date(pharma: _Pharma) -> None:
    """Expired before the date, or not yet started on it, is named as such."""
    pharma.hold()
    pharma.hold(customer=True, valid_to=ORDER_DATE - timedelta(days=1))
    pharma.sale()
    (finding,) = pharma.last.findings
    assert finding.shortfall is LicenceShortfall.EXPIRED
    assert "expired on 2026-08-03" in finding.message

    pharma.hold(customer=True, valid_from=ORDER_DATE + timedelta(days=5))
    pharma.sale()
    (finding,) = pharma.last.findings
    assert finding.shortfall is LicenceShortfall.NOT_YET_VALID
    # The same licence covers a sale dated after it starts.
    pharma.sale(on=ORDER_DATE + timedelta(days=5))
    assert pharma.last.findings == []


def test_a_licence_of_another_type_does_not_cover_it(pharma: _Pharma) -> None:
    """A retail drug licence does not permit a wholesale purchase."""
    pharma.hold()
    pharma.hold(customer=True, licence_type=pharma.types["DRUG_RETAIL"])
    pharma.sale()
    assert [f.party for f in pharma.last.findings] == [LicenceParty.CUSTOMER]


def test_goods_needing_nothing_are_never_flagged(pharma: _Pharma) -> None:
    """The check is per line: a customer with no licence buys the rest."""
    pharma.category.required_licence_type_ids = []
    pharma.session.commit()
    pharma.policy(LicenceEnforcement.BLOCK)
    pharma.sale()
    assert pharma.last.findings == []


def test_off_checks_nothing(pharma: _Pharma) -> None:
    """A firm that switched the check off gets no findings."""
    pharma.policy(LicenceEnforcement.OFF)
    pharma.sale()
    assert pharma.last.findings == []


def test_the_purchase_side_never_blocks() -> None:
    """BLOCK is refused for purchases: the goods on the dock have arrived."""
    with pytest.raises(SchemaError, match="only warns"):
        TradeLicenceSettingsWrite(
            sale_enforcement=LicenceEnforcement.BLOCK,
            purchase_enforcement=LicenceEnforcement.BLOCK,
        )


# -- at approval --------------------------------------------------------------


def test_warn_approves_and_records_the_warning(pharma: _Pharma) -> None:
    """The order is approved; the timeline says what was missing."""
    order_id = pharma.order()
    SalesOrderService(pharma.session).approve_order(
        order_id, firm_scope=pharma.firm.id, actor_id=pharma.actor_id
    )
    event = pharma.approval_event(order_id)
    assert event.details_json is not None
    assert "licence_warning" in event.details_json
    assert event.remarks is not None
    assert "holds no Drug licence" in event.remarks


def test_block_refuses_and_reserves_nothing(pharma: _Pharma) -> None:
    """Refused before stock is held; an override reason lets it through."""
    pharma.policy(LicenceEnforcement.BLOCK)
    order_id = pharma.order()
    orders = SalesOrderService(pharma.session)
    movements = len(pharma.session.scalars(select(InventoryTransaction)).all())
    with pytest.raises(ValidationError, match="refuses a sale without"):
        orders.approve_order(
            order_id, firm_scope=pharma.firm.id, actor_id=pharma.actor_id
        )
    pharma.session.rollback()
    assert orders.get_order(order_id, firm_scope=pharma.firm.id).status == "DRAFT"
    assert len(pharma.session.scalars(select(InventoryTransaction)).all()) == movements

    approved = orders.approve_order(
        order_id,
        firm_scope=pharma.firm.id,
        actor_id=pharma.actor_id,
        licence_override_reason="Licence renewal filed; copy on record.",
    )
    assert approved.status == "APPROVED"
    event = pharma.approval_event(order_id)
    assert event.details_json is not None
    override = event.details_json["licence_override"]
    assert isinstance(override, dict)
    assert override["reason"] == "Licence renewal filed; copy on record."
    assert event.remarks is not None
    assert event.remarks.startswith("Licence check overridden")


def test_a_counter_bill_is_checked_once_at_its_own_approval(
    pharma: _Pharma,
) -> None:
    """The order and note it raises are not checked; the bill is."""
    pharma.stages(quotation=False, sales_order=False, delivery_note=False)
    pharma.policy(LicenceEnforcement.BLOCK)
    bills = SalesInvoiceService(pharma.session)
    draft = bills.create_invoice(
        pharma.bare_bill(), firm_id=pharma.firm.id, actor_id=pharma.actor_id
    )
    with pytest.raises(ValidationError, match="holds no Drug licence"):
        bills.approve_invoice(
            draft.id, firm_scope=pharma.firm.id, actor_id=pharma.actor_id
        )
    pharma.session.rollback()

    pharma.hold()
    pharma.hold(customer=True)
    approved = bills.approve_invoice(
        draft.id, firm_scope=pharma.firm.id, actor_id=pharma.actor_id
    )
    assert approved.status == SalesInvoiceStatus.APPROVED.value


# -- a drug licence with no expiry date (owner decision 2026-10-17) ------------

_NO_EXPIRY = (
    "Drug licence, wholesale DL-C for {name} has no expiry date; please add it."
)


def _caller(pharma: _Pharma) -> object:
    """Return a scope as a create route receives it, holding every code."""
    return SimpleNamespace(
        firm_id=pharma.firm.id,
        actor_id=pharma.actor_id,
        principal=SimpleNamespace(has_permission=lambda code: True),
    )


def _created(pharma: _Pharma, document_id: UUID) -> DocumentLifecycleEvent:
    """Return the CREATED event on a document's timeline."""
    event = pharma.session.scalar(
        select(DocumentLifecycleEvent).where(
            DocumentLifecycleEvent.source_document_id == document_id,
            DocumentLifecycleEvent.action == "CREATED",
        )
    )
    assert event is not None
    return event


def test_a_new_order_warns_of_a_drug_licence_with_no_expiry(
    pharma: _Pharma,
) -> None:
    """Recorded at creation, returned as the message, and never blocking."""
    pharma.policy(LicenceEnforcement.BLOCK)
    pharma.hold()
    pharma.hold(customer=True, valid_to=None)
    expected = _NO_EXPIRY.format(name=pharma.customer.display_name)

    response = create_sales_order(
        SalesOrderCreate(
            customer_id=pharma.customer.id,
            branch_id=pharma.branch.id,
            warehouse_id=pharma.warehouse.id,
            order_date=ORDER_DATE,
            lines=[
                SalesOrderLineWrite(
                    line_number=1,
                    product_id=pharma.product.id,
                    quantity=Decimal("1"),
                    unit_price=Decimal("100"),
                )
            ],
        ),
        _caller(pharma),  # type: ignore[arg-type]
        pharma.session,
    )
    assert response.message == expected
    order_id = response.data.id
    details = _created(pharma, order_id).details_json
    assert details is not None
    warning = details["licence_expiry_warning"]
    assert isinstance(warning, dict)
    assert warning["message"] == expected
    audit = pharma.session.scalar(
        select(AuditLog).where(
            AuditLog.entity_id == order_id, AuditLog.action == "sales_order.created"
        )
    )
    assert audit is not None and audit.after_data is not None
    assert audit.after_data["licence_expiry_warning"] == warning

    # The licence still covers the sale, so even BLOCK approves it.
    approved = SalesOrderService(pharma.session).approve_order(
        order_id, firm_scope=pharma.firm.id, actor_id=pharma.actor_id
    )
    assert approved.status == "APPROVED"


def test_a_new_bill_warns_and_one_with_its_date_does_not(pharma: _Pharma) -> None:
    """A counter bill says it; a licence with its valid-to says nothing."""
    pharma.stages(quotation=False, sales_order=False, delivery_note=False)
    pharma.hold(customer=True, valid_to=None)
    response = create_sales_invoice(
        _caller(pharma),  # type: ignore[arg-type]
        pharma.session,
        pharma.bare_bill(),
    )
    assert response.message == _NO_EXPIRY.format(name=pharma.customer.display_name)
    details = _created(pharma, response.data.id).details_json
    assert details is not None
    assert "licence_expiry_warning" in details

    licence = pharma.session.scalar(
        select(TradeLicence).where(TradeLicence.customer_id == pharma.customer.id)
    )
    assert licence is not None
    licence.valid_to = date(2027, 3, 31)
    pharma.session.commit()
    quiet = create_sales_invoice(
        _caller(pharma),  # type: ignore[arg-type]
        pharma.session,
        pharma.bare_bill(),
    )
    assert quiet.message is None
    details = _created(pharma, quiet.data.id).details_json
    assert details is not None
    assert "licence_expiry_warning" not in details


def test_the_purchase_check_asks_the_vendor(pharma: _Pharma) -> None:
    """A vendor with no drug licence is named; one with it is not."""
    vendor = Vendor(
        firm_id=pharma.firm.id,
        code="VEN-1",
        name="Pharma Supplies",
        display_name="Pharma Supplies",
        status="ACTIVE",
    )
    pharma.session.add(vendor)
    pharma.session.commit()
    lines = [LicenceLine(1, pharma.product.id)]
    result = pharma.checks.check_purchase(
        firm_id=pharma.firm.id, vendor_id=vendor.id, on=ORDER_DATE, lines=lines
    )
    assert [f.party for f in result.findings] == [LicenceParty.VENDOR]
    assert not result.would_block
    pharma.session.add(
        TradeLicence(
            firm_id=pharma.firm.id,
            licence_type_id=pharma.drug.id,
            holder_type="VENDOR",
            vendor_id=vendor.id,
            licence_number="DL-V",
            valid_to=date(2027, 3, 31),
        )
    )
    pharma.session.commit()
    result = pharma.checks.check_purchase(
        firm_id=pharma.firm.id, vendor_id=vendor.id, on=ORDER_DATE, lines=lines
    )
    assert result.findings == []


def test_the_preview_judges_a_saved_document_as_approval_would(
    pharma: _Pharma,
) -> None:
    """The endpoint's answer is the approval's, on the document's date."""
    pharma.policy(LicenceEnforcement.BLOCK)
    order_id = pharma.order()
    result = pharma.checks.check_document(
        LicenceDocument.SALES_ORDER, order_id, firm_id=pharma.firm.id
    )
    assert result.would_block
    assert result.on == ORDER_DATE


def test_only_the_override_permission_may_give_a_reason() -> None:
    """A reason from someone without the permission is refused, not ignored."""

    def scope(*codes: str) -> ResolvedFirmScope:
        """Build a scope whose principal holds the given codes."""
        principal = SimpleNamespace(has_permission=lambda code: code in codes)
        return ResolvedFirmScope(principal=principal, firm_id=uuid4())  # type: ignore[arg-type]

    assert authorised_override(scope(), None) is None
    assert authorised_override(scope(), "   ") is None
    with pytest.raises(AuthorizationError):
        authorised_override(scope(), "because")
    assert (
        authorised_override(scope("TRADE_LICENCE_OVERRIDE"), " because ") == "because"
    )
