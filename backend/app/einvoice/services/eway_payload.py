"""The e-way bill raised without an IRN (backlog 77 row 9).

An invoice registered on the e-invoice portal raises its e-way bill from the
IRN. One that is not -- the firm does not e-invoice, or the buyer is a
consumer -- and a delivery note no invoice bills yet (job work, goods on
approval, a van loaded before its sales) raise it from the document itself:
the portal's e-way bill schema carries the parties, the value and the goods.

**The supply type follows the challan's reason**, as the portal codes them:
a sale is *Supply* (1), a van or route sale *Line sales* (10), job work *Job
work* (4), and goods on approval, of unknown quantity or anything else
*Others* (8) with the reason written out.
"""

from collections.abc import Iterable
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.firm_metadata import FirmMetadataReader
from app.core.utils.money import ZERO, quantize_ledger
from app.customers.models import Customer
from app.products.models import Product

#: The portal's sub-supply codes, by challan reason.
SUB_SUPPLY: dict[str, tuple[str, str | None]] = {
    "SALE": ("1", None),
    "ROUTE_SALE": ("10", None),
    "JOB_WORK": ("4", None),
    "ON_APPROVAL": ("8", "Supply on approval"),
    "QUANTITY_UNKNOWN": ("8", "Quantity not known at removal"),
    "OTHER": ("8", "Other"),
}

#: The portal's word for a party with no GSTIN.
UNREGISTERED = "URP"


def _state(gstin: str | None) -> str | None:
    """Return the two-digit state code a GSTIN begins with."""
    text = (gstin or "").strip()
    return text[:2] if len(text) >= 2 and text[:2].isdigit() else None


def eway_payload(
    session: Session,
    *,
    firm_id: UUID,
    customer_id: UUID,
    doc_type: str,
    number: str,
    on: str,
    reason: str,
    reason_note: str | None,
    lines: Iterable[Any],
    quantity_of: str,
    total_value: Decimal,
    branch_id: UUID | None = None,
) -> dict[str, object]:
    """Return the e-way bill payload for one document, without an IRN.

    ``doc_type`` is ``INV`` for a bill or ``CHL`` for a delivery challan;
    ``quantity_of`` names the line attribute that holds what moves. The
    consignor is the GSTIN of the branch the goods leave (STK-2).
    """
    firm = FirmMetadataReader(session).get(firm_id)
    customer = session.scalar(select(Customer).where(Customer.id == customer_id))
    from app.branches.services.registration import BranchRegistration

    seller = BranchRegistration(session).own_gstin(branch_id) or (
        (getattr(firm, "gst_number", None) or "").strip().upper() or None
    )
    buyer = (getattr(customer, "gst_number", None) or "").strip().upper() or None
    rows = list(lines)
    products = {
        product.id: product
        for product in session.scalars(
            select(Product).where(
                Product.id.in_([line.product_id for line in rows] or [None])
            )
        )
    }
    items: list[dict[str, object]] = []
    taxable_total = tax_total = ZERO
    for line in rows:
        product = products.get(line.product_id)
        taxable = (
            Decimal(str(line.gross_amount or 0))
            - Decimal(str(line.discount_amount or 0))
            - Decimal(str(line.bill_discount_amount or 0))
        )
        tax = Decimal(str(line.tax_amount or 0))
        taxable_total += taxable
        tax_total += tax
        items.append(
            {
                "productName": getattr(product, "name", "") or "",
                "hsnCode": (
                    getattr(line, "hsn_sac", None)
                    or getattr(product, "hsn_sac", None)
                    or ""
                ),
                "quantity": float(Decimal(str(getattr(line, quantity_of) or 0))),
                "taxableAmount": float(quantize_ledger(taxable)),
                "taxAmount": float(quantize_ledger(tax)),
            }
        )
    sub_supply, description = SUB_SUPPLY.get(reason, SUB_SUPPLY["OTHER"])
    return {
        "supplyType": "O",
        "subSupplyType": sub_supply,
        "subSupplyDesc": reason_note or description,
        "docType": doc_type,
        "docNo": number,
        "docDate": on,
        "fromGstin": seller or UNREGISTERED,
        "fromStateCode": _state(seller),
        "toGstin": buyer or UNREGISTERED,
        "toTrdName": getattr(customer, "name", "") or "",
        "toStateCode": _state(buyer),
        "totalValue": float(quantize_ledger(taxable_total)),
        "totalTaxValue": float(quantize_ledger(tax_total)),
        "totInvValue": float(quantize_ledger(total_value)),
        "itemList": items,
    }
