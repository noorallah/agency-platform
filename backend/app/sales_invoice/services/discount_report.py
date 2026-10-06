"""Discount given: what was given away, by whom and on whose say-so (67 row 8).

Every billed line records where its discount came from (``discount_source``),
so this is a report rather than a data change. **Billed** is what the sales
analysis bills: approved and closed invoices dated in the period, read by the
invoice's own date. Returns and credit notes are not netted -- what a return
takes back is the goods, not the discount decision.

A line's discount is put in one of three columns by the branch that set it:

* **Typed** -- somebody keyed a rate or an amount (``percent``/``amount``), on
  the bill or on the order the bill inherited it from. A line written before
  the source was recorded that carries a discount is judged typed, as the
  approver's discount limit judges it.
* **Arranged** -- a standing arrangement applied itself: the price list, the
  customer's own rate or their group's.
* **Promotion** -- an offer set it.

An ``inherited`` line looks through to the order line it continues, because
that is where the decision was made: a bill raised from a delivery note
reaches it through the note's line. The bill's **share of a bill discount**
is its own column: it is typed on the bill, or carried from the order where
an offer may have set it, and the line does not say which.

**Everything billed in the period has a row, discounted or not.** A product
sold at full price reads a discount of nothing rather than being left out:
with it left out the gross by product fell short of the gross by customer and
by salesman by exactly what that product sold for, and the percentage beside
it was of a smaller figure than the firm billed (D-PRC-14). The three
dimensions add up to the same gross and the same discount.

Grouped and paged in SQL; names are read once for the page.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Select, and_, case, func, or_, select
from sqlalchemy.orm import InstrumentedAttribute, Session
from sqlalchemy.sql.elements import ColumnElement

from app.common.firm_metadata import FirmMetadataReader
from app.core.exceptions import ValidationError
from app.core.pagination.reports import ReportRows, ReportWindow
from app.core.utils.chunks import over_chunks
from app.customers.models import Customer
from app.delivery_note.models import DeliveryNoteLine
from app.products.models import Product
from app.promotions.models import Promotion, PromotionRedemption
from app.sales_invoice.models import SalesInvoice, SalesInvoiceLine
from app.sales_order.models import SalesOrderLine

ZERO = Decimal("0.00")
BILLED = ("APPROVED", "CLOSED")
TYPED = ("percent", "amount")
ARRANGED = ("price_list", "customer", "customer_group")

#: The dimensions a discount is read by, and the invoice column each groups on.
DIMENSIONS = ("customer", "salesman", "product")

#: What a row says for a bill with no salesman.
NO_SALESMAN = "No salesman"


@dataclass(frozen=True)
class DiscountRow:
    """One customer's, salesman's or product's discounts over the period."""

    key_id: UUID | None
    code: str
    name: str
    lines: int
    gross_amount: Decimal
    typed_discount: Decimal
    arranged_discount: Decimal
    promotion_discount: Decimal
    bill_discount: Decimal
    total_discount: Decimal
    discount_percent: Decimal


@dataclass(frozen=True)
class PromotionDiscountRow:
    """One offer's claims over the period, as it costed them."""

    version_group_id: UUID
    code: str
    name: str
    claims: int
    customers: int
    benefit_amount: Decimal


def _money(value: object) -> Decimal:
    """Read a summed figure to two places; NULL is nothing."""
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


