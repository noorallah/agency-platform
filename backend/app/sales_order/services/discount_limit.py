"""The largest discount a role may give on its own (BACKLOG 64 row 3).

Anybody who could edit an order could type any discount. Each role may now
carry a maximum per firm (``role_discount_limits``); a document whose typed
discount is above the approver's limit is refused at approval with the limit
it needs, so it waits, saved, for somebody allowed more. The approval that
clears it records the discount and the approver's limit on the APPROVED event,
beside the approver it already names.

**Only a typed discount counts.** A price list's ladder, a promotion and the
customer's or group's standing rate are arrangements the firm made, and the
discount source each line stores says which branch was taken
(``app/core/utils/pricing.py``). An order's bill discount is typed unless a
promotion set it. A bill's is typed where the bill stated it; the share it
inherited from its order is handed over as nothing by the caller, like a bill
line that inherited its order's discount, which was judged when that order
was approved (D-PRC-1).

**Whose limit.** The approver's: the largest among their roles in the firm
that have one. A person none of whose roles has a limit is not limited, and
neither is a platform administrator -- a firm that never sets a limit behaves
exactly as before.

Judged per line on (typed line discount + typed bill-discount share) / gross,
because a 2% bill discount on top of a 9% line discount is 11% off that line.

**A price typed below the customer's is a discount by another name** (D-PRC-2).
Only the discount boxes were judged, so with a 5% limit a typed 50% was refused
and the same goods at half the price with no discount were approved, delivered
and billed below cost. The limit is now judged on the **whole reduction** from
the price the customer would otherwise pay -- what the price ranking gives this
customer for this product, quantity and date before anything is typed
(``UnitPriceResolver``: price list, batch rate, price level, product price) --
to what the line charges: the cut in the price and the typed discounts
together, as a share of the line at the customer's price. A price typed at or
above the customer's is not a discount, and the customer's own cheaper list or
level is their price, not the person's doing. On a bill of documents the
customer's price is the one its order line agreed, so a price cut on the bill
is judged where it is billed.

**A delivery note is judged for what it types** (D-PRC-23). A discount typed
on a note reached the bill as inherited and was judged nowhere, so the person
the limit binds gave 30% by typing it one document later. A note line that is
cheaper than the order line it continues -- a larger discount, a larger share
of a discount on the whole note, or a lower price -- is judged at the note's
approval (``note_reduction``), and the APPROVED event records that it was
(``NOTE_REDUCTION_JUDGED``). A bill treats as inherited only what the order
agreed, or what a note so judged holds: a reduction from a note with no such
record is judged at the bill. A note that types nothing is never judged.

**A line sold in another unit is judged in that unit** (D-PRC-24). The
ranking's price is per stock unit, so the customer's price for a box is that
price times the stock units the line's own conversion factor says a box holds;
then the line is judged exactly as a stock-unit line is. A product with no
selling price still has no customer's price to cut.
"""

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.common.firm_metadata import FirmMetadataReader
from app.core.exceptions import ValidationError
from app.core.utils.dates import utc_now
from app.pricing.services.unit_price import UnitPriceResolver
from app.sales_order.models import RoleDiscountLimit

_ZERO = Decimal("0")
_HUNDRED = Decimal("100")
_CENT = Decimal("0.01")
#: The sources `resolve_line_discount` gives a rate somebody typed.
TYPED_SOURCES = frozenset({"percent", "amount"})
PLATFORM_ADMIN_CODE = "platform_admin"


@dataclass(frozen=True, slots=True)
class DiscountedLine:
    """What one line gave away by somebody's hand."""

    line_number: int
    gross: Decimal
    typed_discount: Decimal
    #: The quantity charged and the price it is charged at.
    quantity: Decimal = _ZERO
    price: Decimal | None = None
    #: The price the customer would otherwise pay, or None where the line's
    #: price is not judged.
    customer_price: Decimal | None = None

    @property
    def price_cut(self) -> Decimal:
        """Return what a price typed below the customer's took off the line."""
        if (
            self.price is None
            or self.customer_price is None
            or self.quantity <= _ZERO
            or self.customer_price <= self.price
        ):
            return _ZERO
        return (self.customer_price - self.price) * self.quantity

    @property
    def percent(self) -> Decimal:
        """Return everything typed off the line, in percent of its full value.

        The full value is the line at the customer's price where the price
        was cut, and its gross otherwise.
        """
        full = self.gross + self.price_cut
        if full <= _ZERO:
            return _ZERO
        return ((self.typed_discount + self.price_cut) * _HUNDRED / full).quantize(
            _CENT, rounding=ROUND_HALF_UP
        )


