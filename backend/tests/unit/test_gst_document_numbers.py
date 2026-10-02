"""Backlog GST-2: GST document numbers are kept to 16 characters.

CGST rule 46(b) (and rules 53 and 55 for notes and challans) allows a serial
number of at most 16 characters -- letters, digits, '-' and '/' -- and the IRP
refuses a longer one. The platform's own default printed
``SI-2026-2027-000001``, 19 characters. A GST document's default now prints
the year as ``26-27``; a series for one that could pass 16 is refused when it
is saved, and so is a typed number; other documents are not judged.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from app.branches.models import Branch
from app.core.exceptions import ValidationError
from app.document_framework.models import DocumentNumberingRule
from app.document_framework.schemas import (
    DocumentNumberingRuleCreate,
    DocumentNumberingRuleUpdate,
)
from app.document_framework.services import DocumentFrameworkService
from app.document_framework.services.gst_numbering import (
    gst_number_problem,
    short_year,
)
from app.document_framework.services.transactional_document_service import (
    DocumentStateSpec,
    DocumentTypeSpec,
    TransactionalDocumentService,
)
from app.firms.models import Firm
from app.sales_invoice.models import SalesInvoice
from tests.unit.test_document_framework import _firm, _session_factory

_STATES = (DocumentStateSpec(code="DRAFT", name="Draft", sort_order=1),)


class _Documents(TransactionalDocumentService):
    """A module reduced to the part that numbers its documents."""

    def series(self, firm_id: UUID, actor_id: UUID) -> DocumentNumberingRule:
        """Return the series the next document is numbered from."""
        return self._ensure_document_setup(firm_id=firm_id, actor_id=actor_id)[1]

    def issue(self, firm_id: UUID, actor_id: UUID) -> str:
        """Issue the next number, as a module's create does."""
        return self._documents.reserve_number(
            self.series(firm_id, actor_id).id,
            firm_id=firm_id,
            document_date=date(2026, 8, 1),
            actor_id=actor_id,
        )

    def typed(self, firm_id: UUID, actor_id: UUID, number: str) -> str:
        """Take a typed number, as a module's create does."""
        return self._issue_number(
            self.series(firm_id, actor_id),
            typed=number,
            number_column=SalesInvoice.invoice_number,
            firm_id=firm_id,
            document_date=date(2026, 8, 1),
            actor_id=actor_id,
        )


class _Invoices(_Documents):
    """The tax invoice: a GST document."""

    DOCUMENT = DocumentTypeSpec(
        code="SALES_INVOICE",
        name="Sales Invoice",
        description="A tax invoice.",
        category="SALES",
        module="sales_invoice",
        prefix="SI",
        states=_STATES,
    )


class _Challans(_Documents):
    """The delivery challan, whose default used to print firm and branch."""

    DOCUMENT = DocumentTypeSpec(
        code="DELIVERY_NOTE",
        name="Delivery Note",
        description="A delivery challan.",
        category="SALES",
        module="delivery_note",
        prefix="DN",
        states=_STATES,
        include_branch_code=True,
        include_company_code=True,
    )


class _Orders(_Documents):
    """A sales order: not a GST document."""

    DOCUMENT = DocumentTypeSpec(
        code="SALES_ORDER",
        name="Sales Order",
        description="An order.",
        category="SALES",
        module="sales_order",
        prefix="SO",
        states=_STATES,
    )


def _setup() -> tuple[Session, Firm, UUID]:
    """Return a session, a firm and an actor."""
    session = _session_factory()()
    return session, _firm(session), uuid4()


def test_the_rule_counts_characters_and_the_characters_allowed() -> None:
    """16 passes, 17 does not, and only '-' and '/' besides letters and digits."""
    assert gst_number_problem("SI/26-27/0000001") is None
    assert "17 characters" in (gst_number_problem("SI-2026-27-000001") or "")
    assert "character" in (gst_number_problem("SI_26_0001") or "")
    assert short_year("2026-2027") == "26-27"
    assert short_year("2026") == "2026"


def test_a_gst_document_s_default_prints_the_short_year() -> None:
    """``SI-26-27-000001``: 15 characters, still naming the year."""
    session, firm, actor = _setup()

    number = _Invoices(session).issue(firm.id, actor)

    assert number == "SI-26-27-000001"


