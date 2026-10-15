"""What Print settings reads for a firm that saved nothing is what it prints.

D-PRT-1: the template read answered every document type with the tax
invoice's defaults and no copies, while each print service fell back to its
own -- three labelled copies on a bill, a challan titled *DELIVERY CHALLAN*
with no bank block. A screen that saved back what it read changed the print.
Both now take the same table, and this holds them together.
"""

from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.document_framework.services import DocumentPrintTemplateService
from app.document_framework.services.print_support import (
    load_template,
    unsaved_fallback,
)
from app.document_framework.services.printable_types import PRINTABLE_DOCUMENT_TYPES


def _session() -> Session:
    """Return a session over every table, as the request sees them."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return Session(engine)


@pytest.mark.parametrize("document_type", sorted(PRINTABLE_DOCUMENT_TYPES))
def test_the_read_offers_what_the_document_prints_with(document_type: str) -> None:
    """Title, bank block, declaration and copies agree for every type."""
    session = _session()
    firm_id = uuid4()
    read = DocumentPrintTemplateService(session).get(document_type, firm_scope=firm_id)
    printed = load_template(
        session,
        firm_scope=firm_id,
        document_type=document_type,
        fallback=unsaved_fallback(document_type),
    )

    assert read.is_customised is False
    assert read.title_text == printed.title_text
    assert read.show_bank_details == printed.show_bank_details
    assert read.declaration == printed.declaration
    assert tuple(read.copy_labels) == printed.copy_labels


def test_a_bill_offers_its_three_copies() -> None:
    """The copies a tax invoice for goods prints with (CGST rule 48)."""
    read = DocumentPrintTemplateService(_session()).get(
        "SALES_INVOICE", firm_scope=uuid4()
    )
    assert read.copy_labels == [
        "ORIGINAL FOR RECIPIENT",
        "DUPLICATE FOR TRANSPORTER",
        "TRIPLICATE FOR SUPPLIER",
    ]


def test_a_challan_offers_its_own_title_and_no_bank_block() -> None:
    """A challan collects nothing and certifies nothing about tax."""
    read = DocumentPrintTemplateService(_session()).get(
        "DELIVERY_NOTE", firm_scope=uuid4()
    )
    assert read.title_text == "DELIVERY CHALLAN"
    assert read.show_bank_details is False
    assert read.declaration is None