def _typed_line(source: str | None, amount: Decimal) -> Decimal:
    """Return the line's own discount if somebody typed it, else nothing.

    NULL is a line written before the source was recorded; one that carries a
    discount is judged as typed, the way an editor reopening it keeps it.
    """
    if source in TYPED_SOURCES or (source is None and amount > _ZERO):
        return amount
    return _ZERO


def _decimal(value: object) -> Decimal | None:
    """Return a stored figure as a Decimal, or None where there is none."""
    return None if value is None else Decimal(str(value))


def order_discounts(
    lines: Iterable[object],
    *,
    bill_discount_source: str | None,
    customer_prices: Mapping[int, Decimal] | None = None,
) -> list[DiscountedLine]:
    """Read sales order lines; the bill share counts unless an offer set it.

    ``customer_prices`` names, by line number, the price the customer would
    otherwise pay (`DiscountLimitService.customer_prices`).
    """
    bill_typed = bill_discount_source not in ("promotion", "none")
    prices = customer_prices or {}
    result: list[DiscountedLine] = []
    for line in lines:
        amount = Decimal(getattr(line, "discount_amount", None) or _ZERO)
        share = Decimal(getattr(line, "bill_discount_amount", None) or _ZERO)
        number = int(getattr(line, "line_number", 0))
        result.append(
            DiscountedLine(
                line_number=number,
                gross=Decimal(getattr(line, "gross_amount", None) or _ZERO),
                typed_discount=_typed_line(
                    getattr(line, "discount_source", None), amount
                )
                + (share if bill_typed else _ZERO),
                quantity=Decimal(getattr(line, "quantity", None) or _ZERO),
                price=_decimal(getattr(line, "unit_price", None)),
                customer_price=prices.get(number),
            )
        )
    return result


def invoice_discounts(lines: Iterable[object]) -> list[DiscountedLine]:
    """Read bill lines; the caller zeroes a bill-discount share nobody typed."""
    result: list[DiscountedLine] = []
    for line in lines:
        amount = Decimal(getattr(line, "discount_amount", None) or _ZERO)
        share = Decimal(getattr(line, "bill_discount_amount", None) or _ZERO)
        result.append(
            DiscountedLine(
                line_number=int(getattr(line, "line_number", 0)),
                gross=Decimal(getattr(line, "gross_amount", None) or _ZERO),
                typed_discount=_typed_line(
                    getattr(line, "discount_source", None), amount
                )
                + share,
                quantity=Decimal(
                    getattr(line, "current_invoice_quantity", None) or _ZERO
                ),
                price=_decimal(getattr(line, "unit_price", None)),
                # Named by the caller, who knows what the line continues.
                customer_price=_decimal(getattr(line, "customer_price", None)),
            )
        )
    return result


#: The key a delivery note's APPROVED event carries when the note typed a
#: reduction and its approval judged it. A bill reads it: only a reduction so
#: recorded is inherited rather than judged again (D-PRC-23).
NOTE_REDUCTION_JUDGED = "typed_reduction_judged"
#: A slice of an amount and its plain pro-rata share differ by rounding
#: alone; anything within a paisa is the inheritance, not a decision.
_INHERITED_WITHIN = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class NoteReduction:
    """What a delivery note line took off beyond what its order line agreed."""

    line: DiscountedLine
    #: The note's own line discount is larger than the order line's.
    typed_line: bool
    #: The note's share of a discount on the whole note is larger than the
    #: order line's share of the order's.
    typed_bill: bool


