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

import re
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.branches.services.registration import BranchRegistration
from app.common.firm_metadata import FirmMetadataReader
from app.core.exceptions import ValidationError
from app.core.utils.money import ZERO, quantize_ledger, quantize_money
from app.customers.gst_registration import effective_type
from app.customers.models import Customer
from app.products.models import Product
from app.sales_invoice.models import (
    SalesInvoice,
    SalesInvoiceCharge,
    SalesInvoiceLine,
    SalesInvoiceLineTax,
)
from app.tax.services.gst_buckets import (
    GstBuckets,
    TaxComponent,
    settle_to_ledger,
    split_components,
)
from app.tax.services.place_of_supply import gst_state_code

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


#: The state code the portal uses for a place of supply outside India.
_FOREIGN = "96"
#: What the portal takes in place of a GSTIN for a buyer who has none -- an
#: overseas buyer (NIC IRP schema 1.1, BuyerDtls.Gstin).
_UNREGISTERED = "URP"

_POS_CODE = re.compile(r"\((\d{2})\)\s*$")


def _place_of_supply_code(label: str | None) -> str | None:
    """Return the state code the invoice's stored place of supply names.

    The invoice keeps it as ``Karnataka (29)`` since D-CMP-15 -- the state the
    tax was charged by. Older invoices keep a bare code or state name, which
    is read the way the tax engine reads one.
    """
    text = (label or "").strip()
    match = _POS_CODE.search(text)
    if match:
        return match.group(1)
    if len(text) == 2 and text.isdigit():
        return text
    return gst_state_code(text) if text else None


def _paise(value: Decimal | int | str) -> float:
    """Return an amount at two decimals, which is all the portal accepts."""
    return float(quantize_ledger(Decimal(str(value))))


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