class DiscountReportService:
    """Read the discount given over a window."""

    def __init__(self, session: Session) -> None:
        """Bind to the firm's store."""
        self._session = session

    def by(
        self, firm_id: UUID, dimension: str, window: ReportWindow
    ) -> list[DiscountRow]:
        """Return the discount given per ``dimension``, largest first.

        Every customer, salesman or product billed in the window is a row,
        one given no discount included, so each dimension's gross adds up to
        what was billed.

        Raises:
            ValidationError: If ``dimension`` is not one of ``DIMENSIONS``.

        """
        if dimension not in DIMENSIONS:
            raise ValidationError(f"Discounts are read by {', '.join(DIMENSIONS)}.")
        key: InstrumentedAttribute[Any] = {
            "customer": SalesInvoice.customer_id,
            "salesman": SalesInvoice.salesman_id,
            "product": SalesInvoiceLine.product_id,
        }[dimension]
        # Where an inherited discount was decided: the order line the bill's
        # line continues, through a delivery note's line where there is one.
        order_line = SalesOrderLine.__table__.alias("decided_on")
        source = case(
            (
                SalesInvoiceLine.discount_source == "inherited",
                order_line.c.discount_source,
            ),
            else_=SalesInvoiceLine.discount_source,
        )
        amount = SalesInvoiceLine.discount_amount
        typed = or_(
            source.in_(TYPED),
            and_(source.is_(None), amount > 0),
            # Inherited from a line that cannot be found: somebody typed it
            # somewhere, and an arrangement would have been re-read here.
            source == "inherited",
        )

        def part(condition: ColumnElement[bool]) -> ColumnElement[Any]:
            """Sum the line discount where ``condition`` holds."""
            return func.coalesce(func.sum(case((condition, amount), else_=0)), 0)

        total = func.coalesce(
            func.sum(amount + SalesInvoiceLine.bill_discount_amount), 0
        )
        statement: Select[Any] = (
            select(
                key.label("key_id"),
                func.count(SalesInvoiceLine.id),
                func.coalesce(func.sum(SalesInvoiceLine.gross_amount), 0),
                part(typed),
                part(source.in_(ARRANGED)),
                part(source == "promotion"),
                func.coalesce(func.sum(SalesInvoiceLine.bill_discount_amount), 0),
                total,
            )
            .select_from(SalesInvoiceLine)
            .join(SalesInvoice, SalesInvoice.id == SalesInvoiceLine.sales_invoice_id)
            .outerjoin(
                DeliveryNoteLine,
                and_(
                    SalesInvoiceLine.source_document_type == "DELIVERY_NOTE",
                    DeliveryNoteLine.id == SalesInvoiceLine.source_document_line_id,
                ),
            )
            .outerjoin(
                order_line,
                order_line.c.id
                == func.coalesce(
                    DeliveryNoteLine.sales_order_line_id,
                    SalesInvoiceLine.source_document_line_id,
                ),
            )
            .where(
                SalesInvoice.firm_id == firm_id,
                SalesInvoice.is_deleted.is_(False),
                SalesInvoice.status.in_(BILLED),
                SalesInvoiceLine.is_deleted.is_(False),
                *window.dated(SalesInvoice.invoice_date),
            )
            .group_by(key)
            .order_by(total.desc(), case((key.is_(None), 1), else_=0), key)
        )
        if window.page is None:
            rows = list(self._session.execute(statement).all())
            count = len(rows)
        else:
            count = int(
                self._session.scalar(
                    select(func.count()).select_from(
                        statement.order_by(None).subquery()
                    )
                )
                or 0
            )
            rows = list(
                self._session.execute(
                    statement.offset((window.page - 1) * window.page_size).limit(
                        window.page_size
                    )
                ).all()
            )
        names = self._names(firm_id, dimension, [row[0] for row in rows if row[0]])
        records: list[DiscountRow] = []
        for key_id, lines, gross, typed_, arranged, promotion, bill, given in rows:
            code, name = names.get(key_id, ("", NO_SALESMAN if key_id is None else ""))
            gross_amount = _money(gross)
            given_amount = _money(given)
            records.append(
                DiscountRow(
                    key_id=key_id,
                    code=code,
                    name=name,
                    lines=int(lines),
                    gross_amount=gross_amount,
                    typed_discount=_money(typed_),
                    arranged_discount=_money(arranged),
                    promotion_discount=_money(promotion),
                    bill_discount=_money(bill),
                    total_discount=given_amount,
                    discount_percent=(
                        (given_amount * 100 / gross_amount).quantize(Decimal("0.01"))
                        if gross_amount
                        else ZERO
                    ),
                )
            )
        return ReportRows(records, total_records=count)

    def by_promotion(
        self, firm_id: UUID, window: ReportWindow
    ) -> list[PromotionDiscountRow]:
        """Return what each offer was claimed for over the window, costliest first.

        Read from the claims recorded at approval, by the day they were
        claimed; a reversed claim is not counted. Grouped by the offer's
        ``version_group_id``, so an offer edited mid-period is one row, named
        as its latest version.
        """
        benefit = func.coalesce(func.sum(PromotionRedemption.benefit_amount), 0)
        rows = list(
            self._session.execute(
                select(
                    Promotion.version_group_id,
                    func.count(PromotionRedemption.id),
                    func.count(func.distinct(PromotionRedemption.customer_id)),
                    benefit,
                )
                .join(Promotion, Promotion.id == PromotionRedemption.promotion_id)
                .where(
                    PromotionRedemption.firm_id == firm_id,
                    PromotionRedemption.is_deleted.is_(False),
                    PromotionRedemption.status == "CLAIMED",
                    *window.dated(PromotionRedemption.redeemed_on),
                )
                .group_by(Promotion.version_group_id)
                .order_by(benefit.desc(), Promotion.version_group_id)
            ).all()
        )
        named = _offer_names(self._session, group_ids=[row[0] for row in rows])
        return [
            PromotionDiscountRow(
                version_group_id=group,
                code=named.get(group, ("", ""))[0],
                name=named.get(group, ("", ""))[1],
                claims=int(claims),
                customers=int(customers),
                benefit_amount=_money(amount),
            )
            for group, claims, customers, amount in rows
        ]

    def _names(
        self, firm_id: UUID, dimension: str, ids: list[UUID]
    ) -> dict[UUID | None, tuple[str, str]]:
        """Name the page's customers, products or salesmen, once for the page."""
        if dimension == "salesman":
            members = FirmMetadataReader(self._session).active_members(firm_id)
            wanted = set(ids)
            found: dict[UUID | None, tuple[str, str]] = {
                member.user_id: ("", member.full_name or member.email)
                for member in members
                if member.user_id in wanted
            }
            for missing in wanted - set(found):
                found[missing] = ("", "Former member")
            return found
        return dict(_master_names(self._session, dimension=dimension, ids=ids))


