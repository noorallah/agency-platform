"""What an offer's discount came to on the bills, for a claim on its principal.

A redemption is the **order's**: it is claimed when the order is approved and
says what the offer took off that order. A principal owes its share of what
the firm actually gave a customer, and nothing is given until it is billed --
an order approved and never delivered gave nothing, one closed after half was
delivered gave half, and one billed and returned in full gave nothing after
all (D-PRC-27). So the scheme money on a claim is read here, off the bills.

**The share a bill line took.** A bill line continues a delivery note line,
which continues an order line (or the order line directly, for a firm that
types no notes), each for part of its quantity. The product of those parts
is the share of the order line the bill line billed, and that share of what
the offer took off the order line -- its line discount where the order line
says an offer set it, its part of the bill discount where the order says an
offer set that, and the delivery charge an offer waived, by value -- is the
discount the bill passed on. It is what the bill line inherited
(`continued_share`), read from the order's own figures so a discount somebody
typed over on the way down is not charged to the principal.

**Less what came back.** A completed sales return of the bill line (or of the
note line it billed), and an approved credit note against it, take the same
share of that discount back: half the units returned is half of it.

**One order, several offers.** An order line records one discount, not which
offer gave how much of it, so each redemption on the order takes the order's
passed-on discount in proportion to its own benefit. With one offer on the
order -- the usual case -- that is the discount exactly.

The per-bill-line figures -- what a line carried and the share of it that
came back -- are `discount_on_bills` in `app/promotions/services`, which an
offer's own budget and reports read too (D-PRC-45): one statement, so the
claim and the offer cannot net a return differently.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.utils.money import ZERO
from app.promotions.models import Promotion, PromotionRedemption
from app.promotions.services.bill_discounts import discount_on_bills
from app.sales_invoice.models import SalesInvoice
from app.sales_order.models import SalesOrderLine

#: Fixed, so one redemption on one bill always makes the same source id --
#: which is what lets the claim lines' unique index refuse a second claim for
#: the same discount.
_SCHEME_BILLS = UUID("3d1b0c52-8a67-4f0e-9d6b-51b7a2c9e4f3")


def scheme_bill_source(redemption_id: UUID, invoice_id: UUID) -> UUID:
    """Return the source an offer's discount on one bill is claimed under."""
    return uuid5(_SCHEME_BILLS, f"{redemption_id}:{invoice_id}")


@dataclass(frozen=True)
class PassedOn:
    """What one redemption's offer took off one bill, before any share."""

    redemption_id: UUID
    promotion_id: UUID
    invoice_id: UUID
    invoice_number: str
    invoice_date: date
    order_number: str
    #: The offer's discount the bill carried when it was approved.
    billed: Decimal
    #: The part of it completed returns and credit notes have taken back.
    came_back: Decimal

    @property
    def given(self) -> Decimal:
        """What the customer kept: the discount billed less what came back."""
        return max(self.billed - self.came_back, ZERO)


def _dec(value: object) -> Decimal:
    """Read a stored number as a Decimal; nothing is zero."""
    return Decimal(str(value or 0))


def passed_on_bills(
    session: Session,
    *,
    firm_id: UUID,
    principal_id: UUID,
    start: date,
    end: date,
) -> list[PassedOn]:
    """Return what the principal's offers took off the bills dated in a period.

    One row per live redemption and bill, in bill date order. Read over the
    period's bills in two statements, never per bill and never by a list of
    ids. What each bill line carried and how much of it came back is
    `discount_on_bills`, the statement an offer's own budget reads too, so
    the claim and the offer cannot net a return differently (D-PRC-45).
    """
    funded = (
        select(PromotionRedemption.document_id)
        .join(Promotion, Promotion.id == PromotionRedemption.promotion_id)
        .where(
            PromotionRedemption.firm_id == firm_id,
            PromotionRedemption.is_deleted.is_(False),
            PromotionRedemption.status == "CLAIMED",
            PromotionRedemption.document_type == "SALES_ORDER",
            Promotion.principal_id == principal_id,
        )
    )
    lines = discount_on_bills(
        firm_id,
        SalesInvoice.invoice_date >= start,
        SalesInvoice.invoice_date <= end,
        SalesOrderLine.sales_order_id.in_(funded),
    ).subquery("billed")
    billed = session.execute(
        select(lines).order_by(lines.c.invoice_date, lines.c.invoice_number)
    ).all()
    if not billed:
        return []
    # Per order and bill: the offers' discount billed, and the part returned.
    sums: dict[tuple[UUID, UUID], list[Decimal]] = {}
    bills: dict[UUID, tuple[str, date]] = {}
    orders: dict[UUID, tuple[str, Decimal]] = {}
    for row in billed:
        passed = _dec(row.passed)
        entry = sums.setdefault((row.order_id, row.invoice_id), [ZERO, ZERO])
        entry[0] += passed
        entry[1] += passed * min(_dec(row.returned), Decimal("1"))
        bills[row.invoice_id] = (row.invoice_number, row.invoice_date)
        orders[row.order_id] = (row.order_number, _dec(row.whole))
    found: list[PassedOn] = []
    redemptions = session.execute(
        select(
            PromotionRedemption.id,
            PromotionRedemption.promotion_id,
            PromotionRedemption.document_id,
            PromotionRedemption.benefit_amount,
        )
        .join(Promotion, Promotion.id == PromotionRedemption.promotion_id)
        .where(
            PromotionRedemption.firm_id == firm_id,
            PromotionRedemption.is_deleted.is_(False),
            PromotionRedemption.status == "CLAIMED",
            PromotionRedemption.document_type == "SALES_ORDER",
            PromotionRedemption.benefit_amount > 0,
            Promotion.principal_id == principal_id,
            PromotionRedemption.document_id.in_(select(lines.c.order_id)),
        )
        .order_by(PromotionRedemption.id)
    ).all()
    by_order: dict[UUID, list[tuple[UUID, UUID, Decimal]]] = defaultdict(list)
    for redemption_id, promotion_id, order_id, benefit in redemptions:
        by_order[order_id].append((redemption_id, promotion_id, _dec(benefit)))
    for (order_id, invoice_id), (passed, returned) in sums.items():
        order_number, whole = orders[order_id]
        if whole <= ZERO:
            continue
        number, dated = bills[invoice_id]
        for redemption_id, promotion_id, benefit in by_order.get(order_id, []):
            found.append(
                PassedOn(
                    redemption_id=redemption_id,
                    promotion_id=promotion_id,
                    invoice_id=invoice_id,
                    invoice_number=number,
                    invoice_date=dated,
                    order_number=order_number,
                    billed=benefit * min(passed / whole, Decimal("1")),
                    came_back=benefit * min(returned / whole, Decimal("1")),
                )
            )
    found.sort(key=lambda row: (row.invoice_date, row.invoice_number))
    return found