def _supply_type(*, export: bool, igst: Decimal, gst_type: str = "REGULAR") -> str:
    """Return the portal's supply type for the document.

    An export is EXPWP where IGST was paid on it and EXPWOP where it went
    under a bond or LUT, which is what the tax the bill charged says. A buyer
    in an SEZ is SEZWP or SEZWOP by its registration type, and a deemed export
    DEXP (``customers.gst_registration_type``, backlog 75 row 2); everything
    else is B2B.
    """
    if export or gst_type == "OVERSEAS":
        return "EXPWP" if igst > ZERO else "EXPWOP"
    if gst_type == "SEZ_WITH_PAYMENT":
        return "SEZWP"
    if gst_type == "SEZ_WITHOUT_PAYMENT":
        return "SEZWOP"
    if gst_type == "DEEMED_EXPORT":
        return "DEXP"
    return "B2B"


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
        # The branch's own GSTIN where it has one (STK-2), else the firm's.
        seller_gstin = _gstin(
            BranchRegistration(self._session).own_gstin(invoice.branch_id)
            or firm.gst_number
        )
        buyer_gstin = _gstin(getattr(customer, "gst_number", None))
        # The place of supply is the document's, as it was charged -- not the
        # buyer's GSTIN, which names where the buyer is registered and not
        # where the goods went (D-CMP-13).
        pos = _place_of_supply_code(invoice.place_of_supply) or _state_code(buyer_gstin)
        export = pos == _FOREIGN
        if seller_gstin is None:
            problems.append("the firm has no GST number")
        if buyer_gstin is None and not export:
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
        # The one answer the printed bill gives for each line's quantity and
        # rate. Imported here: the print service reads this module's stamp.
        from app.sales_invoice.services.invoice_print_service import (
            stated_invoice_lines,
        )

        stated = stated_invoice_lines(self._session, lines, products)

        item_list: list[dict[str, object]] = []
        splits: list[GstBuckets] = []
        taxables: list[Decimal] = []
        totals = {
            "taxable": ZERO,
            _CGST: ZERO,
            _SGST: ZERO,
            _IGST: ZERO,
            _CESS: ZERO,
        }
        for line in lines:
            product = products.get(line.product_id)
            # The code the line was billed under (D-CMP-22), else the
            # product's for a line written before lines kept one.
            hsn = (
                getattr(line, "hsn_sac", None)
                or getattr(product, "hsn_sac", None)
                or ""
            ).strip()
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
                    # As the printed bill states the line -- 24 at 100.00
                    # for a bill typed 24 PIECE of a note of 2 BOX, not the
                    # 2 at 1,200.00 the row stores (D-PRC-40).
                    "Qty": float(stated[line.id].quantity),
                    # Free goods are stated so the consignment reconciles, and
                    # are outside the taxable value -- the same rule the bill
                    # itself follows.
                    "FreeQty": float(stated[line.id].free_quantity),
                    # Three decimals for a price, two for every amount: the
                    # schema's own limits (D-CMP-13 found four going out).
                    "UnitPrice": float(
                        Decimal(str(stated[line.id].rate)).quantize(Decimal("0.001"))
                    ),
                    "TotAmt": _paise(line.gross_amount),
                    "Discount": _paise(
                        Decimal(str(line.discount_amount))
                        + Decimal(str(line.bill_discount_amount))
                    ),
                    # The portal has a field for it, and it is part of the
                    # assessable value above rather than an addition to it.
                    "OthChrg": _paise(other_charges),
                    "AssAmt": _paise(taxable),
                    "GstRt": float(split.rate),
                }
            )
            splits.append(split)
            taxables.append(taxable)
            # The sum of what each item declares, so AssVal is exactly the
            # total of the AssAmt the portal adds up.
            totals["taxable"] += quantize_ledger(taxable)

        # A charge on the bill taxed at a rate of its own (SG-4) is an item
        # of the supply -- a service under its SAC -- or the items would not
        # add up to the invoice. One outside GST altogether (it names no tax
        # profile) is an other charge of the document instead.
        outside_gst = ZERO
        serial = max((line.line_number for line in lines), default=0)
        for charge in self._session.scalars(
            select(SalesInvoiceCharge)
            .where(
                SalesInvoiceCharge.sales_invoice_id == invoice.id,
                SalesInvoiceCharge.is_deleted.is_(False),
            )
            .order_by(SalesInvoiceCharge.sequence.asc())
        ):
            amount = quantize_money(Decimal(str(charge.amount)))
            if amount == ZERO:
                continue
            if charge.tax_profile_id is None:
                outside_gst += amount
                continue
            code = (charge.hsn_sac or "").strip()
            if not code:
                problems.append(f"the charge {charge.name} has no SAC code")
            serial += 1
            split = GstBuckets(
                cgst=Decimal(str(charge.cgst_amount)),
                sgst=Decimal(str(charge.sgst_amount)),
                igst=Decimal(str(charge.igst_amount)),
                cess=Decimal(str(charge.cess_amount)),
                rate=Decimal(str(charge.tax_rate_percent)),
            )
            item_list.append(
                {
                    "SlNo": str(serial),
                    "PrdDesc": charge.name[:300],
                    "IsServc": "Y",
                    "HsnCd": code,
                    "Qty": 1.0,
                    "FreeQty": 0.0,
                    "UnitPrice": float(amount.quantize(Decimal("0.001"))),
                    "TotAmt": _paise(amount),
                    "Discount": 0.0,
                    "OthChrg": 0.0,
                    "AssAmt": _paise(amount),
                    "GstRt": float(split.rate),
                }
            )
            splits.append(split)
            taxables.append(amount)
            totals["taxable"] += quantize_ledger(amount)

        # Registered at paise, adding up to what the journal credited: the
        # tax is rounded once as the invoice's sum and the odd paisa put on
        # the last component, rather than each bucket rounded on its own
        # (D-CMP-4). What is registered, filed and posted are one figure.
        for item, taxable, filed in zip(
            item_list, taxables, settle_to_ledger(splits), strict=True
        ):
            item["CgstAmt"] = float(filed.cgst)
            item["SgstAmt"] = float(filed.sgst)
            item["IgstAmt"] = float(filed.igst)
            item["CesAmt"] = float(filed.cess)
            item["TotItemVal"] = float(quantize_ledger(taxable) + filed.total)
            totals[_CGST] += filed.cgst
            totals[_SGST] += filed.sgst
            totals[_IGST] += filed.igst
            totals[_CESS] += filed.cess

        if problems:
            raise ValidationError(
                "This invoice cannot be registered yet: " + "; ".join(problems) + "."
            )

        seller_state = _state_code(seller_gstin)
        buyer_state = _FOREIGN if export else _state_code(buyer_gstin)
        # Intra-state supplies carry CGST and SGST, inter-state carries IGST,
        # and which one it is turns on the place of supply (IGST Act s.7, 8)
        # -- the seller's GSTIN against the state the document was charged by.
        interstate = seller_state != pos
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
                "SupTyp": _supply_type(
                    export=export,
                    igst=totals[_IGST],
                    gst_type=invoice.buyer_gst_registration_type
                    or effective_type(
                        getattr(customer, "gst_registration_type", None),
                        getattr(customer, "gst_number", None),
                    ),
                ),
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
                "Gstin": buyer_gstin if not export else _UNREGISTERED,
                "LglNm": getattr(customer, "name", ""),
                "Pos": pos,
                "Stcd": buyer_state,
            },
            "ItemList": item_list,
            "ValDtls": {
                "AssVal": _paise(totals["taxable"]),
                "CgstVal": float(quantize_ledger(totals[_CGST])),
                "SgstVal": float(quantize_ledger(totals[_SGST])),
                "IgstVal": float(quantize_ledger(totals[_IGST])),
                "CesVal": float(quantize_ledger(totals[_CESS])),
                # The bill discount is already inside each line's assessable
                # value, so nothing is taken off again here.
                "Discount": 0.0,
                # What the bill adds outside the tax, and the rounding that
                # brings it to a whole figure -- without them the parts did
                # not add up to TotInvVal (D-CMP-13).
                "OthChrg": _paise(
                    Decimal(str(invoice.additional_charges)) + outside_gst
                ),
                "RndOffAmt": _paise(invoice.round_off),
                "TotInvVal": _paise(invoice.grand_total),
            },
        }

    def build_note(
        self,
        *,
        kind: str,
        number: str,
        on: str,
        invoice: SalesInvoice,
        lines: list[Any],
        firm_id: UUID,
        references: tuple[SalesInvoice, ...] = (),
    ) -> dict[str, object]:
        """Return the payload for a credit note (CRN) or debit note (DBN).

        Backlog 77 row 4. A note corrects the invoice it names, so it carries
        that invoice's parties, place of supply and supply type -- built from
        the invoice and checked as it is -- with its own document details,
        its own lines and values, and the invoice it refers to. Each line's tax
        is split into heads in the proportion its invoice line was charged,
        which is how the note was posted.

        Raises:
            ValidationError: When the invoice cannot produce a valid payload, or
                a line names nothing to register.

        """
        base = self.build(invoice, firm_id=firm_id)
        invoice_lines = {
            row.id: row
            for row in self._session.scalars(
                select(SalesInvoiceLine).where(
                    SalesInvoiceLine.id.in_(
                        [line.sales_invoice_line_id for line in lines] or [None]
                    )
                )
            )
        }
        charged = self._taxes_by_line(list(invoice_lines))
        products = {
            row.id: row
            for row in self._session.scalars(
                select(Product).where(
                    Product.id.in_([line.product_id for line in lines] or [None])
                )
            )
        }
        items: list[dict[str, object]] = []
        splits: list[GstBuckets] = []
        taxables: list[Decimal] = []
        total_taxable = ZERO
        for index, line in enumerate(lines, start=1):
            source = invoice_lines.get(line.sales_invoice_line_id)
            product = products.get(line.product_id)
            hsn = (
                getattr(source, "hsn_sac", None)
                or getattr(product, "hsn_sac", None)
                or ""
            ).strip()
            taxable = quantize_money(Decimal(str(line.taxable_amount)))
            tax = Decimal(str(line.tax_amount))
            components = charged.get(line.sales_invoice_line_id, [])
            whole = sum((Decimal(str(item.amount)) for item in components), ZERO)
            split = split_components(
                [
                    TaxComponent(
                        code=item.component_code,
                        percentage=Decimal(str(item.percentage)),
                        amount=(
                            tax * Decimal(str(item.amount)) / whole
                            if whole > ZERO
                            else ZERO
                        ),
                    )
                    for item in components
                ]
            )
            quantity = Decimal(str(line.quantity or 0))
            items.append(
                {
                    "SlNo": str(index),
                    "PrdDesc": str(
                        line.description or getattr(product, "name", "") or ""
                    )[:300],
                    "IsServc": "N",
                    "HsnCd": hsn,
                    "Qty": float(quantity),
                    "UnitPrice": float(
                        (taxable / quantity if quantity > ZERO else taxable).quantize(
                            Decimal("0.001")
                        )
                    ),
                    "TotAmt": _paise(taxable),
                    "Discount": 0.0,
                    "AssAmt": _paise(taxable),
                    "GstRt": float(split.rate),
                }
            )
            splits.append(split)
            taxables.append(taxable)
            total_taxable += quantize_ledger(taxable)
        if not items:
            raise ValidationError("The note has no lines to register.")
        heads = {_CGST: ZERO, _SGST: ZERO, _IGST: ZERO, _CESS: ZERO}
        for item, taxable, filed in zip(
            items, taxables, settle_to_ledger(splits), strict=True
        ):
            item["CgstAmt"] = float(filed.cgst)
            item["SgstAmt"] = float(filed.sgst)
            item["IgstAmt"] = float(filed.igst)
            item["CesAmt"] = float(filed.cess)
            item["TotItemVal"] = float(quantize_ledger(taxable) + filed.total)
            heads[_CGST] += filed.cgst
            heads[_SGST] += filed.sgst
            heads[_IGST] += filed.igst
            heads[_CESS] += filed.cess
        tax_total = sum(heads.values(), ZERO)
        return base | {
            "DocDtls": {"Typ": kind, "No": number, "Dt": on},
            "ItemList": items,
            "ValDtls": {
                "AssVal": float(total_taxable),
                "CgstVal": float(quantize_ledger(heads[_CGST])),
                "SgstVal": float(quantize_ledger(heads[_SGST])),
                "IgstVal": float(quantize_ledger(heads[_IGST])),
                "CesVal": float(quantize_ledger(heads[_CESS])),
                "Discount": 0.0,
                "OthChrg": 0.0,
                "RndOffAmt": 0.0,
                "TotInvVal": float(total_taxable + tax_total),
            },
            # The invoices the note corrects, which the portal ties it to: a
            # sales return may cover several (D-TAX-2).
            "RefDtls": {
                "PrecDocDtls": [
                    {
                        "InvNo": each.invoice_number,
                        "InvDt": each.invoice_date.strftime("%d/%m/%Y"),
                    }
                    for each in (references or (invoice,))
                ]
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
