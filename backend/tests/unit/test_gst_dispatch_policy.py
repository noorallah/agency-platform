"""Backlog 77 rows 1-3: why the goods go out, and the invoice at removal.

A tax invoice for goods is issued at or before their removal (CGST s.31); a
challan may carry them ahead of it only for a reason the rules allow (r.55).
Every delivery note now says why it goes out, a sale dispatched by hand before
its invoice is judged by the firm's policy (OFF / WARN, the default / BLOCK),
and *Dispatch and invoice* dispatches and bills a note in one transaction.
"""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.models import AuditLog
from app.core.exceptions import AuthorizationError, ValidationError
from app.delivery_note.api.router import (
    check_delivery_note_dispatch,
    dispatch_and_invoice_delivery_note,
)
from app.delivery_note.models import DeliveryNote
from app.delivery_note.schemas import DeliveryNoteCreate, DeliveryNoteLineWrite
from app.delivery_note.services import DeliveryNoteService
from app.finance.services.opening_setup import seed_finance_setup
from app.firms.models import Firm
from app.sales_invoice.models import SalesInvoiceLine
from app.tax.schemas.gst_compliance import GstComplianceSettingsWrite
from app.tax.services.gst_compliance import GstComplianceService
from tests.unit.test_delivery_note_module import (
    _approved_order,
    _branch,
    _customer,
    _firm,
    _product,
    _session_factory,
    _stock,
    _warehouse,
)


class _Shop:
    """A firm with its books, stock and one approved order of 10."""

    def __init__(self) -> None:
        """Build everything a dispatch and a bill need."""
        self.session: Session = _session_factory()()
        self.firm: Firm = _firm(self.session)
        seed_finance_setup(
            self.session,
            firm_id=self.firm.id,
            year_starts_on=date(2026, 4, 1),
            actor_id=uuid4(),
        )
        self.session.commit()
        branch = _branch(self.session, firm_id=self.firm.id)
        warehouse = _warehouse(self.session, firm_id=self.firm.id, branch_id=branch.id)
        customer = _customer(self.session, firm_id=self.firm.id)
        product = _product(self.session, firm_id=self.firm.id)
        self.actor_id = uuid4()
        _stock(
            self.session,
            firm=self.firm,
            branch=branch,
            warehouse=warehouse,
            product=product,
        )
        self.order, self.order_line = _approved_order(
            self.session,
            firm=self.firm,
            branch=branch,
            warehouse=warehouse,
            customer=customer,
            product=product,
            quantity=Decimal("10"),
            actor_id=self.actor_id,
        )
        self.notes = DeliveryNoteService(self.session)

    def note(
        self,
        reason: str | None = None,
        *,
        words: str | None = None,
        quantity: str = "2",
        approve: bool = True,
    ) -> DeliveryNote:
        """Raise (and approve) one note of the order."""
        row = self.notes.create_note(
            DeliveryNoteCreate(
                sales_order_id=self.order.id,
                delivery_date=date(2026, 8, 4),
                challan_reason=reason,  # type: ignore[arg-type]
                challan_reason_note=words,
                lines=[
                    DeliveryNoteLineWrite(
                        sales_order_line_id=self.order_line.id,
                        line_number=1,
                        current_delivery_quantity=Decimal(quantity),
                        unit_price=Decimal("100"),
                    )
                ],
            ),
            firm_id=self.firm.id,
            actor_id=self.actor_id,
        )
        if approve:
            self.notes.approve_note(
                row.id, firm_scope=self.firm.id, actor_id=self.actor_id
            )
        return row

    def policy(
        self, enforcement: str, *, route_sale_needs_invoice: bool = False
    ) -> None:
        """Set the firm's policy on dispatch before the invoice."""
        GstComplianceService(self.session).update_settings(
            GstComplianceSettingsWrite(
                einvoice_applicable_from=None,
                thirty_day_rule_from=None,
                dispatch_without_invoice=enforcement,  # type: ignore[arg-type]
                route_sale_needs_invoice=route_sale_needs_invoice,
            ),
            firm_id=self.firm.id,
            actor_id=self.actor_id,
        )

    def dispatch(self, note: DeliveryNote) -> DeliveryNote:
        """Dispatch a note by hand."""
        return self.notes.dispatch_note(
            note.id, firm_scope=self.firm.id, actor_id=self.actor_id
        )

    def scope(self, *permissions: str) -> object:
        """Build the scope a request from somebody holding these codes carries."""
        held = frozenset(permissions)
        return SimpleNamespace(
            firm_id=self.firm.id,
            actor_id=self.actor_id,
            principal=SimpleNamespace(has_permission=lambda code: code in held),
        )


def _audit_warning(session: Session, note_id: UUID) -> object:
    """Return the warning the dispatch's audit row kept, if any."""
    row = session.scalar(
        select(AuditLog).where(
            AuditLog.entity_id == note_id,
            AuditLog.action == "delivery_note.dispatched",
        )
    )
    assert row is not None
    after = row.after_data or {}
    return after.get("gst_warning") if isinstance(after, dict) else None


def test_a_sale_dispatched_before_its_invoice_is_warned_by_default() -> None:
    """No policy chosen: the note goes, and the warning is kept on the trail."""
    shop = _Shop()
    note = shop.note()
    assert note.challan_reason == "SALE"

    check = check_delivery_note_dispatch(
        note_id=note.id,
        scope=shop.scope("SALES_VIEW"),  # type: ignore[arg-type]
        db=shop.session,
    ).data
    assert check is not None
    assert check.enforcement == "WARN"
    assert check.would_block is False
    assert "CGST s.31" in (check.message or "")

    shipped = shop.dispatch(note)
    assert shipped.status == "DISPATCHED"
    assert "CGST s.31" in str(_audit_warning(shop.session, note.id))


