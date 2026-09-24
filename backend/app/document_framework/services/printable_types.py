"""The document types a firm can save a print template for.

A leaf module on purpose. `print_support` imports the invoice PDF helpers,
and with them the whole sales-invoice service package; `print_template_service`
imported this set from there, which put the sales invoice inside the document
framework's own import and made a module that reached the framework first --
the delivery note, through batch/serial and inventory -- fail to import on a
fresh interpreter.
"""

#: The document types a print service reads a template for. Each print
#: service's own ``DOCUMENT_TYPE`` must be in here; a test holds them together.
PRINTABLE_DOCUMENT_TYPES = frozenset(
    {
        "DELIVERY_NOTE",
        "PURCHASE_ORDER",
        "SALES_INVOICE",
        "SALES_QUOTATION",
        "SALES_RETURN",
    }
)
