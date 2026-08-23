"""The parts every printed document needs, in one place.

`purchase_print_service` and `invoice_print_service` each carried their own
copy of "read the firm's template" and "describe the firm as a party block",
differing only in the defaults a document with no configured template falls
back to. Adding a delivery challan, a credit note and a quotation would have
made that four copies of each, which is how `transactional_document_service`
came to exist for the services one layer down.

Nothing here decides what a document *says*. It reads the template a firm
saved, and it names the firm — both of which are the same question whatever is
being printed.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.firm_metadata import platform_reader
from app.customers.models import Customer, CustomerAddress
from app.document_framework.models import DocumentPrintTemplate
from app.firms.models import Firm
from app.sales_invoice.services.invoice_pdf import PartyBlock, TemplateSettings


def load_template(
    session: Session,
    *,
    firm_scope: UUID,
    document_type: str,
    fallback: TemplateSettings | None = None,
) -> TemplateSettings:
    """Return the firm's template for one document type.

    Args:
        session: The tenant session the template lives on.
        firm_scope: Whose template to read.
        document_type: `SALES_INVOICE`, `DELIVERY_NOTE`, and so on.
        fallback: What a firm that has configured nothing gets. A tax invoice
            wants the full default; an order or a challan charges nobody and
            wants neither a bank block nor a certification.

    Returns:
        The saved settings, or the fallback where the firm has saved none.

    """
    row = session.scalar(
        select(DocumentPrintTemplate).where(
            DocumentPrintTemplate.firm_id == firm_scope,
            DocumentPrintTemplate.document_type == document_type,
            DocumentPrintTemplate.is_deleted.is_(False),
        )
    )
    if row is None:
        return fallback or TemplateSettings()
    # `declaration` falls back per field rather than per row: a firm that
    # cleared it on a bill still needs the statutory sentence, which is why
    # the invoice has always read it this way.
    default = fallback or TemplateSettings()
    return TemplateSettings(
        title_text=row.title_text,
        accent_color=row.accent_color,
        header_note=row.header_note,
        show_bank_details=row.show_bank_details,
        bank_details=row.bank_details,
        terms=row.terms,
        declaration=row.declaration or default.declaration,
        jurisdiction=row.jurisdiction,
        footer_note=row.footer_note,
        signatory_text=row.signatory_text,
        show_discount_column=row.show_discount_column,
        show_batch_column=row.show_batch_column,
        show_expiry_column=row.show_expiry_column,
        copy_labels=tuple(row.copy_labels or ()),
        page_size=row.page_size,
        margin_mm=row.margin_mm,
    )


def firm_party(firm_scope: UUID) -> PartyBlock:
    """Describe the firm as a party on a printed document.

    Read through `platform_reader` because `firms` exists only in the platform
    schema: a tenant session running `SET search_path` to a firm store cannot
    see it, and asking anyway raises `UndefinedTable`.
    """
    with platform_reader() as platform:
        firm = platform.get(Firm, firm_scope)
        if firm is None:
            return PartyBlock(name="", address_lines=[])
        address = [
            firm.address_line1,
            ", ".join(
                part for part in (firm.city, firm.state, firm.postal_code) if part
            ),
            firm.country,
        ]
        contact = " · ".join(
            part for part in (firm.contact_phone, firm.contact_email) if part
        )
        return PartyBlock(
            name=firm.name,
            address_lines=[line for line in address if line],
            gstin=firm.gst_number,
            pan=firm.pan_number,
            state=firm.state,
            contact=contact or None,
        )


def customer_party(session: Session, customer_id: UUID, kind: str) -> PartyBlock | None:
    """Describe a customer as one side of a document.

    Args:
        session: The tenant session the customer lives on.
        customer_id: Whose block to build.
        kind: `BILLING` or `SHIPPING` — the same customer reads differently
            depending on which address the document is speaking to.

    Returns:
        The block, or None where the customer has been removed.

    """
    customer = session.get(Customer, customer_id)
    if customer is None:
        return None
    address = session.scalar(
        select(CustomerAddress)
        .where(
            CustomerAddress.customer_id == customer_id,
            CustomerAddress.address_type == kind,
            CustomerAddress.is_deleted.is_(False),
        )
        .limit(1)
    )
    lines: list[str] = []
    state: str | None = None
    if address is not None:
        lines = [
            part
            for part in (
                address.address_line1,
                address.address_line2,
                ", ".join(
                    piece
                    for piece in (address.city, address.state, address.postal_code)
                    if piece
                ),
            )
            if part
        ]
        state = address.state
    return PartyBlock(
        name=customer.display_name or customer.name,
        address_lines=lines,
        gstin=customer.gst_number,
        pan=customer.pan_number,
        state=state,
        contact=customer.phone,
    )