def test_a_firm_that_blocks_refuses_a_sale_but_not_a_challan_with_a_reason() -> None:
    """BLOCK stops a sale; on approval or quantity unknown still go."""
    shop = _Shop()
    shop.policy("BLOCK")
    sale = shop.note()
    with pytest.raises(ValidationError, match="Dispatch and invoice"):
        shop.dispatch(sale)
    shop.session.rollback()
    assert shop.notes.get_note(sale.id, firm_scope=shop.firm.id).status == "APPROVED"
    # Completing an approved note dispatches it too, so it is judged as well.
    with pytest.raises(ValidationError, match="CGST s.31"):
        shop.notes.complete_note(
            sale.id, firm_scope=shop.firm.id, actor_id=shop.actor_id
        )
    shop.session.rollback()

    for reason in ("ON_APPROVAL", "QUANTITY_UNKNOWN", "JOB_WORK"):
        note = shop.note(reason, quantity="1")
        assert shop.dispatch(note).status == "DISPATCHED"
        assert _audit_warning(shop.session, note.id) is None


def test_a_route_sale_follows_what_the_firms_ca_said() -> None:
    """A van sale goes on a challan unless the firm says it needs the invoice."""
    shop = _Shop()
    shop.policy("BLOCK")
    van = shop.note("ROUTE_SALE", quantity="1")
    assert shop.dispatch(van).status == "DISPATCHED"

    shop.policy("BLOCK", route_sale_needs_invoice=True)
    second = shop.note("ROUTE_SALE", quantity="1")
    with pytest.raises(ValidationError, match="van or route sale"):
        shop.dispatch(second)


def test_off_says_nothing() -> None:
    """A firm that switched the check off dispatches as before."""
    shop = _Shop()
    shop.policy("OFF")
    note = shop.note()
    assert shop.dispatch(note).status == "DISPATCHED"
    assert _audit_warning(shop.session, note.id) is None


def test_other_must_say_what_it_is() -> None:
    """OTHER needs the firm's words; any other reason keeps none."""
    shop = _Shop()
    with pytest.raises(ValidationError, match="Say why"):
        shop.note("OTHER", approve=False)
    shop.session.rollback()
    note = shop.note("OTHER", words="Exhibition stock", approve=False)
    assert note.challan_reason_note == "Exhibition stock"
    response = shop.notes.note_response(note)
    assert (response.challan_reason, response.challan_reason_note) == (
        "OTHER",
        "Exhibition stock",
    )
    plain = shop.note("ON_APPROVAL", words="ignored", approve=False)
    assert plain.challan_reason_note is None


def test_dispatch_and_invoice_bills_the_note_as_the_goods_leave() -> None:
    """One action: the note dispatched, its bill raised and approved."""
    shop = _Shop()
    shop.policy("BLOCK")
    note = shop.note(quantity="3")

    with pytest.raises(AuthorizationError, match="SALES_CREATE"):
        dispatch_and_invoice_delivery_note(
            note_id=note.id,
            scope=shop.scope("SALES_APPROVE"),  # type: ignore[arg-type]
            db=shop.session,
        )
    bill = dispatch_and_invoice_delivery_note(
        note_id=note.id,
        scope=shop.scope("SALES_APPROVE", "SALES_CREATE"),  # type: ignore[arg-type]
        db=shop.session,
    ).data
    assert bill is not None
    assert bill.status == "APPROVED"
    assert shop.notes.get_note(note.id, firm_scope=shop.firm.id).status == (
        "DISPATCHED"
    )
    lines = shop.session.scalars(
        select(SalesInvoiceLine).where(SalesInvoiceLine.sales_invoice_id == bill.id)
    ).all()
    assert [
        (line.source_document_id, line.current_invoice_quantity) for line in lines
    ] == [(note.id, Decimal("3.0000"))]
    # A dispatched note cannot be dispatched and invoiced again.
    with pytest.raises(ValidationError, match="only an approved delivery note"):
        dispatch_and_invoice_delivery_note(
            note_id=note.id,
            scope=shop.scope("SALES_APPROVE", "SALES_CREATE"),  # type: ignore[arg-type]
            db=shop.session,
        )


def test_the_settings_keep_the_dates_in_order() -> None:
    """The 30-day limit needs e-invoicing, and cannot start before it."""
    with pytest.raises(PydanticValidationError, match="firm that e-invoices"):
        GstComplianceSettingsWrite(
            einvoice_applicable_from=None,
            thirty_day_rule_from=date(2026, 4, 1),
            dispatch_without_invoice="WARN",
            route_sale_needs_invoice=False,
        )
    with pytest.raises(PydanticValidationError, match="cannot start before"):
        GstComplianceSettingsWrite(
            einvoice_applicable_from=date(2026, 4, 1),
            thirty_day_rule_from=date(2025, 4, 1),
            dispatch_without_invoice="WARN",
            route_sale_needs_invoice=False,
        )
    shop = _Shop()
    service = GstComplianceService(shop.session)
    assert service.settings_response(shop.firm.id).is_configured is False
    saved = service.update_settings(
        GstComplianceSettingsWrite(
            einvoice_applicable_from=date(2026, 4, 1),
            thirty_day_rule_from=date(2026, 4, 1),
            dispatch_without_invoice="BLOCK",
            route_sale_needs_invoice=True,
        ),
        firm_id=shop.firm.id,
        actor_id=shop.actor_id,
    )
    assert saved.is_configured is True
    assert saved.einvoice_applicable_from == date(2026, 4, 1)
    assert saved.dispatch_without_invoice == "BLOCK"
