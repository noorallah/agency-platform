"""The document types a firm can save a print template for.

A leaf module on purpose. `print_support` imports the invoice PDF helpers,
and with them the whole sales-invoice service package; `print_template_service`
imported this set from there, which put the sales invoice inside the document
framework's own import and made a module that reached the framework first --
the delivery note, through batch/serial and inventory -- fail to import on a
fresh interpreter.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The document types a print service reads a template for. Each print
#: service's own ``DOCUMENT_TYPE`` must be in here; a test holds them together.
PRINTABLE_DOCUMENT_TYPES = frozenset(
    {
        "DELIVERY_NOTE",
        "PROFORMA_INVOICE",
        "PURCHASE_ORDER",
        "SALES_INVOICE",
        "SALES_ORDER",
        "SALES_QUOTATION",
        "SALES_RETURN",
    }
)


@dataclass(frozen=True)
class UnsavedTemplate:
    """What one document type prints with before its firm saves a template.

    The print service and the template read both take it from here, so a
    Print settings screen that saves back what it read cannot change how the
    firm's documents print (D-PRT-1: the read offered a bill no copies while
    the bill printed three, and offered a challan the tax invoice's title).
    """

    title_text: str = "TAX INVOICE"
    show_bank_details: bool = True
    #: A tax invoice certifies what it charges; an order or a challan does not.
    certifies: bool = True
    copy_labels: tuple[str, ...] = ()


#: By document type. A type missing here takes the tax invoice's defaults.
UNSAVED_TEMPLATES: dict[str, UnsavedTemplate] = {
    # CGST rule 48: the original for the recipient, the duplicate for the
    # transporter, the triplicate for the supplier (BL-31.14).
    "SALES_INVOICE": UnsavedTemplate(
        copy_labels=(
            "ORIGINAL FOR RECIPIENT",
            "DUPLICATE FOR TRANSPORTER",
            "TRIPLICATE FOR SUPPLIER",
        )
    ),
    # A challan collects nothing, so it carries no bank block and certifies
    # nothing about tax.
    "DELIVERY_NOTE": UnsavedTemplate(
        title_text="DELIVERY CHALLAN",
        show_bank_details=False,
        certifies=False,
        copy_labels=(
            "ORIGINAL FOR CONSIGNEE",
            "DUPLICATE FOR TRANSPORTER",
            "TRIPLICATE FOR CONSIGNOR",
        ),
    ),
    # The bank block stays: a proforma is what an advance is paid on.
    "PROFORMA_INVOICE": UnsavedTemplate(title_text="PROFORMA INVOICE", certifies=False),
    # An order asks for goods; it certifies nothing.
    "PURCHASE_ORDER": UnsavedTemplate(
        title_text="PURCHASE ORDER", show_bank_details=False, certifies=False
    ),
    # An offer collects nothing and certifies nothing.
    "SALES_QUOTATION": UnsavedTemplate(
        title_text="QUOTATION", show_bank_details=False, certifies=False
    ),
    # An order confirmation collects nothing and certifies nothing.
    "SALES_ORDER": UnsavedTemplate(
        title_text="ORDER CONFIRMATION", show_bank_details=False, certifies=False
    ),
    # Nothing is being collected, so no bank block.
    "SALES_RETURN": UnsavedTemplate(title_text="CREDIT NOTE", show_bank_details=False),
}


def unsaved_template(document_type: str) -> UnsavedTemplate:
    """Return what ``document_type`` prints with before a template is saved."""
    return UNSAVED_TEMPLATES.get(document_type.upper(), UnsavedTemplate())
