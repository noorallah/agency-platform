"""Check a document's lines against the licences its parties hold (backlog 54).

A product needs a licence type when it names one itself, or when its
sub-category or category -- or any category above them -- does; the product's
own outranks the category's, and the nearest category outranks the ones above
it. A product that resolves to none needs none, so a customer without any
licence can still buy everything else: the check is per line, not per
customer.

**A product or a category may name several** (backlog 152), and then every
one is asked for: each type is judged by itself, so a party short of two
gets two findings, each naming its licence. The list a product names takes
the place of its category's; it is not added to it. A list of one behaves
exactly as the single type did.

**The sale check** asks two parties: the customer, and the firm as seller --
a licence for the whole firm, or for the selling branch, since a drug licence
is issued per premises. **The purchase check** asks the vendor. Each is judged
on the document's own date, never today's, so a licence that lapsed after an
order was dated does not condemn it and one that starts next week does not
cover it.

**A shop under a parent buyer** (row F8) is asked for its own licence of the
type first. Where it holds none of that type at all, its parent's counts,
judged on the same date, and the result says the parent's was used; a shop
that holds one of its own, valid or not, is judged on its own. A supplier's
branch and its main office work the same way on the purchase check. The firm
setting ``shop_needs_own_licence`` switches the parent off for both.

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

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.branches.models import Branch
from app.common.audit.services import record_audit
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.customers.models import Customer
from app.delivery_note.models import DeliveryNote, DeliveryNoteLine
from app.goods_receipt.models import GoodsReceipt, GoodsReceiptLine
from app.products.models import (
    Product,
    ProductCategory,
    ProductCategoryLicenceRequirement,
    ProductLicenceRequirement,
)
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
    LicenceParentCover,
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


#: The licence types whose missing expiry date a new sale warns about.
_DRUG_TYPE_PREFIX = "DRUG_"


def no_expiry_warning(
    session: Session, firm_id: UUID, customer_id: UUID, on: date
) -> dict[str, object] | None:
    """Say which of a customer's drug licences have no expiry date recorded.

    A new sales order or invoice asks this (owner decision 2026-10-17). A
    drug licence with no valid-to still *covers* a sale (``_COVERING``), so
    the check never refuses; this only tells the person to add the date.
    It warns whatever the firm's licence enforcement is, judges each licence
    on the document's own date, and refuses nothing. Returns None when
    there is nothing to say.
    """
    # No autoflush: the document is still being staged, and a flush here
    # would raise its number clash from this read instead of from the
    # service's own conflict handling.
    with session.no_autoflush:
        rows = session.execute(
            select(TradeLicence, TradeLicenceType)
            .join(TradeLicenceType, TradeLicenceType.id == TradeLicence.licence_type_id)
            .where(
                TradeLicence.firm_id == firm_id,
                TradeLicence.is_deleted.is_(False),
                TradeLicence.customer_id == customer_id,
                TradeLicenceType.code.startswith(_DRUG_TYPE_PREFIX),
            )
            .order_by(TradeLicenceType.code, TradeLicence.licence_number)
        ).all()
        missing = [
            (licence, licence_type)
            for licence, licence_type in rows
            if standing_of(licence, licence_type, on=on)[0]
            is LicenceStanding.NO_EXPIRY_RECORDED
        ]
        if not missing:
            return None
        customer_name = (
            session.scalar(
                select(Customer.display_name).where(Customer.id == customer_id)
            )
            or "the customer"
        )
    return {
        "licences": [
            {
                "licence_id": str(licence.id),
                "licence_type_code": licence_type.code,
                "licence_type_name": licence_type.name,
                "licence_number": licence.licence_number,
            }
            for licence, licence_type in missing
        ],
        "message": " ".join(
            f"{licence_type.name} {licence.licence_number} for {customer_name} "
            "has no expiry date; please add it."
            for licence, licence_type in missing
        ),
    }


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
    #: The parent buyer or main office whose licences stand in for a type
    #: this holder has none of; None where there is none, or the firm asks
    #: each shop for its own.
    parent_name: str | None = None
    parent_licences: tuple[TradeLicence, ...] = ()


def _ancestors(
    category_id: UUID | None,
    categories: dict[UUID, tuple[UUID | None, tuple[UUID, ...]]],
) -> tuple[UUID, ...]:
    """Return the licence types of the nearest category that names any."""
    seen: set[UUID] = set()
    while category_id is not None and category_id not in seen:
        seen.add(category_id)
        entry = categories.get(category_id)
        if entry is None:
            return ()
        parent_id, licence_type_ids = entry
        if licence_type_ids:
            return licence_type_ids
        category_id = parent_id
    return ()


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
                shop_needs_own_licence=False,
                is_configured=False,
            )
        return TradeLicenceSettingsResponse(
            sale_enforcement=LicenceEnforcement(stored.sale_enforcement),
            purchase_enforcement=LicenceEnforcement(stored.purchase_enforcement),
            shop_needs_own_licence=stored.shop_needs_own_licence,
            is_configured=True,
        )

    def update_settings(
        self, data: TradeLicenceSettingsWrite, *, firm_id: UUID, actor_id: UUID
    ) -> TradeLicenceSettingsResponse:
        """Replace the firm's policy, creating its row on first write."""
        row = self._stored_settings(firm_id)
        before: dict[str, object] | None = None
        if row is None:
            row = TradeLicenceSettings(
                firm_id=firm_id, created_by=actor_id, shop_needs_own_licence=False
            )
            self._session.add(row)
        else:
            before = {
                "sale_enforcement": row.sale_enforcement,
                "purchase_enforcement": row.purchase_enforcement,
                "shop_needs_own_licence": row.shop_needs_own_licence,
            }
        row.sale_enforcement = data.sale_enforcement.value
        row.purchase_enforcement = data.purchase_enforcement.value
        # Absent means leave alone: a client older than the switch sends
        # the two policies only.
        if data.shop_needs_own_licence is not None:
            row.shop_needs_own_licence = data.shop_needs_own_licence
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
                "shop_needs_own_licence": row.shop_needs_own_licence,
            },
        )
        self._session.commit()
        return self.settings_response(firm_id)

    # -- what the lines need --------------------------------------------------------

    def required_types(
        self, firm_id: UUID, product_ids: set[UUID]
    ) -> dict[UUID, tuple[UUID, ...]]:
        """Map each product that needs a licence to the types it needs.

        Every type on the list is needed. A product's own list takes the
        place of its category's, and the nearest category that names any
        takes the place of those above it.
        """
        if not product_ids:
            return {}
        products = self._session.execute(
            select(Product.id, Product.sub_category_id, Product.category_id).where(
                Product.id.in_(product_ids)
            )
        ).all()
        own: dict[UUID, list[UUID]] = defaultdict(list)
        for product_id, licence_type_id in self._session.execute(
            select(
                ProductLicenceRequirement.product_id,
                ProductLicenceRequirement.licence_type_id,
            )
            .where(
                ProductLicenceRequirement.product_id.in_(product_ids),
                ProductLicenceRequirement.is_deleted.is_(False),
            )
            .order_by(ProductLicenceRequirement.position)
        ).all():
            own[product_id].append(licence_type_id)
        categories: dict[UUID, tuple[UUID | None, tuple[UUID, ...]]] | None = None
        needed: dict[UUID, tuple[UUID, ...]] = {}
        for product_id, sub_category_id, category_id in products:
            if product_id in own:
                needed[product_id] = tuple(own[product_id])
                continue
            if sub_category_id is None and category_id is None:
                continue
            if categories is None:
                categories = self._category_requirements(firm_id)
            found = _ancestors(sub_category_id, categories) or _ancestors(
                category_id, categories
            )
            if found:
                needed[product_id] = found
        return needed

    def _category_requirements(
        self, firm_id: UUID
    ) -> dict[UUID, tuple[UUID | None, tuple[UUID, ...]]]:
        """Return each category's parent and the licence types it names.

        A firm's categories are a short list: read once, walked by the
        caller.
        """
        named: dict[UUID, list[UUID]] = defaultdict(list)
        for category_id, licence_type_id in self._session.execute(
            select(
                ProductCategoryLicenceRequirement.category_id,
                ProductCategoryLicenceRequirement.licence_type_id,
            )
            .join(
                ProductCategory,
                ProductCategory.id == ProductCategoryLicenceRequirement.category_id,
            )
            .where(
                ProductCategory.firm_id == firm_id,
                ProductCategoryLicenceRequirement.is_deleted.is_(False),
            )
            .order_by(ProductCategoryLicenceRequirement.position)
        ).all():
            named[category_id].append(licence_type_id)
        return {
            row_id: (parent_id, tuple(named.get(row_id, ())))
            for row_id, parent_id in self._session.execute(
                select(ProductCategory.id, ProductCategory.parent_id).where(
                    ProductCategory.firm_id == firm_id
                )
            ).all()
        }

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
            return self._result("SALE", enforcement, on, [], [])
        customer = self._session.execute(
            select(Customer.display_name, Customer.parent_customer_id).where(
                Customer.id == customer_id
            )
        ).one_or_none()
        customer_name = (customer.display_name if customer else None) or (
            "The customer"
        )
        parent_id = customer.parent_customer_id if customer else None
        parent_name, parent_licences = (
            (None, ())
            if parent_id is None
            else self._parent(
                policy,
                firm_id,
                select(Customer.display_name).where(Customer.id == parent_id),
                TradeLicence.customer_id == parent_id,
            )
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
                parent_name,
                parent_licences,
            ),
            _Holder(
                LicenceParty.SELLER,
                f"The firm ({branch_name})" if branch_name else "The firm",
                list(self._session.scalars(seller_query).all()),
            ),
        ]
        findings, covers = self._findings(firm_id, on=on, lines=lines, holders=holders)
        return self._result("SALE", enforcement, on, findings, covers)

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
            return self._result("PURCHASE", enforcement, on, [], [])
        vendor = self._session.execute(
            select(Vendor.display_name, Vendor.parent_vendor_id).where(
                Vendor.id == vendor_id
            )
        ).one_or_none()
        vendor_name = (vendor.display_name if vendor else None) or "The vendor"
        parent_id = vendor.parent_vendor_id if vendor else None
        parent_name, parent_licences = (
            (None, ())
            if parent_id is None
            else self._parent(
                policy,
                firm_id,
                select(Vendor.display_name).where(Vendor.id == parent_id),
                TradeLicence.vendor_id == parent_id,
            )
        )
        holders = [
            _Holder(
                LicenceParty.VENDOR,
                vendor_name,
                self._licences(firm_id, TradeLicence.vendor_id == vendor_id),
                parent_name,
                parent_licences,
            )
        ]
        findings, covers = self._findings(firm_id, on=on, lines=lines, holders=holders)
        return self._result("PURCHASE", enforcement, on, findings, covers)

    def _parent(
        self,
        policy: TradeLicenceSettingsResponse,
        firm_id: UUID,
        name_of_parent: Select[tuple[str]],
        holds: object,
    ) -> tuple[str | None, tuple[TradeLicence, ...]]:
        """Return a parent's name and licences, where they may stand in.

        Nothing where the firm asks each shop for its own: the party is then
        judged alone, as one with no parent is.
        """
        if policy.shop_needs_own_licence:
            return None, ()
        name = self._session.scalar(name_of_parent)
        if name is None:
            return None, ()
        return name, tuple(self._licences(firm_id, holds))

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
    ) -> tuple[list[LicenceFinding], list[LicenceParentCover]]:
        """Group the lines by the type they need; ask each holder for each type."""
        needed = self.required_types(firm_id, {line.product_id for line in lines})
        if not needed:
            return [], []
        by_type: dict[UUID, list[LicenceLine]] = defaultdict(list)
        for line in sorted(lines, key=lambda item: item.line_number):
            # A line that needs several is judged under each (backlog 152).
            for licence_type_id in needed.get(line.product_id, ()):
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
        covers: list[LicenceParentCover] = []
        for holder in holders:
            for licence_type_id, type_lines in by_type.items():
                licence_type = types[licence_type_id]
                judged = self._judge(
                    holder,
                    licence_type,
                    on=on,
                    lines=type_lines,
                    product_names=names,
                )
                if isinstance(judged, LicenceFinding):
                    findings.append(judged)
                elif judged is not None:
                    covers.append(judged)
        return findings, covers

    @staticmethod
    def _judge(
        holder: _Holder,
        licence_type: TradeLicenceType,
        *,
        on: date,
        lines: list[LicenceLine],
        product_names: dict[UUID, str],
    ) -> LicenceFinding | LicenceParentCover | None:
        """Return why a holder's licences of one type do not cover a day.

        Or, where the holder has none of the type and its parent's covers
        the day, that the parent's was used.
        """
        held = [
            licence
            for licence in holder.licences
            if licence.licence_type_id == licence_type.id
        ]
        # The holder's own comes first: only one with none of the type at
        # all is judged on its parent's (row F8).
        from_parent = not held and holder.parent_name is not None
        if from_parent:
            held = [
                licence
                for licence in holder.parent_licences
                if licence.licence_type_id == licence_type.id
            ]
        owner = (
            f"{holder.name} holds no {licence_type.name}; its parent "
            f"{holder.parent_name}'s"
            if from_parent
            else f"{holder.name}'s"
        )
        standings = [
            (licence, standing_of(licence, licence_type, on=on)[0]) for licence in held
        ]
        covering = [licence for licence, standing in standings if standing in _COVERING]
        if covering and not from_parent:
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
        if covering:
            # The one that runs longest is the one named and printed.
            used = max(covering, key=lambda item: item.valid_to or date.max)
            return LicenceParentCover(
                party=holder.party,
                party_name=holder.name,
                parent_name=holder.parent_name or "",
                licence_type_id=licence_type.id,
                licence_type_name=licence_type.name,
                licence_number=used.licence_number,
                valid_from=used.valid_from,
                valid_to=used.valid_to,
                line_numbers=line_numbers,
                product_names=products,
                message=(
                    f"{where}: {owner} {licence_type.name} "
                    f"{used.licence_number} was used."
                ),
            )
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
                f"{owner} {licence_type.name} {shown.licence_number} "
                f"is valid only from {shown.valid_from.isoformat()}"
                if shown.valid_from is not None
                else f"{owner} {licence_type.name} is not yet valid"
            )
        elif expired:
            shown = max(expired, key=lambda item: item.valid_to or date.min)
            shortfall = LicenceShortfall.EXPIRED
            why = (
                f"{owner} {licence_type.name} {shown.licence_number} "
                f"expired on {shown.valid_to.isoformat()}"
                if shown.valid_to is not None
                else f"{owner} {licence_type.name} has expired"
            )
        else:
            shortfall = LicenceShortfall.MISSING
            why = (
                f"{holder.name} holds no {licence_type.name}, and neither "
                f"does its parent {holder.parent_name}"
                if from_parent
                else f"{holder.name} holds no {licence_type.name}"
            )
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
            parent_name=holder.parent_name if from_parent else None,
            message=f"{where}: {why}.",
        )

    @staticmethod
    def _result(
        direction: str,
        enforcement: LicenceEnforcement,
        on: date,
        findings: list[LicenceFinding],
        covers: list[LicenceParentCover],
    ) -> LicenceCheckResponse:
        """Wrap the findings with the policy's verdict."""
        return LicenceCheckResponse(
            direction=direction,
            enforcement=enforcement,
            on=on,
            findings=findings,
            covered_by_parent=covers,
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

        A line covered by a parent's licence stops nothing, and the timeline
        still says whose licence was used.
        """
        covers = [item.model_dump(mode="json") for item in result.covered_by_parent]
        used = " ".join(item.message for item in result.covered_by_parent)
        cover_details: dict[str, object] = (
            {"licence_parent_cover": {"covers": covers}} if covers else {}
        )
        if not result.findings:
            return (used, cover_details) if covers else (None, None)
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
                    },
                    **cover_details,
                },
            )
        return (
            f"{result.message} {used}".strip(),
            {"licence_warning": {"findings": findings}, **cover_details},
        )
