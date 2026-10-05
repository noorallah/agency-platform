"""Requests for quotation, supplier quotations and the comparison (PG-8).

An RFQ asks several suppliers for their prices on a list of products. It is
typed as a DRAFT -- lines and invited suppliers -- and SENT, after which its
lines and suppliers are fixed and each supplier's quotation is entered: a rate,
a discount and a lead time per line. The comparison sets every supplier's
landed rate (the rate after its discount, before tax: tax is decided by the
product and the transaction, not by who quotes, so it would not separate
them) side by side, cheapest first, and marks the lowest. A person chooses a
quote per line; choosing one that is not the lowest needs a reason, which the
RFQ keeps. *Raise orders* turns the choices into one draft purchase order per
chosen supplier through the order's own staging path, every line at the
quoted rate and discount, and closes the RFQ -- all in one commit.
"""

from collections import defaultdict
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.common.firm_metadata import firm_today
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.document_framework.services.transactional_document_service import (
    DocumentStateSpec,
    DocumentTypeSpec,
    TransactionalDocumentService,
)
from app.purchase.models import PurchaseOrder
from app.purchase.models.requisition import PurchaseRequisition
from app.purchase.schemas import PurchaseOrderCreate
from app.rfq.models import (
    Rfq,
    RfqLine,
    RfqSupplier,
    SupplierQuotation,
    SupplierQuotationLine,
)
from app.rfq.repositories import RfqRepository
from app.rfq.schemas import (
    ComparisonLine,
    ComparisonQuote,
    RfqComparisonResponse,
    RfqCreate,
    RfqLineResponse,
    RfqLineWrite,
    RfqResponse,
    RfqSelectionsWrite,
    RfqSupplierResponse,
    RfqUpdate,
    SupplierQuotationLineResponse,
    SupplierQuotationResponse,
    SupplierQuotationWrite,
)
from app.vendors.models import Vendor

HUNDRED = Decimal("100")
RATE_SCALE = Decimal("0.0001")


def landed_rate(rate: Decimal, discount_percent: Decimal) -> Decimal:
    """Return the rate after the quoted discount, before tax."""
    return (rate * (HUNDRED - discount_percent) / HUNDRED).quantize(RATE_SCALE)


def _vendor_name(vendor: Vendor | None) -> str:
    """Return the name a supplier is shown under."""
    if vendor is None:
        return ""
    return vendor.display_name or vendor.name


