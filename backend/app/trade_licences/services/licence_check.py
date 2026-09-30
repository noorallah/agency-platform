"""Check a document's lines against the licences its parties hold (backlog 54).

A product needs a licence type when it names one itself, or when its
sub-category or category -- or any category above them -- does; the product's
own outranks the category's, and the nearest category outranks the ones above
it. A product that resolves to none needs none, so a customer without any
licence can still buy everything else: the check is per line, not per
customer.

**The sale check** asks two parties: the customer, and the firm as seller --
a licence for the whole firm, or for the selling branch, since a drug licence
is issued per premises. **The purchase check** asks the vendor. Each is judged
on the document's own date, never today's, so a licence that lapsed after an
order was dated does not condemn it and one that starts next week does not
cover it.

What happens then is the firm's policy (``trade_licence_settings``): warn by
default, block if the firm chooses -- the sale side only. A blocked approval
can be overridden by a holder of ``TRADE_LICENCE_OVERRIDE`` who gives a
reason, and the override is recorded on the document's timeline with what it
overrode. The server decides; a screen only shows what this says.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.branches.models import Branch
from app.common.audit.services import record_audit
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.customers.models import Customer
from app.delivery_note.models import DeliveryNote, DeliveryNoteLine
from app.goods_receipt.models import GoodsReceipt, GoodsReceiptLine
from app.products.models import Product, ProductCategory
from app.purchase.models import PurchaseOrder, PurchaseOrderLine
from app.sales_invoice.models import SalesInvoice, SalesInvoiceLine
from app.sales_order.models import SalesOrder, SalesOrderLine
from app.trade_licences.models import (
    TradeLicence,
    TradeLicenceSettings,
    TradeLicenceType,
)
from app.trade_licences.schemas import (
    LicenceCheckResponse,
    LicenceEnforcement,
    LicenceFinding,
    LicenceParty,
    LicenceShortfall,
    LicenceStanding,
    TradeLicenceSettingsResponse,
    TradeLicenceSettingsWrite,
)
from app.trade_licences.services.trade_licence_service import standing_of
from app.vendors.models import Vendor

#: Standings that cover a document. A licence copied from the old free-text
#: fields has no valid-to; it is printed as held, so it is judged as held.
_COVERING = frozenset(
    {
        LicenceStanding.VALID,
        LicenceStanding.EXPIRING,
        LicenceStanding.NO_EXPIRY_RECORDED,
    }
)


class LicenceDocument(StrEnum):
    """The documents the check runs on."""

    SALES_ORDER = "SALES_ORDER"
    DELIVERY_NOTE = "DELIVERY_NOTE"
    SALES_INVOICE = "SALES_INVOICE"
    PURCHASE_ORDER = "PURCHASE_ORDER"
    GOODS_RECEIPT = "GOODS_RECEIPT"


@dataclass(frozen=True, slots=True)
class LicenceLine:
    """One document line, as far as the check needs it."""

    line_number: int
    product_id: UUID


@dataclass(frozen=True, slots=True)
class _Holder:
    """A party whose licences are asked about."""

    party: LicenceParty
    name: str
    licences: list[TradeLicence]


def _ancestors(
    category_id: UUID | None,
    categories: dict[UUID, tuple[UUID | None, UUID | None]],
) -> UUID | None:
    """Return the nearest licence type named on a category or above it."""
    seen: set[UUID] = set()
    while category_id is not None and category_id not in seen:
        seen.add(category_id)
        entry = categories.get(category_id)
        if entry is None:
            return None
        parent_id, licence_type_id = entry
        if licence_type_id is not None:
            return licence_type_id
        category_id = parent_id
    return None


class LicenceCheckService:
    """Say which licences a document needs and which are not held."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request unit of work."""
        self._session = session

    # -- policy -----------------------------------------------------------------

    def _stored_settings(self, firm_id: UUID) -> TradeLicenceSettings | None:
        """Return the firm's own policy row, or nothing if it never set one."""
        return self._session.scalar(
            select(TradeLicenceSettings).where(
                TradeLicenceSettings.firm_id == firm_id,
                TradeLicenceSettings.is_deleted.is_(False),
            )
        )

    def settings_response(self, firm_id: UUID) -> TradeLicenceSettingsResponse:
        """Report the firm's policy, defaulting to warn on both sides."""
        stored = self._stored_settings(firm_id)
        if stored is None:
            return TradeLicenceSettingsResponse(
                sale_enforcement=LicenceEnforcement.WARN,
                purchase_enforcement=LicenceEnforcement.WARN,
                is_configured=False,
            )
        return TradeLicenceSettingsResponse(
            sale_enforcement=LicenceEnforcement(stored.sale_enforcement),
            purchase_enforcement=LicenceEnforcement(stored.purchase_enforcement),
            is_configured=True,
        )

    def update_settings(
        self, data: TradeLicenceSettingsWrite, *, firm_id: UUID, actor_id: UUID
    ) -> TradeLicenceSettingsResponse:
        """Replace the firm's policy, creating its row on first write."""
        row = self._stored_settings(firm_id)
        before: dict[str, object] | None = None
        if row is None:
            row = TradeLicenceSettings(firm_id=firm_id, created_by=actor_id)
            self._session.add(row)
        else:
            before = {
                "sale_enforcement": row.sale_enforcement,
                "purchase_enforcement": row.purchase_enforcement,
            }
        row.sale_enforcement = data.sale_enforcement.value
        row.purchase_enforcement = data.purchase_enforcement.value
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action=(
                "trade_licence_settings.updated"
                if before is not None
                else "trade_licence_settings.created"
            ),
            entity_type="trade_licence_settings",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before,
            after_data={
                "sale_enforcement": row.sale_enforcement,
                "purchase_enforcement": row.purchase_enforcement,
            },
        )
        self._session.commit()
        return self.settings_response(firm_id)

    # -- what the lines need --------------------------------------------------------

    def required_types(self, firm_id: UUID, product_ids: set[UUID]) -> dict[UUID, UUID]:
        """Map each product that needs a licence to the type it needs."""
        if not product_ids:
            return {}
        products = self._session.execute(
            select(
                Product.id,
                Product.required_licence_type_id,
                Product.sub_category_id,
                Product.category_id,
            ).where(Product.id.in_(product_ids))
        ).all()
        categories: dict[UUID, tuple[UUID | None, UUID | None]] | None = None
        needed: dict[UUID, UUID] = {}
        for product_id, own, sub_category_id, category_id in products:
            if own is not None:
                needed[product_id] = own
                continue
            if sub_category_id is None and category_id is None:
                continue
            if categories is None:
                # A firm's categories are a short list: read once, walk here.
                categories = {
                    row_id: (parent_id, licence_type_id)
                    for row_id, parent_id, licence_type_id in self._session.execute(
                        select(
                            ProductCategory.id,
                            ProductCategory.parent_id,
                            ProductCategory.required_licence_type_id,
                        ).where(ProductCategory.firm_id == firm_id)
                    ).all()
                }
            found = _ancestors(sub_category_id, categories) or _ancestors(
                category_id, categories
            )
            if found is not None:
                needed[product_id] = found
        return needed

    # -- the checks, by document -------------------------------------------------

    # Five line models share the two columns read here and no base class, so
    # these two helpers take the model untyped rather than a five-way union.
    def _lines(
        self, model: Any, parent: Any, document_id: UUID  # noqa: ANN401
    ) -> list[LicenceLine]:
        """Read a document's live lines."""
        return [
            LicenceLine(line_number, product_id)
            for line_number, product_id in self._session.execute(
                select(model.line_number, model.product_id).where(
                    parent == document_id, model.is_deleted.is_(False)
                )
            ).all()
        ]

    def check_document(
        self, kind: LicenceDocument, document_id: UUID, *, firm_id: UUID
    ) -> LicenceCheckResponse:
        """Judge one saved document, as its approval would."""
        if kind is LicenceDocument.SALES_ORDER:
            order = self._document(SalesOrder, document_id, firm_id)
            return self.check_sale(
                firm_id=firm_id,
                customer_id=order.customer_id,
                branch_id=order.branch_id,
                on=order.order_date,
                lines=self._lines(
                    SalesOrderLine, SalesOrderLine.sales_order_id, order.id
                ),
            )
        if kind is LicenceDocument.DELIVERY_NOTE:
            note = self._document(DeliveryNote, document_id, firm_id)
            return self.check_sale(
                firm_id=firm_id,
                customer_id=note.customer_id,
                branch_id=note.branch_id,
                on=note.delivery_date,
                lines=self._lines(
                    DeliveryNoteLine, DeliveryNoteLine.delivery_note_id, note.id
                ),
            )
        if kind is LicenceDocument.SALES_INVOICE:
            invoice = self._document(SalesInvoice, document_id, firm_id)
            return self.check_sale(
                firm_id=firm_id,
                customer_id=invoice.customer_id,
                branch_id=invoice.branch_id,
                on=invoice.invoice_date,
                lines=self._lines(
                    SalesInvoiceLine, SalesInvoiceLine.sales_invoice_id, invoice.id
                ),
            )
        if kind is LicenceDocument.PURCHASE_ORDER:
            purchase = self._document(PurchaseOrder, document_id, firm_id)
            return self.check_purchase(
                firm_id=firm_id,
                vendor_id=purchase.vendor_id,
                on=purchase.purchase_date,
                lines=self._lines(
                    PurchaseOrderLine,
                    PurchaseOrderLine.purchase_order_id,
                    purchase.id,
                ),
            )
        receipt = self._document(GoodsReceipt, document_id, firm_id)
        return self.check_purchase(
            firm_id=firm_id,
            vendor_id=receipt.vendor_id,
            on=receipt.receipt_date,
            lines=self._lines(
                GoodsReceiptLine, GoodsReceiptLine.goods_receipt_id, receipt.id
            ),
        )

    def _document(
        self, model: Any, document_id: UUID, firm_id: UUID  # noqa: ANN401
    ) -> Any:  # noqa: ANN401
        """Return one live document of this firm, or refuse by name."""
        row = self._session.scalar(
            select(model).where(
                model.id == document_id,
                model.firm_id == firm_id,
                model.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Document not found.")
        return row

    def approve_sale(
        self,
        kind: LicenceDocument,
        document_id: UUID,
        *,
        firm_id: UUID,
        override_reason: str | None,
    ) -> tuple[str | None, dict[str, object] | None]:
        """Judge a sale at approval: refuse it, or say what to record."""
        result = self.check_document(kind, document_id, firm_id=firm_id)
        return self.enforce(result, override_reason=override_reason)

    def approve_purchase(
        self, kind: LicenceDocument, document_id: UUID, *, firm_id: UUID
    ) -> tuple[str | None, dict[str, object] | None]:
        """Judge a purchase at approval; it only ever warns."""
        result = self.check_document(kind, document_id, firm_id=firm_id)
        return self.enforce(result, override_reason=None)

    # -- the checks -------------------------------------------------------------------

    def check_sale(
        self,
        *,
        firm_id: UUID,
        customer_id: UUID,
        branch_id: UUID | None,
        on: date,
        lines: list[LicenceLine],
    ) -> LicenceCheckResponse:
        """Judge a sale: the customer and the selling branch, on its date."""
        policy = self.settings_response(firm_id)
        enforcement = policy.sale_enforcement
        if enforcement is LicenceEnforcement.OFF:
            return self._result("SALE", enforcement, on, [])
        customer_name = (
            self._session.scalar(
                select(Customer.display_name).where(Customer.id == customer_id)
            )
            or "The customer"
        )
        branch_name = (
            self._session.scalar(
                select(Branch.display_name).where(Branch.id == branch_id)
            )
            if branch_id is not None
            else None
        )
        seller_query = select(TradeLicence).where(
            TradeLicence.firm_id == firm_id,
            TradeLicence.is_deleted.is_(False),
            TradeLicence.holder_type == "FIRM",
        )
        seller_query = seller_query.where(
            TradeLicence.branch_id.is_(None) | (TradeLicence.branch_id == branch_id)
        )
        holders = [
            _Holder(
                LicenceParty.CUSTOMER,
                customer_name,
                self._licences(firm_id, TradeLicence.customer_id == customer_id),
            ),
            _Holder(
                LicenceParty.SELLER,
                f"The firm ({branch_name})" if branch_name else "The firm",
                list(self._session.scalars(seller_query).all()),
            ),
        ]
        findings = self._findings(firm_id, on=on, lines=lines, holders=holders)
        return self._result("SALE", enforcement, on, findings)

    def check_purchase(
        self,
        *,
        firm_id: UUID,
        vendor_id: UUID,
        on: date,
        lines: list[LicenceLine],
    ) -> LicenceCheckResponse:
        """Judge a purchase: whether the vendor may supply the goods. Warns only."""
        policy = self.settings_response(firm_id)
        enforcement = policy.purchase_enforcement
        if enforcement is LicenceEnforcement.OFF:
            return self._result("PURCHASE", enforcement, on, [])
        vendor_name = (
            self._session.scalar(
                select(Vendor.display_name).where(Vendor.id == vendor_id)
            )
            or "The vendor"
        )
        holders = [
            _Holder(
                LicenceParty.VENDOR,
                vendor_name,
                self._licences(firm_id, TradeLicence.vendor_id == vendor_id),
            )
        ]
        findings = self._findings(firm_id, on=on, lines=lines, holders=holders)
        return self._result("PURCHASE", enforcement, on, findings)

    def _licences(self, firm_id: UUID, condition: object) -> list[TradeLicence]:
        """Return a party's live licences."""
        return list(
            self._session.scalars(
                select(TradeLicence).where(
                    TradeLicence.firm_id == firm_id,
                    TradeLicence.is_deleted.is_(False),
                    condition,  # type: ignore[arg-type]
                )
            ).all()
        )

    def _findings(
        self,
        firm_id: UUID,
        *,
        on: date,
        lines: list[LicenceLine],
        holders: list[_Holder],
    ) -> list[LicenceFinding]:
        """Group the lines by the type they need; ask each holder for each type."""
        needed = self.required_types(firm_id, {line.product_id for line in lines})
        if not needed:
            return []
        by_type: dict[UUID, list[LicenceLine]] = defaultdict(list)
        for line in sorted(lines, key=lambda item: item.line_number):
            licence_type_id = needed.get(line.product_id)
            if licence_type_id is not None:
                by_type[licence_type_id].append(line)
        types = {
            row.id: row
            for row in self._session.scalars(
                select(TradeLicenceType).where(TradeLicenceType.id.in_(by_type))
            ).all()
        }
        names = dict(
            self._session.execute(
                select(Product.id, Product.name).where(
                    Product.id.in_({line.product_id for line in lines})
                )
            )
            .tuples()
            .all()
        )
        findings: list[LicenceFinding] = []
        for holder in holders:
            for licence_type_id, type_lines in by_type.items():
                licence_type = types[licence_type_id]
                finding = self._judge(
                    holder,
                    licence_type,
                    on=on,
                    lines=type_lines,
                    product_names=names,
                )
                if finding is not None:
                    findings.append(finding)
        return findings

    @staticmethod
    def _judge(
        holder: _Holder,
        licence_type: TradeLicenceType,
        *,
        on: date,
        lines: list[LicenceLine],
        product_names: dict[UUID, str],
    ) -> LicenceFinding | None:
        """Return why a holder's licences of one type do not cover a day."""
        held = [
            licence
            for licence in holder.licences
            if licence.licence_type_id == licence_type.id
        ]
        standings = [
            (licence, standing_of(licence, licence_type, on=on)[0]) for licence in held
        ]
        if any(standing in _COVERING for _, standing in standings):
            return None
        line_numbers = [line.line_number for line in lines]
        products = list(
            dict.fromkeys(product_names.get(line.product_id, "") for line in lines)
        )
        where = (
            f"Line {line_numbers[0]}"
            if len(line_numbers) == 1
            else "Lines " + ", ".join(str(number) for number in line_numbers)
        )
        where += f" ({', '.join(products)})"
        not_yet = [
            licence
            for licence, standing in standings
            if standing is LicenceStanding.NOT_YET_VALID
        ]
        expired = [
            licence
            for licence, standing in standings
            if standing is LicenceStanding.EXPIRED
        ]
        shown: TradeLicence | None = None
        if not_yet:
            shown = min(not_yet, key=lambda item: item.valid_from or date.max)
            shortfall = LicenceShortfall.NOT_YET_VALID
            why = (
                f"{holder.name}'s {licence_type.name} {shown.licence_number} "
                f"is valid only from {shown.valid_from.isoformat()}"
                if shown.valid_from is not None
                else f"{holder.name}'s {licence_type.name} is not yet valid"
            )
        elif expired:
            shown = max(expired, key=lambda item: item.valid_to or date.min)
            shortfall = LicenceShortfall.EXPIRED
            why = (
                f"{holder.name}'s {licence_type.name} {shown.licence_number} "
                f"expired on {shown.valid_to.isoformat()}"
                if shown.valid_to is not None
                else f"{holder.name}'s {licence_type.name} has expired"
            )
        else:
            shortfall = LicenceShortfall.MISSING
            why = f"{holder.name} holds no {licence_type.name}"
        return LicenceFinding(
            party=holder.party,
            party_name=holder.name,
            licence_type_id=licence_type.id,
            licence_type_name=licence_type.name,
            shortfall=shortfall,
            licence_number=None if shown is None else shown.licence_number,
            valid_from=None if shown is None else shown.valid_from,
            valid_to=None if shown is None else shown.valid_to,
            line_numbers=line_numbers,
            product_names=products,
            message=f"{where}: {why}.",
        )

    @staticmethod
    def _result(
        direction: str,
        enforcement: LicenceEnforcement,
        on: date,
        findings: list[LicenceFinding],
    ) -> LicenceCheckResponse:
        """Wrap the findings with the policy's verdict."""
        return LicenceCheckResponse(
            direction=direction,
            enforcement=enforcement,
            on=on,
            findings=findings,
            would_block=bool(findings) and enforcement is LicenceEnforcement.BLOCK,
            message=" ".join(item.message for item in findings) or None,
        )

    # -- at approval ----------------------------------------------------------------

    @staticmethod
    def enforce(
        result: LicenceCheckResponse, *, override_reason: str | None
    ) -> tuple[str | None, dict[str, object] | None]:
        """Refuse a blocked document, or say what to record on its timeline.

        Returns the remark and the event details: a warning when the policy
        warns, an override when it blocked and a reason was given, nothing
        when every line is covered. Whether the caller may override is the
        router's question -- it holds the principal.
        """
        if not result.findings:
            return None, None
        findings = [item.model_dump(mode="json") for item in result.findings]
        if result.would_block:
            reason = (override_reason or "").strip()
            if not reason:
                raise ValidationError(
                    f"{result.message} The firm's policy refuses a sale without "
                    "the licence; record the licence, or approve with an "
                    "override reason if you hold the override permission."
                )
            return (
                f"Licence check overridden: {reason}",
                {
                    "licence_override": {
                        "reason": reason,
                        "findings": findings,
                    }
                },
            )
        return result.message, {"licence_warning": {"findings": findings}}
