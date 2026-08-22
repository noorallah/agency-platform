"""Turn a stored purchase order into the document a supplier is sent.

The same renderer that draws a sales invoice, given an order's shape: a
purchase order is placed with a supplier and delivered to a warehouse, and it
carries no place of supply, no reverse-charge declaration and no HSN-wise tax
summary, because it charges nobody -- it asks.

The template it reads is the firm's own, under `PURCHASE_ORDER`, so a firm's
orders can look like its bills without either being able to change what a tax
invoice must state.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.branches.models import Warehouse
from app.common.firm_metadata import platform_reader
from app.core.exceptions import ResourceNotFoundError
from app.document_framework.models import DocumentPrintTemplate
from app.firms.models import Firm
from app.products.models import Product
from app.purchase.models import PurchaseOrder, PurchaseOrderLine
from app.sales_invoice.services.invoice_pdf import (
    InvoiceDocument,
    InvoiceLineBlock,
    InvoicePdfRenderer,
    PartyBlock,
    TemplateSettings,
)
from app.uom.models import Uom
from app.vendors.models import Vendor

ZERO = Decimal("0")
DOCUMENT_TYPE = "PURCHASE_ORDER"
#: A purchase order is not a tax invoice, so its default banner is its own.
DEFAULT_TITLE = "PURCHASE ORDER"


class PurchaseOrderPrintService:
    """Render one purchase order, with the firm's template around it."""

    def __init__(self, session: Session) -> None:
        """Keep the tenant session the order lives on."""
        self._session = session

    def render(self, order_id: UUID, *, firm_scope: UUID) -> tuple[bytes, str]:
        """Return the PDF bytes and the filename to offer them under."""
        order = self._session.scalar(
            select(PurchaseOrder).where(
                PurchaseOrder.id == order_id,
                PurchaseOrder.firm_id == firm_scope,
                PurchaseOrder.is_deleted.is_(False),
            )
        )
        if order is None:
            raise ResourceNotFoundError("Purchase order not found.")

        template = self._template(firm_scope)
        document = self._document(order, firm_scope=firm_scope)
        pdf = InvoicePdfRenderer(template).render(document)
        safe = order.po_number.replace("/", "-").replace(" ", "-")
        return pdf, f"{safe}.pdf"

    # ------------------------------------------------------------------
    def _template(self, firm_scope: UUID) -> TemplateSettings:
        """Return the firm's order template, or the platform default."""
        row = self._session.scalar(
            select(DocumentPrintTemplate).where(
                DocumentPrintTemplate.firm_id == firm_scope,
                DocumentPrintTemplate.document_type == DOCUMENT_TYPE,
                DocumentPrintTemplate.is_deleted.is_(False),
            )
        )
        if row is None:
            return TemplateSettings(
                title_text=DEFAULT_TITLE,
                # An order asks for goods; it certifies nothing.
                declaration=None,
                show_bank_details=False,
            )
        return TemplateSettings(
            title_text=row.title_text,
            accent_color=row.accent_color,
            header_note=row.header_note,
            show_bank_details=row.show_bank_details,
            bank_details=row.bank_details,
            terms=row.terms,
            declaration=row.declaration,
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

    def _document(self, order: PurchaseOrder, *, firm_scope: UUID) -> InvoiceDocument:
        """Gather the parties, lines and figures the order states."""
        lines = list(
            self._session.scalars(
                select(PurchaseOrderLine)
                .where(
                    PurchaseOrderLine.purchase_order_id == order.id,
                    PurchaseOrderLine.is_deleted.is_(False),
                )
                .order_by(PurchaseOrderLine.line_number.asc())
            ).all()
        )
        products = {
            product.id: product
            for product in self._session.scalars(
                select(Product).where(
                    Product.id.in_([line.product_id for line in lines] or [None])
                )
            )
        }
        units = {
            unit.id: unit
            for unit in self._session.scalars(
                select(Uom).where(
                    Uom.id.in_(
                        [line.purchase_uom_id for line in lines if line.purchase_uom_id]
                        or [None]
                    )
                )
            )
        }

        printed = [
            InvoiceLineBlock(
                number=line.line_number,
                description=(
                    line.description
                    or (
                        products[line.product_id].name
                        if line.product_id in products
                        else ""
                    )
                ),
                hsn=(
                    products[line.product_id].hsn_sac
                    if line.product_id in products
                    else None
                ),
                quantity=line.ordered_quantity,
                uom=(
                    units[line.purchase_uom_id].code
                    if line.purchase_uom_id in units
                    else None
                ),
                rate=line.unit_price,
                discount=line.discount_amount,
                taxable=self._taxable(line),
                total=line.net_amount,
            )
            for line in lines
        ]

        references: list[tuple[str, str]] = []
        if order.expected_delivery_date:
            references.append(
                ("Expected", order.expected_delivery_date.strftime("%d %b %Y"))
            )
        if order.payment_terms:
            references.append(("Payment terms", order.payment_terms))
        if order.delivery_terms:
            references.append(("Delivery terms", order.delivery_terms))

        return InvoiceDocument(
            number=order.po_number,
            date=order.purchase_date.strftime("%d %b %Y"),
            due_date=None,
            place_of_supply=None,
            reverse_charge=False,
            seller=self._firm(firm_scope),
            buyer=self._vendor(order),
            ship_to=self._warehouse(order),
            lines=tuple(printed),
            taxable_total=order.subtotal,
            tax_total=order.tax_total,
            charges=order.header_discount_amount * -1,
            round_off=order.round_off,
            grand_total=order.grand_total,
            references=tuple(references),
            # An order is placed, not billed.
            party_labels=("SUPPLIER", "DELIVER TO"),
            show_tax_summary=False,
            show_supply_terms=False,
            number_label="Order no.",
            date_label="Order date",
            words_label="ORDER VALUE, IN WORDS",
        )

    @staticmethod
    def _taxable(line: PurchaseOrderLine) -> Decimal:
        """Return the line's value before tax."""
        return line.net_amount - line.tax_amount

    def _firm(self, firm_scope: UUID) -> PartyBlock:
        """Return the ordering firm, read from the platform store.

        `firms` lives only in the platform schema, so a tenant session cannot
        see it -- `platform_reader` is the documented answer to that.
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

    def _vendor(self, order: PurchaseOrder) -> PartyBlock:
        """Return the supplier the order is placed with."""
        vendor = self._session.get(Vendor, order.vendor_id)
        if vendor is None:
            return PartyBlock(name="", address_lines=[])
        lines = [part for part in (order.vendor_address, order.vendor_contact) if part]
        return PartyBlock(
            name=vendor.display_name or vendor.name,
            address_lines=lines,
            gstin=vendor.gstin,
            pan=vendor.pan,
            contact=vendor.phone,
        )

    def _warehouse(self, order: PurchaseOrder) -> PartyBlock | None:
        """Return where the goods are to be delivered."""
        warehouse = self._session.get(Warehouse, order.warehouse_id)
        if warehouse is None:
            return None
        # A warehouse holds geography *keys*, not text -- `geo_cities` and its
        # siblings are the masters. Only the street lines are its own.
        address = [warehouse.address_line1, warehouse.address_line2]
        return PartyBlock(
            name=warehouse.name,
            address_lines=[line for line in address if line],
        )