class RfqService(TransactionalDocumentService):
    """Raise, send, quote, compare and order from RFQs."""

    DOCUMENT = DocumentTypeSpec(
        code="RFQ",
        name="Request for Quotation",
        description="Asking several suppliers for their prices.",
        category="PURCHASE",
        module="rfq",
        prefix="RFQ",
        rule_code="RFQ_DEFAULT",
        rule_name="Request for Quotation Default Numbering",
        states=(
            DocumentStateSpec("DRAFT", "Draft", 10, allows_edit=True),
            DocumentStateSpec("SENT", "Sent", 20),
            DocumentStateSpec("CLOSED", "Closed", 80, is_terminal=True),
            DocumentStateSpec("CANCELLED", "Cancelled", 90, is_terminal=True),
        ),
    )

    def __init__(self, session: Session) -> None:
        """Bind the service and its repository to a session it does not own."""
        super().__init__(session)
        self._rows = RfqRepository(self._session)

    # -- writing the RFQ ------------------------------------------------
    def create(self, data: RfqCreate, *, firm_id: UUID, actor_id: UUID) -> Rfq:
        """Raise a draft RFQ and commit."""
        row = self.stage_create(data, firm_id=firm_id, actor_id=actor_id)
        self._session.commit()
        return row

    def stage_create(
        self,
        data: RfqCreate,
        *,
        firm_id: UUID,
        actor_id: UUID,
        source_requisition_id: UUID | None = None,
    ) -> Rfq:
        """Raise a draft RFQ without committing."""
        _, rule = self._ensure_document_setup(firm_id=firm_id, actor_id=actor_id)
        branch_code, company_code = self._scope_codes(
            firm_id=firm_id, branch_id=data.branch_id
        )
        number = self._issue_number(
            rule,
            typed=None,
            number_column=Rfq.rfq_number,
            firm_id=firm_id,
            document_date=data.rfq_date,
            actor_id=actor_id,
            branch_code=branch_code,
            company_code=company_code,
        )
        row = Rfq(
            firm_id=firm_id,
            branch_id=data.branch_id,
            warehouse_id=data.warehouse_id,
            rfq_number=number,
            rfq_date=data.rfq_date,
            required_by=data.required_by,
            status="DRAFT",
            notes=data.notes,
            source_requisition_id=source_requisition_id,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._flush_or_conflict("RFQ number already exists in this firm.")
        self._write_lines(row, data.lines, actor_id=actor_id)
        self._write_suppliers(row, data.vendor_ids, actor_id=actor_id)
        self._audit("rfq.created", row, actor_id)
        return row

    def update(
        self, rfq_id: UUID, data: RfqUpdate, *, firm_id: UUID, actor_id: UUID
    ) -> Rfq:
        """Change a draft RFQ; a field left out is left alone.

        Raises:
            ValidationError: If the RFQ has been sent, closed or cancelled.

        """
        row = self.get(rfq_id, firm_id=firm_id)
        self._require(row, "DRAFT", "Only a draft RFQ can be changed.")
        values = data.model_dump(exclude_unset=True)
        for field in ("branch_id", "warehouse_id", "rfq_date"):
            if field in values and values[field] is None:
                raise ValidationError(f"{field} cannot be blank.")
        row.branch_id = values.get("branch_id", row.branch_id)
        row.warehouse_id = values.get("warehouse_id", row.warehouse_id)
        row.rfq_date = values.get("rfq_date", row.rfq_date)
        row.required_by = values.get("required_by", row.required_by)
        row.notes = values.get("notes", row.notes)
        row.updated_by = actor_id
        if "lines" in data.model_fields_set and data.lines is not None:
            self._write_lines(row, data.lines, actor_id=actor_id)
        if "vendor_ids" in data.model_fields_set and data.vendor_ids is not None:
            self._write_suppliers(row, data.vendor_ids, actor_id=actor_id)
        self._audit("rfq.updated", row, actor_id)
        self._session.commit()
        return row

    def create_from_requisition(
        self, requisition_id: UUID, *, firm_id: UUID, actor_id: UUID
    ) -> Rfq:
        """Start a draft RFQ from an approved requisition and commit.

        The requisition's lines become the RFQ's; the suppliers its lines name,
        and the preferred suppliers of its products, are invited.

        Raises:
            ValidationError: If the requisition is not approved, or an RFQ not
                cancelled was already started from it.

        """
        from app.purchase.services.requisitions import PurchaseRequisitionService

        requisitions = PurchaseRequisitionService(self._session)
        requisition = requisitions.get(requisition_id, firm_id=firm_id)
        if requisition.status != "APPROVED":
            raise ValidationError(
                "An RFQ is started only from an approved requisition."
            )
        existing = self._rows.live_rfq_for_requisition(requisition.id)
        if existing is not None:
            raise ValidationError(
                f"RFQ {existing.rfq_number} was already started from requisition "
                f"{requisition.requisition_number}."
            )
        lines = requisitions._lines(requisition.id)
        products = self._rows.products(line.product_id for line in lines)
        vendor_ids: list[UUID] = []
        for line in lines:
            product = products.get(line.product_id)
            for candidate in (
                line.vendor_id,
                product.preferred_vendor_id if product else None,
            ):
                if candidate is not None and candidate not in vendor_ids:
                    vendor_ids.append(candidate)
        row = self.stage_create(
            RfqCreate(
                branch_id=requisition.branch_id,
                warehouse_id=requisition.warehouse_id,
                rfq_date=firm_today(self._session, firm_id),
                required_by=requisition.needed_by,
                notes=f"From requisition {requisition.requisition_number}",
                lines=[
                    RfqLineWrite(
                        product_id=line.product_id,
                        quantity=line.quantity,
                        notes=line.remarks,
                    )
                    for line in lines
                ],
                vendor_ids=vendor_ids,
            ),
            firm_id=firm_id,
            actor_id=actor_id,
            source_requisition_id=requisition.id,
        )
        self._session.commit()
        return row

    # -- the lifecycle --------------------------------------------------
    def send(self, rfq_id: UUID, *, firm_id: UUID, actor_id: UUID) -> Rfq:
        """Send a draft RFQ: its lines and suppliers are fixed from here.

        Raises:
            ValidationError: If it is not a draft or invites nobody.

        """
        row = self.get(rfq_id, firm_id=firm_id)
        self._require(row, "DRAFT", "Only a draft RFQ can be sent.")
        if not self._rows.suppliers([row.id]).get(row.id):
            raise ValidationError("Invite at least one supplier before sending.")
        if not self._rows.lines([row.id]).get(row.id):
            raise ValidationError("Add at least one line before sending.")
        row.status = "SENT"
        row.sent_at = utc_now()
        row.sent_by = actor_id
        row.updated_by = actor_id
        self._audit("rfq.sent", row, actor_id)
        self._session.commit()
        return row

    def cancel(
        self, rfq_id: UUID, reason: str, *, firm_id: UUID, actor_id: UUID
    ) -> Rfq:
        """Call off a draft or sent RFQ.

        Raises:
            ValidationError: If it is closed or cancelled, or no reason is given.

        """
        row = self.get(rfq_id, firm_id=firm_id)
        if row.status not in ("DRAFT", "SENT"):
            raise ValidationError(f"A {row.status.lower()} RFQ cannot be cancelled.")
        if not reason.strip():
            raise ValidationError("Say why the RFQ is cancelled.")
        row.status = "CANCELLED"
        row.cancel_reason = reason.strip()
        row.updated_by = actor_id
        self._audit("rfq.cancelled", row, actor_id)
        self._session.commit()
        return row

    def close(self, rfq_id: UUID, *, firm_id: UUID, actor_id: UUID) -> Rfq:
        """Close a sent RFQ without raising any order."""
        row = self.get(rfq_id, firm_id=firm_id)
        self._require(row, "SENT", "Only a sent RFQ can be closed.")
        self._close(row, actor_id)
        self._session.commit()
        return row

    # -- quotations -----------------------------------------------------
    def save_quotation(
        self,
        rfq_id: UUID,
        vendor_id: UUID,
        data: SupplierQuotationWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> SupplierQuotation:
        """Enter or replace one invited supplier's quotation, and commit.

        Raises:
            ValidationError: If the RFQ is not sent, the supplier was not
                invited, or a line is not one of the RFQ's or is quoted twice.

        """
        row = self.get(rfq_id, firm_id=firm_id)
        if row.status != "SENT":
            raise ValidationError(
                f"A {row.status.lower()} RFQ takes no quotations; "
                "quotes are entered while it is sent."
            )
        invited = {s.vendor_id for s in self._rows.suppliers([row.id]).get(row.id, [])}
        if vendor_id not in invited:
            raise ValidationError("That supplier was not invited to quote on this RFQ.")
        rfq_lines = {
            line.id: line for line in self._rows.lines([row.id]).get(row.id, [])
        }
        seen: set[UUID] = set()
        for line in data.lines:
            if line.rfq_line_id not in rfq_lines:
                raise ValidationError(f"Line {line.rfq_line_id} is not on this RFQ.")
            if line.rfq_line_id in seen:
                raise ValidationError(
                    f"Line {rfq_lines[line.rfq_line_id].line_number} is quoted twice."
                )
            seen.add(line.rfq_line_id)
        quotation = self._rows.quotation_for(row.id, vendor_id)
        if quotation is None:
            quotation = SupplierQuotation(
                rfq_id=row.id,
                firm_id=row.firm_id,
                vendor_id=vendor_id,
                created_by=actor_id,
            )
            self._session.add(quotation)
        quotation.is_deleted = False
        quotation.deleted_at = None
        quotation.quote_ref = data.quote_ref
        quotation.quote_date = data.quote_date
        quotation.valid_until = data.valid_until
        quotation.notes = data.notes
        quotation.updated_by = actor_id
        self._session.flush()
        existing = {
            q.rfq_line_id: q
            for q in self._rows.quotation_lines(
                [quotation.id], include_deleted=True
            ).get(quotation.id, [])
        }
        for line in data.lines:
            current = existing.get(line.rfq_line_id)
            if current is None:
                current = SupplierQuotationLine(
                    quotation_id=quotation.id,
                    firm_id=row.firm_id,
                    rfq_line_id=line.rfq_line_id,
                    created_by=actor_id,
                )
                self._session.add(current)
            current.is_deleted = False
            current.deleted_at = None
            current.rate = line.rate
            current.discount_percent = line.discount_percent
            current.lead_time_days = line.lead_time_days
            current.notes = line.notes
            current.updated_by = actor_id
        dropped = {
            q.id
            for rfq_line_id, q in existing.items()
            if rfq_line_id not in seen and not q.is_deleted
        }
        for rfq_line_id, q in existing.items():
            if q.id in dropped:
                q.is_deleted = True
                q.deleted_at = utc_now()
                rfq_line = rfq_lines.get(rfq_line_id)
                if rfq_line and rfq_line.selected_quotation_line_id == q.id:
                    rfq_line.selected_quotation_line_id = None
                    rfq_line.selection_reason = None
        self._session.flush()
        record_audit(
            self._session,
            action="rfq.quotation_saved",
            entity_type="supplier_quotation",
            entity_id=quotation.id,
            actor_id=actor_id,
            firm_id=row.firm_id,
            after_data={
                "rfq_number": row.rfq_number,
                "vendor_id": str(vendor_id),
                "quote_ref": quotation.quote_ref,
                "lines": len(data.lines),
            },
        )
        self._session.commit()
        return quotation

    # -- comparison and choice ------------------------------------------
    def comparison(self, rfq_id: UUID, *, firm_id: UUID) -> RfqComparisonResponse:
        """Return every supplier's landed rate per line, cheapest first."""
        row = self.get(rfq_id, firm_id=firm_id)
        lines = self._rows.lines([row.id]).get(row.id, [])
        quotations = self._rows.quotations([row.id]).get(row.id, [])
        by_id = {q.id: q for q in quotations}
        quoted = self._rows.quotation_lines(by_id)
        products = self._rows.products(line.product_id for line in lines)
        vendors = self._rows.vendors(q.vendor_id for q in quotations)
        offers: dict[UUID, list[ComparisonQuote]] = defaultdict(list)
        for quotation_id, quote_lines in quoted.items():
            quotation = by_id[quotation_id]
            for q in quote_lines:
                offers[q.rfq_line_id].append(
                    ComparisonQuote(
                        quotation_id=quotation.id,
                        quotation_line_id=q.id,
                        vendor_id=quotation.vendor_id,
                        vendor_name=_vendor_name(vendors.get(quotation.vendor_id)),
                        rate=q.rate,
                        discount_percent=q.discount_percent,
                        landed_rate=landed_rate(q.rate, q.discount_percent),
                        lead_time_days=q.lead_time_days,
                        valid_until=quotation.valid_until,
                        notes=q.notes,
                        is_lowest=False,
                    )
                )
        result: list[ComparisonLine] = []
        for line in lines:
            quotes = sorted(
                offers.get(line.id, []),
                key=lambda o: (
                    o.landed_rate,
                    o.lead_time_days is None,
                    o.lead_time_days or 0,
                    o.vendor_name,
                ),
            )
            lowest = quotes[0].landed_rate if quotes else None
            for quote in quotes:
                quote.is_lowest = quote.landed_rate == lowest
            product = products.get(line.product_id)
            result.append(
                ComparisonLine(
                    rfq_line_id=line.id,
                    line_number=line.line_number,
                    product_id=line.product_id,
                    product_code=product.code if product else "",
                    product_name=product.name if product else "",
                    quantity=line.quantity,
                    uom_id=line.uom_id,
                    lowest_quotation_line_id=(
                        quotes[0].quotation_line_id if quotes else None
                    ),
                    selected_quotation_line_id=line.selected_quotation_line_id,
                    selection_reason=line.selection_reason,
                    quotes=quotes,
                )
            )
        return RfqComparisonResponse(
            rfq_id=row.id,
            rfq_number=row.rfq_number,
            status=row.status,
            version=row.version,
            lines=result,
        )

    def set_selections(
        self,
        rfq_id: UUID,
        data: RfqSelectionsWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> Rfq:
        """Replace the quote chosen per line; a line left out has none.

        Raises:
            ValidationError: If the RFQ is not sent, a choice names a quote for
                another line, a line is chosen twice, or a quote that is not
                the lowest is chosen without a reason.

        """
        row = self.get(rfq_id, firm_id=firm_id)
        self._require(row, "SENT", "Quotes are chosen only on a sent RFQ.")
        comparison = self.comparison(row.id, firm_id=firm_id)
        offers = {
            line.rfq_line_id: {q.quotation_line_id: q for q in line.quotes}
            for line in comparison.lines
        }
        numbers = {line.rfq_line_id: line.line_number for line in comparison.lines}
        chosen: dict[UUID, tuple[UUID, str | None]] = {}
        for pick in data.selections:
            if pick.rfq_line_id not in offers:
                raise ValidationError(f"Line {pick.rfq_line_id} is not on this RFQ.")
            number = numbers[pick.rfq_line_id]
            if pick.rfq_line_id in chosen:
                raise ValidationError(f"Line {number} is chosen twice.")
            quote = offers[pick.rfq_line_id].get(pick.quotation_line_id)
            if quote is None:
                raise ValidationError(
                    f"The quote chosen for line {number} is not a quote for that line."
                )
            reason = (pick.reason or "").strip() or None
            if not quote.is_lowest and reason is None:
                raise ValidationError(
                    f"Line {number}: say why {quote.vendor_name or 'this supplier'} "
                    "is chosen over the lowest quote."
                )
            chosen[pick.rfq_line_id] = (pick.quotation_line_id, reason)
        for line in self._rows.lines([row.id]).get(row.id, []):
            pick_for = chosen.get(line.id)
            line.selected_quotation_line_id = pick_for[0] if pick_for else None
            line.selection_reason = pick_for[1] if pick_for else None
            line.updated_by = actor_id
        row.updated_by = actor_id
        self._audit("rfq.selections_saved", row, actor_id, chosen=len(chosen))
        self._session.commit()
        return row

    def raise_orders(
        self, rfq_id: UUID, *, firm_id: UUID, actor_id: UUID
    ) -> list[PurchaseOrder]:
        """Raise one draft order per chosen supplier, close the RFQ, commit once.

        Each order line carries the quoted rate and discount; the order's
        reference is the RFQ number and its external reference the supplier's
        quote reference.

        Raises:
            ValidationError: If the RFQ is not sent, nothing is chosen, or a
                choice no longer stands (its quote changed and is no longer
                the lowest, and no reason was given).

        """
        from app.purchase.services import PurchaseService

        row = self.get(rfq_id, firm_id=firm_id)
        self._require(row, "SENT", "Orders are raised only from a sent RFQ.")
        comparison = self.comparison(row.id, firm_id=firm_id)
        lines = {line.id: line for line in self._rows.lines([row.id]).get(row.id, [])}
        grouped: dict[UUID, list[tuple[RfqLine, ComparisonQuote]]] = defaultdict(list)
        refs: dict[UUID, UUID] = {}
        for entry in comparison.lines:
            if entry.selected_quotation_line_id is None:
                continue
            quote = next(
                (
                    q
                    for q in entry.quotes
                    if q.quotation_line_id == entry.selected_quotation_line_id
                ),
                None,
            )
            if quote is None:
                raise ValidationError(
                    f"Line {entry.line_number}: the chosen quote is no longer there; "
                    "choose again."
                )
            if not quote.is_lowest and not entry.selection_reason:
                raise ValidationError(
                    f"Line {entry.line_number}: say why {quote.vendor_name} is "
                    "chosen over the lowest quote."
                )
            grouped[quote.vendor_id].append((lines[entry.rfq_line_id], quote))
            refs[quote.vendor_id] = quote.quotation_id
        if not grouped:
            raise ValidationError("Choose a quote for at least one line first.")
        quotations = {q.id: q for q in self._rows.quotations([row.id]).get(row.id, [])}
        suppliers = {
            s.vendor_id: s for s in self._rows.suppliers([row.id]).get(row.id, [])
        }
        orders = PurchaseService(self._session)
        raised: list[PurchaseOrder] = []
        for vendor_id, picks in grouped.items():
            quotation = quotations.get(refs[vendor_id])
            order = orders.stage_order(
                PurchaseOrderCreate.model_validate(
                    {
                        "branch_id": row.branch_id,
                        "warehouse_id": row.warehouse_id,
                        "vendor_id": vendor_id,
                        "purchase_date": firm_today(self._session, firm_id),
                        "expected_delivery_date": row.required_by,
                        "reference_number": row.rfq_number,
                        "external_reference": (
                            quotation.quote_ref if quotation else None
                        ),
                        "remarks": f"From RFQ {row.rfq_number}",
                        "lines": [
                            {
                                "product_id": line.product_id,
                                "purchase_uom_id": line.uom_id,
                                "ordered_quantity": line.quantity,
                                "unit_price": quote.rate,
                                "discount_percent": quote.discount_percent,
                                "remarks": line.notes,
                            }
                            for line, quote in sorted(
                                picks, key=lambda pick: pick[0].line_number
                            )
                        ],
                    }
                ),
                firm_id=firm_id,
                actor_id=actor_id,
            )
            supplier = suppliers.get(vendor_id)
            if supplier is not None:
                supplier.purchase_order_id = order.id
                supplier.updated_by = actor_id
            raised.append(order)
        self._close(row, actor_id, orders=len(raised))
        self._mark_requisition_ordered(row, actor_id)
        self._session.commit()
        return raised

    # -- reading --------------------------------------------------------
    def get(self, rfq_id: UUID, *, firm_id: UUID) -> Rfq:
        """Return one of the firm's RFQs."""
        row = self._rows.get(rfq_id, firm_id=firm_id)
        if row is None:
            raise ResourceNotFoundError("RFQ not found.")
        return row

    def page(
        self,
        firm_id: UUID,
        *,
        status: str | None,
        search: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Rfq], int]:
        """Return one page of the firm's RFQs and the total."""
        return self._rows.page(
            firm_id, status=status, search=search, page=page, page_size=page_size
        )

    def responses(self, rows: list[Rfq]) -> list[RfqResponse]:
        """Shape RFQs with their lines and suppliers, reading each table once."""
        if not rows:
            return []
        ids = [row.id for row in rows]
        lines = self._rows.lines(ids)
        suppliers = self._rows.suppliers(ids)
        quotations = self._rows.quotations(ids)
        products = self._rows.products(
            line.product_id for group in lines.values() for line in group
        )
        vendors = self._rows.vendors(
            s.vendor_id for group in suppliers.values() for s in group
        )
        quoted = {
            (q.rfq_id, q.vendor_id): q.id
            for group in quotations.values()
            for q in group
        }
        result: list[RfqResponse] = []
        for row in rows:
            result.append(
                RfqResponse(
                    id=row.id,
                    rfq_number=row.rfq_number,
                    rfq_date=row.rfq_date,
                    required_by=row.required_by,
                    branch_id=row.branch_id,
                    warehouse_id=row.warehouse_id,
                    status=row.status,
                    notes=row.notes,
                    source_requisition_id=row.source_requisition_id,
                    sent_at=row.sent_at,
                    closed_at=row.closed_at,
                    cancel_reason=row.cancel_reason,
                    version=row.version,
                    lines=[
                        RfqLineResponse(
                            id=line.id,
                            line_number=line.line_number,
                            product_id=line.product_id,
                            product_code=(
                                products[line.product_id].code
                                if line.product_id in products
                                else ""
                            ),
                            product_name=(
                                products[line.product_id].name
                                if line.product_id in products
                                else ""
                            ),
                            quantity=line.quantity,
                            uom_id=line.uom_id,
                            notes=line.notes,
                            selected_quotation_line_id=line.selected_quotation_line_id,
                            selection_reason=line.selection_reason,
                        )
                        for line in lines.get(row.id, [])
                    ],
                    suppliers=[
                        RfqSupplierResponse(
                            id=s.id,
                            vendor_id=s.vendor_id,
                            vendor_code=(
                                vendors[s.vendor_id].code
                                if s.vendor_id in vendors
                                else ""
                            ),
                            vendor_name=_vendor_name(vendors.get(s.vendor_id)),
                            quotation_id=quoted.get((row.id, s.vendor_id)),
                            purchase_order_id=s.purchase_order_id,
                        )
                        for s in suppliers.get(row.id, [])
                    ],
                )
            )
        return result

    def quotations(self, rfq_id: UUID, *, firm_id: UUID) -> list[SupplierQuotation]:
        """Return the RFQ's quotations."""
        row = self.get(rfq_id, firm_id=firm_id)
        return self._rows.quotations([row.id]).get(row.id, [])

    def quotation_responses(
        self, quotations: list[SupplierQuotation]
    ) -> list[SupplierQuotationResponse]:
        """Shape quotations with their lines, reading each table once."""
        if not quotations:
            return []
        lines = self._rows.quotation_lines(q.id for q in quotations)
        vendors = self._rows.vendors(q.vendor_id for q in quotations)
        return [
            SupplierQuotationResponse(
                id=q.id,
                rfq_id=q.rfq_id,
                vendor_id=q.vendor_id,
                vendor_name=_vendor_name(vendors.get(q.vendor_id)),
                quote_ref=q.quote_ref,
                quote_date=q.quote_date,
                valid_until=q.valid_until,
                notes=q.notes,
                version=q.version,
                lines=[
                    SupplierQuotationLineResponse(
                        id=line.id,
                        rfq_line_id=line.rfq_line_id,
                        rate=line.rate,
                        discount_percent=line.discount_percent,
                        landed_rate=landed_rate(line.rate, line.discount_percent),
                        lead_time_days=line.lead_time_days,
                        notes=line.notes,
                    )
                    for line in lines.get(q.id, [])
                ],
            )
            for q in quotations
        ]

    # -- internals ------------------------------------------------------
    @staticmethod
    def _require(row: Rfq, status: str, message: str) -> None:
        """Refuse unless the RFQ is in ``status``."""
        if row.status != status:
            raise ValidationError(message)

    def _close(self, row: Rfq, actor_id: UUID, **extra: object) -> None:
        """Move a sent RFQ to CLOSED, uncommitted."""
        row.status = "CLOSED"
        row.closed_at = utc_now()
        row.updated_by = actor_id
        self._audit("rfq.closed", row, actor_id, **extra)

    def _mark_requisition_ordered(self, row: Rfq, actor_id: UUID) -> None:
        """Mark the approved requisition the RFQ came from as ordered."""
        if row.source_requisition_id is None:
            return
        requisition = self._session.get(PurchaseRequisition, row.source_requisition_id)
        if requisition is None or requisition.status != "APPROVED":
            return
        requisition.status = "ORDERED"
        requisition.updated_by = actor_id
        record_audit(
            self._session,
            action="purchase_requisition.ordered",
            entity_type="purchase_requisition",
            entity_id=requisition.id,
            actor_id=actor_id,
            firm_id=requisition.firm_id,
            after_data={
                "requisition_number": requisition.requisition_number,
                "status": requisition.status,
                "rfq_number": row.rfq_number,
            },
        )

    def _write_lines(
        self, row: Rfq, lines: list[RfqLineWrite], *, actor_id: UUID
    ) -> None:
        """Reconcile the lines on their line number."""
        products = self._rows.products(line.product_id for line in lines)
        missing = [
            str(line.product_id)
            for line in lines
            if line.product_id not in products
            or products[line.product_id].firm_id != row.firm_id
            or products[line.product_id].is_deleted
        ]
        if missing:
            raise ValidationError("Unknown product(s): " + ", ".join(missing) + ".")
        existing = {
            line.line_number: line for line in self._rows.lines([row.id])[row.id]
        }
        seen: set[int] = set()
        for number, line in enumerate(lines, start=1):
            seen.add(number)
            current = existing.get(number)
            if current is None:
                current = RfqLine(
                    rfq_id=row.id,
                    firm_id=row.firm_id,
                    line_number=number,
                    created_by=actor_id,
                )
                self._session.add(current)
            current.product_id = line.product_id
            current.quantity = line.quantity
            current.uom_id = line.uom_id
            current.notes = line.notes
            current.updated_by = actor_id
        for number, stale in existing.items():
            if number not in seen:
                self._session.delete(stale)
        self._session.flush()

    def _write_suppliers(
        self, row: Rfq, vendor_ids: list[UUID], *, actor_id: UUID
    ) -> None:
        """Replace the invited suppliers, reviving one invited before."""
        wanted = list(dict.fromkeys(vendor_ids))
        vendors = self._rows.vendors(wanted)
        unknown = [
            str(vendor_id)
            for vendor_id in wanted
            if vendor_id not in vendors
            or vendors[vendor_id].firm_id != row.firm_id
            or vendors[vendor_id].is_deleted
        ]
        if unknown:
            raise ValidationError("Unknown supplier(s): " + ", ".join(unknown) + ".")
        existing = {
            s.vendor_id: s
            for s in self._rows.suppliers([row.id], include_deleted=True).get(
                row.id, []
            )
        }
        for vendor_id in wanted:
            current = existing.get(vendor_id)
            if current is None:
                current = RfqSupplier(
                    rfq_id=row.id,
                    firm_id=row.firm_id,
                    vendor_id=vendor_id,
                    created_by=actor_id,
                )
                self._session.add(current)
            elif current.is_deleted:
                current.is_deleted = False
                current.deleted_at = None
                current.updated_by = actor_id
        for vendor_id, stale in existing.items():
            if vendor_id not in wanted and not stale.is_deleted:
                stale.is_deleted = True
                stale.deleted_at = utc_now()
                stale.updated_by = actor_id
        self._session.flush()

    def _audit(self, action: str, row: Rfq, actor_id: UUID, **extra: object) -> None:
        """Write one audit row for an RFQ."""
        record_audit(
            self._session,
            action=action,
            entity_type="rfq",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=row.firm_id,
            after_data={
                "rfq_number": row.rfq_number,
                "status": row.status,
                **{key: value for key, value in extra.items()},
            },
        )