@over_chunks("ids")
def _master_names(
    session: Session, *, dimension: str, ids: list[UUID]
) -> dict[UUID | None, tuple[str, str]]:
    """Read the code and name of each customer or product named."""
    if not ids:
        return {}
    if dimension == "customer":
        return {
            row_id: (code, display or name)
            for row_id, code, display, name in session.execute(
                select(
                    Customer.id, Customer.code, Customer.display_name, Customer.name
                ).where(Customer.id.in_(ids))
            ).all()
        }
    return {
        row_id: (code, name)
        for row_id, code, name in session.execute(
            select(Product.id, Product.code, Product.name).where(Product.id.in_(ids))
        ).all()
    }


@over_chunks("group_ids")
def _offer_names(
    session: Session, *, group_ids: list[UUID]
) -> dict[UUID, tuple[str, str]]:
    """Name each offer as its latest version names it."""
    if not group_ids:
        return {}
    latest: dict[UUID, tuple[int, str, str]] = {}
    for group, number, code, name in session.execute(
        select(
            Promotion.version_group_id,
            Promotion.version_number,
            Promotion.code,
            Promotion.name,
        ).where(Promotion.version_group_id.in_(group_ids))
    ).all():
        held = latest.get(group)
        if held is None or number > held[0]:
            latest[group] = (number, code, name)
    return {group: (code, name) for group, (_, code, name) in latest.items()}
