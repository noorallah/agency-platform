"""Build what the Invoice Registration Portal is sent, and refuse what it would.

This is the part that matters and the part no portal is needed to get right.
The portal rejects on the payload it received, so the most useful thing this
module does is **refuse locally, naming the field**, rather than send a
document that comes back with a numeric error code somebody has to look up.

Everything here is derived from the invoice as it was approved. Nothing is
re-read from a master: a GSTIN corrected next month must not change what was
registered for a supply made today, which is the same rule that stops an
invoice re-reading a customer's discount.
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.firm_metadata import FirmMetadataReader
from app.core.exceptions import ValidationError
from app.core.utils.money import ZERO, quantize_money
from app.customers.models import Customer
from app.products.models import Product
from app.sales_invoice.models import (
    SalesInvoice,
    SalesInvoiceLine,
    SalesInvoiceLineTax,
)
from app.tax.services.gst_buckets import TaxComponent, split_components

#: The components the portal wants separated. A firm's tax framework may name
#: them anything; these are the codes the return is filed under, matched on the
#: component code the invoice line actually carried.
_CGST = "CGST"
_SGST = "SGST"
_IGST = "IGST"
_CESS = "CESS"


def _gstin(value: str | None) -> str | None:
    """Return a GSTIN stripped of spacing, or None where there is none."""
    token = (value or "").strip().upper()
    return token or None


def _state_code(gstin: str | None) -> str | None:
    """Return the state code a GSTIN begins with.

    The first two digits of a GSTIN are the state, which is what decides
    whether a supply is intra-state or inter-state -- and therefore whether it
    carries CGST and SGST or IGST. Reading it off the number rather than off
    an address field means the two can never disagree.
    """
    if gstin is None or len(gstin) < 2 or not gstin[:2].isdigit():
        return None
    return gstin[:2]


class EInvoicePayloadBuilder:
    """Turn an approved sales invoice into the portal's request body."""

    def __init__(self, session: Session) -> None:
        """Bind the builder to the request unit of work."""
        self._session = session
        # `firms` lives only in the platform schema, so a firm-owned service
        # reading it on the request session raises `relation
        # "<firm schema>.firms" does not exist` for every firm outside the
        # platform store. This repo has hit that seven times; the reader is
        # the one way to ask.
        self._firms = FirmMetadataReader(session)

    def build(self, invoice: SalesInvoice, *, firm_id: UUID) -> dict[str, object]:
        """Return the payload for one invoice.

        Args:
            invoice: The approved invoice to register.
            firm_id: The owning firm.

        Returns:
            The request body, as nested dictionaries of plain values.

        Raises:
            ValidationError: If the invoice is missing something the portal
                requires, naming the field rather than leaving a numeric code
                to be looked up.

        """
        problems: list[str] = []
        firm = self._firms.get(firm_id)
        customer = self._session.scalar(
            select(Customer).where(Customer.id == invoice.customer_id)
        )
        seller_gstin = _gstin(firm.gst_number)
        buyer_gstin = _gstin(getattr(customer, "gst_number", None))
        if seller_gstin is None:
            problems.append("the firm has no GST number")
        if buyer_gstin is None:
            problems.append("the customer has no GST number")
        if invoice.status not in {"APPROVED", "CLOSED"}:
            problems.append("the invoice is not approved")

        lines = list(
            self._session.scalars(
                select(SalesInvoiceLine)
                .where(
                    SalesInvoiceLine.sales_invoice_id == invoice.id,
                    SalesInvoiceLine.is_deleted.is_(False),
                )
                .order_by(SalesInvoiceLine.line_number.asc())
            ).all()
        )
        if not lines:
            problems.append("the invoice has no lines")

        products = {
            row.id: row
            for row in self._session.scalars(
                select(Product).where(
                    Product.id.in_([line.product_id for line in lines] or [None])
                )
            ).all()
        }
        taxes = self._taxes_by_line([line.id for line in lines])

        item_list: list[dict[str, object]] = []
        totals = {
            "taxable": ZERO,
            _CGST: ZERO,
            _SGST: ZERO,
            _IGST: ZERO,
            _CESS: ZERO,
        }
        for line in lines:
            product = products.get(line.product_id)
            hsn = (getattr(product, "hsn_sac", None) or "").strip()
            if not hsn:
                name = getattr(product, "name", "a product")
                problems.append(f"{name} has no HSN or SAC code")
            # Freight and the line's own charges are both inside the taxable
            # value: each is ancillary to the supply and taxed with the goods,
            # so a payload leaving either out registers less than the invoice
            # charged tax on. `charges_amount` was missing until the
            # 2026-09-03 review -- freight was added when #191 moved it inside
            # the base, and the line charges were never added at all.
            other_charges = quantize_money(
                Decimal(str(line.charges_amount)) + Decimal(str(line.freight_amount))
            )
            taxable = quantize_money(
                Decimal(str(line.gross_amount))
                - Decimal(str(line.discount_amount))
                - Decimal(str(line.bill_discount_amount))
                + other_charges
            )
            split = split_components(
                [
                    TaxComponent(
                        code=component.component_code,
                        percentage=Decimal(str(component.percentage)),
                        amount=Decimal(str(component.amount)),
                    )
                    for component in taxes.get(line.id, [])
                ]
            )
            item_list.append(
                {
                    "SlNo": str(line.line_number),
                    "PrdDesc": str(
                        line.description or getattr(product, "name", "") or ""
                    )[:300],
                    "IsServc": "N",
                    "HsnCd": hsn,
                    "Qty": float(line.current_invoice_quantity),
                    # Free goods are stated so the consignment reconciles, and
                    # are outside the taxable value -- the same rule the bill
                    # itself follows.
                    "FreeQty": float(line.free_quantity),
                    "UnitPrice": float(line.unit_price),
                    "TotAmt": float(quantize_money(Decimal(str(line.gross_amount)))),
                    "Discount": float(
                        quantize_money(
                            Decimal(str(line.discount_amount))
                            + Decimal(str(line.bill_discount_amount))
                        )
                    ),
                    # The portal has a field for it, and it is part of the
                    # assessable value above rather than an addition to it.
                    "OthChrg": float(other_charges),
                    "AssAmt": float(taxable),
                    "GstRt": float(split.rate),
                    "CgstAmt": float(split.cgst),
                    "SgstAmt": float(split.sgst),
                    "IgstAmt": float(split.igst),
                    "CesAmt": float(split.cess),
                    "TotItemVal": float(quantize_money(taxable + split.total)),
                }
            )
            totals["taxable"] += taxable
            totals[_CGST] += split.cgst
            totals[_SGST] += split.sgst
            totals[_IGST] += split.igst
            totals[_CESS] += split.cess

        if problems:
            raise ValidationError(
                "This invoice cannot be registered yet: " + "; ".join(problems) + "."
            )

        seller_state = _state_code(seller_gstin)
        buyer_state = _state_code(buyer_gstin)
        # Intra-state supplies carry CGST and SGST, inter-state carries IGST.
        # Read off the GSTINs rather than an address, so the two can never
        # disagree about the same supply.
        interstate = seller_state != buyer_state
        if interstate and totals[_IGST] == ZERO and totals[_CGST] > ZERO:
            raise ValidationError(
                "This is an inter-state supply but the invoice charged CGST "
                "and SGST. Correct the tax before registering it."
            )
        if not interstate and totals[_IGST] > ZERO:
            raise ValidationError(
                "This is an intra-state supply but the invoice charged IGST. "
                "Correct the tax before registering it."
            )

        return {
            "Version": "1.1",
            "TranDtls": {
                "TaxSch": "GST",
                "SupTyp": "B2B",
                "RegRev": "N",
                "IgstOnIntra": "N",
            },
            "DocDtls": {
                "Typ": "INV",
                "No": invoice.invoice_number,
                "Dt": invoice.invoice_date.strftime("%d/%m/%Y"),
            },
            "SellerDtls": {
                "Gstin": seller_gstin,
                "LglNm": firm.name or "",
                "Stcd": seller_state,
            },
            "BuyerDtls": {
                "Gstin": buyer_gstin,
                "LglNm": getattr(customer, "name", ""),
                "Pos": buyer_state,
                "Stcd": buyer_state,
            },
            "ItemList": item_list,
            "ValDtls": {
                "AssVal": float(quantize_money(totals["taxable"])),
                "CgstVal": float(quantize_money(totals[_CGST])),
                "SgstVal": float(quantize_money(totals[_SGST])),
                "IgstVal": float(quantize_money(totals[_IGST])),
                "CesVal": float(quantize_money(totals[_CESS])),
                "TotInvVal": float(quantize_money(Decimal(str(invoice.grand_total)))),
            },
        }

    def _taxes_by_line(
        self, line_ids: list[UUID]
    ) -> dict[UUID, list[SalesInvoiceLineTax]]:
        """Return each line's tax components, keyed by line."""
        if not line_ids:
            return {}
        grouped: dict[UUID, list[SalesInvoiceLineTax]] = {}
        for row in self._session.scalars(
            select(SalesInvoiceLineTax).where(
                SalesInvoiceLineTax.sales_invoice_line_id.in_(line_ids),
                SalesInvoiceLineTax.is_deleted.is_(False),
            )
        ).all():
            grouped.setdefault(row.sales_invoice_line_id, []).append(row)
        return grouped
