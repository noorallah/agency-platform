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
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.common.firm_metadata import FirmMetadataReader
from app.core.exceptions import ValidationError
from app.core.utils.dates import utc_now
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

    @property
    def percent(self) -> Decimal:
        """Return the typed discount as a share of the gross, in percent."""
        if self.gross <= _ZERO:
            return _ZERO
        return (self.typed_discount * _HUNDRED / self.gross).quantize(
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


def order_discounts(
    lines: Iterable[object], *, bill_discount_source: str | None
) -> list[DiscountedLine]:
    """Read sales order lines; the bill share counts unless an offer set it."""
    bill_typed = bill_discount_source not in ("promotion", "none")
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
                + (share if bill_typed else _ZERO),
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
            )
        )
    return result


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

    def enforce(
        self,
        firm_id: UUID,
        approver_id: UUID,
        lines: Sequence[DiscountedLine],
    ) -> dict[str, object] | None:
        """Refuse an approval above the approver's limit, else say what to keep.

        Returns the event details when a typed discount was approved by
        somebody with a limit, so the timeline says who allowed what; nothing
        when no discount was typed or the approver has no limit.
        """
        typed = [line for line in lines if line.percent > _ZERO]
        if not typed:
            return None
        widest = max(typed, key=lambda line: line.percent)
        limit = self.limit_for(firm_id, approver_id)
        if limit is None:
            return None
        if widest.percent > limit:
            raise ValidationError(
                f"Line {widest.line_number} carries a discount of "
                f"{widest.percent}%, above your limit of {limit}%. It needs "
                f"approval by someone allowed at least {widest.percent}%."
            )
        return {
            "discount_approval": {
                "typed_discount_percent": str(widest.percent),
                "approver_limit_percent": str(limit),
            }
        }