def test_the_challan_s_default_leaves_out_the_firm_and_branch() -> None:
    """Those two alone took the old challan number past 25 characters."""
    session, firm, actor = _setup()

    series = _Challans(session).series(firm.id, actor)

    assert series.include_branch_code is False
    assert series.include_company_code is False
    assert _Challans(session).issue(firm.id, actor) == "DN-26-27-000001"


def test_a_document_that_is_not_a_gst_document_keeps_its_full_year() -> None:
    """An order is nobody's tax document, and its numbers stay as they were."""
    session, firm, actor = _setup()

    assert _Orders(session).issue(firm.id, actor) == "SO-2026-2027-000001"


def test_a_gst_series_that_could_pass_16_is_refused_when_saved() -> None:
    """Judged on the longest number it can print, on create and on edit."""
    session, firm, actor = _setup()
    series = _Invoices(session).series(firm.id, actor)
    session.commit()
    service = DocumentFrameworkService(session)

    with pytest.raises(ValidationError, match="at most 16"):
        service.create_numbering_rule(
            firm.id,
            DocumentNumberingRuleCreate(
                document_type_id=series.document_type_id,
                code="LONG",
                name="Long",
                prefix="INV",
                include_financial_year=True,
            ),
            actor,
        )
    session.rollback()

    with pytest.raises(ValidationError, match="Sales Invoice is a GST document"):
        service.update_numbering_rule(
            firm.id,
            series.id,
            DocumentNumberingRuleUpdate(
                document_type_id=series.document_type_id,
                code=series.code,
                name=series.name,
                short_financial_year=False,
            ),
            actor,
        )
    session.rollback()

    shorter = service.create_numbering_rule(
        firm.id,
        DocumentNumberingRuleCreate(
            document_type_id=series.document_type_id,
            code="SLASHED",
            name="Slashed",
            prefix="INV",
            separator="/",
            include_financial_year=True,
            short_financial_year=True,
            sequence_padding=5,
        ),
        actor,
    )
    assert shorter.short_financial_year is True


def test_the_longest_branch_code_is_what_a_branch_series_is_judged_on() -> None:
    """A branch code on the number counts at its longest."""
    session, firm, actor = _setup()
    series = _Invoices(session).series(firm.id, actor)
    session.add(
        Branch(firm_id=firm.id, code="WAREHOUSE7", name="Far", display_name="Far")
    )
    session.commit()

    with pytest.raises(ValidationError, match="WAREHOUSE7"):
        DocumentFrameworkService(session).create_numbering_rule(
            firm.id,
            DocumentNumberingRuleCreate(
                document_type_id=series.document_type_id,
                code="BY_BRANCH",
                name="By branch",
                prefix="SI",
                include_financial_year=True,
                short_financial_year=True,
                include_branch_code=True,
            ),
            actor,
        )


def test_a_format_pattern_may_name_the_short_year() -> None:
    """``{financial_year_short}`` prints ``26-27`` and satisfies the reset."""
    session, firm, actor = _setup()
    series = _Invoices(session).series(firm.id, actor)
    service = DocumentFrameworkService(session)
    rule = service.create_numbering_rule(
        firm.id,
        DocumentNumberingRuleCreate(
            document_type_id=series.document_type_id,
            code="PATTERN",
            name="Pattern",
            prefix="T",
            format_pattern="{prefix}/{financial_year_short}/{sequence}",
            sequence_padding=4,
        ),
        actor,
    )

    assert (
        service.preview_number(rule.id, firm_id=firm.id, document_date=date(2026, 8, 1))
        == "T/26-27/0001"
    )


def test_a_typed_gst_number_is_held_to_the_limit_too() -> None:
    """The one way past the series check is closed as well."""
    session, firm, actor = _setup()
    documents = _Invoices(session)
    documents.series(firm.id, actor).manual_allowed = True
    session.commit()

    with pytest.raises(ValidationError, match="at most 16"):
        documents.typed(firm.id, actor, "SI/2026-2027/000123")
    assert documents.typed(firm.id, actor, "OLD/2026/123") == "OLD/2026/123"


def test_a_non_gst_series_may_be_as_long_as_the_firm_likes() -> None:
    """Orders are not judged."""
    session, firm, actor = _setup()
    series = _Orders(session).series(firm.id, actor)

    rule = DocumentFrameworkService(session).create_numbering_rule(
        firm.id,
        DocumentNumberingRuleCreate(
            document_type_id=series.document_type_id,
            code="VERY_LONG",
            name="Very long",
            prefix="SALESORDER",
            include_financial_year=True,
        ),
        actor,
    )
    assert rule.id is not None