def note_reduction(note_line: object, order_line: object) -> NoteReduction | None:
    """Return what a note line typed that makes it cheaper than its order line.

    A note that says nothing ships the order line's price, its discount and
    its share of the order's bill discount by the quantity shipped, and is
    never judged for them: they were the order's, judged at its approval.
    What the note *types* replaces what it would have inherited; where that
    leaves the line cheaper than the same quantity on the order, it is the
    typing person's doing (D-PRC-23) and is judged as on an order -- a typed
    line discount and a typed bill-discount share in whole, a lower price
    against the order's price.

    Args:
        note_line: The delivery note line.
        order_line: The sales order line it continues.

    Returns:
        The line for the judge and which of its discounts were typed, or
        None where the note line is no cheaper than its order line agreed.

    """

    def figure(row: object, name: str) -> Decimal:
        """Return a stored figure of a line, nothing as zero."""
        return Decimal(str(getattr(row, name, None) or _ZERO))

    shipped = figure(note_line, "current_delivery_quantity")
    ordered = figure(order_line, "quantity")
    if shipped <= _ZERO or ordered <= _ZERO:
        return None
    price = figure(note_line, "unit_price")
    agreed_price = figure(order_line, "unit_price")
    gross = figure(note_line, "gross_amount")
    line_discount = figure(note_line, "discount_amount")
    bill_share = figure(note_line, "bill_discount_amount")
    # At the order's price the order's amount is shared by quantity; at
    # another price its rate is what silence inherits.
    agreed_at_order_price = figure(order_line, "discount_amount") * shipped / ordered
    agreed_line = (
        agreed_at_order_price
        if price == agreed_price
        else gross * figure(order_line, "discount_percent") / _HUNDRED
    )
    agreed_bill = figure(order_line, "bill_discount_amount") * shipped / ordered
    charged = gross - line_discount - bill_share
    agreed = shipped * agreed_price - agreed_at_order_price - agreed_bill
    if charged >= agreed - _INHERITED_WITHIN:
        return None
    typed_line = line_discount > agreed_line + _INHERITED_WITHIN
    typed_bill = bill_share > agreed_bill + _INHERITED_WITHIN
    if not typed_line and not typed_bill and price >= agreed_price:
        return None
    return NoteReduction(
        line=DiscountedLine(
            line_number=int(getattr(note_line, "line_number", 0)),
            gross=gross,
            typed_discount=(line_discount if typed_line else _ZERO)
            + (bill_share if typed_bill else _ZERO),
            quantity=shipped,
            price=price,
            customer_price=agreed_price,
        ),
        typed_line=typed_line,
        typed_bill=typed_bill,
    )


