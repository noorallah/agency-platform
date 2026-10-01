"""The largest purchase order a role may approve (BACKLOG 68 row 4).

Anybody holding ``PURCHASE_APPROVE`` could commit the firm to any amount. Each
role may now carry a maximum per firm (``role_purchase_approval_limits``); an
order whose amount is above the approver's limit is refused at approval with
the limit it needs, so it stays submitted, saved, for somebody allowed more.
The approval that clears it records the order's amount and the approver's
limit on the APPROVED event, beside the approver it already names.

The same rules as the discount limit (``app/sales_order/services/
discount_limit.py``, BACKLOG 64 row 3), deliberately: a person's limit is the
largest among their roles in the firm that have one; a person none of whose
roles has a limit is not limited, and neither is a platform administrator, so
a firm that never sets a limit behaves exactly as before.

**The amount is the order's grand total, tax included** -- what the firm
commits to pay the supplier, and the figure the approver reads on the order.
It is judged in the order's own figures; nothing here converts a currency.
"""

from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.common.firm_metadata import FirmMetadataReader
from app.core.exceptions import ValidationError
from app.core.utils.dates import utc_now
from app.purchase.models import RolePurchaseApprovalLimit

_CENT = Decimal("0.01")
PLATFORM_ADMIN_CODE = "platform_admin"


class PurchaseApprovalLimitService:
    """Each role's approval limit in a firm, and judging an approval by it."""

    def __init__(self, session: Session) -> None:
        """Hold the session the order is being approved on."""
        self._session = session

    def limits(self, firm_id: UUID) -> list[RolePurchaseApprovalLimit]:
        """Return the firm's limits, by role code."""
        return list(
            self._session.scalars(
                select(RolePurchaseApprovalLimit)
                .where(
                    RolePurchaseApprovalLimit.firm_id == firm_id,
                    RolePurchaseApprovalLimit.is_deleted.is_(False),
                )
                .order_by(RolePurchaseApprovalLimit.role_code)
            )
        )

    def replace_limits(
        self,
        items: Sequence[tuple[str, Decimal]],
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> list[RolePurchaseApprovalLimit]:
        """Replace the whole list; a role left out has no limit afterwards.

        Rows are updated in place by role code and the ones no longer named
        are soft-deleted first, so the partial unique index never sees two
        live rows for one role. Audited with both lists.
        """
        wanted: dict[str, Decimal] = {}
        for code, amount in items:
            key = code.strip()
            if not key:
                raise ValidationError("Every approval limit needs a role.")
            if key in wanted:
                raise ValidationError(f"Role {key} is listed twice.")
            wanted[key] = amount.quantize(_CENT, rounding=ROUND_HALF_UP)
        current = {row.role_code: row for row in self.limits(firm_id)}
        before = {code: str(row.max_order_amount) for code, row in current.items()}
        for code, stale in current.items():
            if code not in wanted:
                stale.is_deleted = True
                stale.deleted_at = utc_now()
                stale.deleted_by = actor_id
                stale.updated_by = actor_id
        self._session.flush()
        for code, amount in wanted.items():
            existing = current.get(code)
            if existing is None:
                self._session.add(
                    RolePurchaseApprovalLimit(
                        firm_id=firm_id,
                        role_code=code,
                        max_order_amount=amount,
                        created_by=actor_id,
                        updated_by=actor_id,
                    )
                )
            else:
                existing.max_order_amount = amount
                existing.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="role_purchase_approval_limits.replaced",
            entity_type="role_purchase_approval_limits",
            entity_id=uuid4(),
            actor_id=actor_id,
            firm_id=firm_id,
            before_data={"limits": before},
            after_data={"limits": {code: str(value) for code, value in wanted.items()}},
        )
        self._session.commit()
        return self.limits(firm_id)

    def limit_for(self, firm_id: UUID, user_id: UUID) -> Decimal | None:
        """Return the largest order a person may approve, or None for no limit."""
        codes = FirmMetadataReader(self._session).role_codes(firm_id, user_id)
        if PLATFORM_ADMIN_CODE in codes or not codes:
            return None
        values = [
            row.max_order_amount
            for row in self.limits(firm_id)
            if row.role_code in codes
        ]
        return max(values) if values else None

    def enforce(
        self, firm_id: UUID, approver_id: UUID, *, order_amount: Decimal
    ) -> dict[str, object] | None:
        """Refuse an approval above the approver's limit, else say what to keep.

        Returns the event details when somebody with a limit approved, so the
        timeline says who allowed what; nothing when the approver has none.
        """
        limit = self.limit_for(firm_id, approver_id)
        if limit is None:
            return None
        amount = Decimal(order_amount).quantize(_CENT, rounding=ROUND_HALF_UP)
        if amount > limit:
            raise ValidationError(
                f"This order's total of {amount} is above your approval limit "
                f"of {limit}. It needs approval by someone allowed at least "
                f"{amount}."
            )
        return {
            "approval_limit": {
                "order_amount": str(amount),
                "approver_limit": str(limit),
            }
        }