class DiscountLimitService:
    """Each role's discount limit in a firm, and judging an approval by it."""

    def __init__(self, session: Session) -> None:
        """Hold the session the document is being written on."""
        self._session = session

    def limits(self, firm_id: UUID) -> list[RoleDiscountLimit]:
        """Return the firm's limits, by role code."""
        return list(
            self._session.scalars(
                select(RoleDiscountLimit)
                .where(
                    RoleDiscountLimit.firm_id == firm_id,
                    RoleDiscountLimit.is_deleted.is_(False),
                )
                .order_by(RoleDiscountLimit.role_code)
            )
        )

    def replace_limits(
        self,
        items: Sequence[tuple[str, Decimal]],
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> list[RoleDiscountLimit]:
        """Replace the whole list; a role left out has no limit afterwards.

        Rows are updated in place by role code and the ones no longer named
        are soft-deleted, so the partial unique index never sees two live rows
        for one role. Audited with both lists.
        """
        wanted: dict[str, Decimal] = {}
        for code, percent in items:
            key = code.strip()
            if not key:
                raise ValidationError("Every discount limit needs a role.")
            if key in wanted:
                raise ValidationError(f"Role {key} is listed twice.")
            wanted[key] = percent.quantize(_CENT, rounding=ROUND_HALF_UP)
        current = {row.role_code: row for row in self.limits(firm_id)}
        before = {code: str(row.max_discount_percent) for code, row in current.items()}
        for code, stale in current.items():
            if code not in wanted:
                stale.is_deleted = True
                stale.deleted_at = utc_now()
                stale.deleted_by = actor_id
                stale.updated_by = actor_id
        self._session.flush()
        for code, percent in wanted.items():
            existing = current.get(code)
            if existing is None:
                self._session.add(
                    RoleDiscountLimit(
                        firm_id=firm_id,
                        role_code=code,
                        max_discount_percent=percent,
                        created_by=actor_id,
                        updated_by=actor_id,
                    )
                )
            else:
                existing.max_discount_percent = percent
                existing.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="role_discount_limits.replaced",
            entity_type="role_discount_limits",
            entity_id=uuid4(),
            actor_id=actor_id,
            firm_id=firm_id,
            before_data={"limits": before},
            after_data={"limits": {code: str(value) for code, value in wanted.items()}},
        )
        self._session.commit()
        return self.limits(firm_id)

    def limit_for(self, firm_id: UUID, user_id: UUID) -> Decimal | None:
        """Return the most a person may discount on their own, or None."""
        codes = FirmMetadataReader(self._session).role_codes(firm_id, user_id)
        if PLATFORM_ADMIN_CODE in codes or not codes:
            return None
        values = [
            row.max_discount_percent
            for row in self.limits(firm_id)
            if row.role_code in codes
        ]
        return max(values) if values else None

    def customer_prices(
        self,
        lines: Iterable[object],
        *,
        firm_id: UUID,
        customer_id: UUID | None,
        territory_id: UUID | None,
        on: date,
    ) -> dict[int, Decimal]:
        """Return, by line number, the price each order line would start at.

        What the ranking gives this customer for the product, the quantity
        and the date before anything is typed, the batch the line is pinned
        to included -- **in the unit the line is sold in**: the ranking's
        price per stock unit times the line's own conversion factor, the one
        its stock moves at. A line by the box was left out, because the
        ranking's price carries no unit, so 2 BOX of 12 at a typed 600.00 a
        box, half of twelve pieces at 100.00, was approved by somebody
        limited to 5% (D-PRC-24). A line that charges nothing is left out.
        """
        resolver = UnitPriceResolver(
            self._session,
            firm_id=firm_id,
            customer_id=customer_id,
            territory_id=territory_id,
            on=on,
        )
        prices: dict[int, Decimal] = {}
        for line in lines:
            quantity = Decimal(getattr(line, "quantity", None) or _ZERO)
            if quantity <= _ZERO:
                continue
            prices[int(getattr(line, "line_number", 0))] = resolver.price_at_factor(
                getattr(line, "product_id"),  # noqa: B009
                quantity,
                factor=Decimal(str(getattr(line, "conversion_factor", None) or 1)),
                batch_id=getattr(line, "pinned_batch_id", None),
            ).price
        return prices

    def enforce(
        self,
        firm_id: UUID,
        approver_id: UUID,
        lines: Sequence[DiscountedLine] | Callable[[], Sequence[DiscountedLine]],
        *,
        document: str | None = None,
    ) -> dict[str, object] | None:
        """Refuse an approval above the approver's limit, else say what to keep.

        Returns the event details when a typed reduction was approved by
        somebody with a limit, so the timeline says who allowed what; nothing
        when nothing was typed off or the approver has no limit. ``lines``
        may be a callable, read only once the approver is known to have a
        limit: working out the customer's prices costs a firm with no limits
        nothing. ``document`` names the document in the refusal where the
        reader may not be looking at it -- "delivery note DN-1" -- and the
        sentence is otherwise the one an order is refused in.
        """
        limit = self.limit_for(firm_id, approver_id)
        if limit is None:
            return None
        judged = lines() if callable(lines) else lines
        typed = [line for line in judged if line.percent > _ZERO]
        if not typed:
            return None
        widest = max(typed, key=lambda line: line.percent)
        cut = widest.price_cut > _ZERO
        price = Decimal(widest.price or _ZERO).quantize(_CENT, ROUND_HALF_UP)
        usual = Decimal(widest.customer_price or _ZERO).quantize(_CENT, ROUND_HALF_UP)
        if widest.percent > limit:
            subject = f"Line {widest.line_number}" + (
                f" of {document}" if document else ""
            )
            if cut:
                besides = (
                    ", with a typed discount besides"
                    if widest.typed_discount > _ZERO
                    else ""
                )
                raise ValidationError(
                    f"{subject} is priced at {price} where the "
                    f"customer's price is {usual}{besides}: {widest.percent}% off "
                    f"in all, above your limit of {limit}%. It needs approval by "
                    f"someone allowed at least {widest.percent}%."
                )
            raise ValidationError(
                f"{subject} carries a discount of "
                f"{widest.percent}%, above your limit of {limit}%. It needs "
                f"approval by someone allowed at least {widest.percent}%."
            )
        approval = {
            "typed_discount_percent": str(widest.percent),
            "approver_limit_percent": str(limit),
        }
        if cut:
            approval["typed_price"] = str(price)
            approval["customer_price"] = str(usual)
        return {"discount_approval": approval}
