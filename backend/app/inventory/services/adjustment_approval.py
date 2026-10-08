"""Approval for large stock adjustments (STK-8, decision A108).

Each role may carry a value limit. An adjustment or write-off worth more --
its quantity at the product's average cost -- is refused when posted
directly, naming the limit, and can be submitted as a request instead. A
person whose own limit covers it approves the request, which posts it
unchanged through the same service; a rejection keeps the reason. A firm
that sets no limit behaves exactly as before.
"""

import json
from collections.abc import Sequence
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.common.firm_metadata import FirmMetadataReader
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.inventory.models import ProductValuation
from app.inventory.models.adjustment_approval import (
    RoleStockAdjustmentLimit,
    StockAdjustmentRequest,
)
from app.inventory.schemas import InventoryAdjustmentCreate, StockWriteOffCreate

_CENT = Decimal("0.01")
PLATFORM_ADMIN_CODE = "platform_admin"
Kind = Literal["ADJUSTMENT", "WRITE_OFF"]


class StockAdjustmentLimitItem(BaseModel):
    """The largest stock adjustment one role may post."""

    model_config = ConfigDict(extra="forbid")

    role_code: str = Field(min_length=1, max_length=100)
    max_value: Decimal = Field(ge=0, max_digits=18, decimal_places=2)


class StockAdjustmentLimitsWrite(BaseModel):
    """Replace the firm's whole list of limits."""

    model_config = ConfigDict(extra="forbid")

    limits: list[StockAdjustmentLimitItem] = Field(default_factory=list)


class StockAdjustmentRequestWrite(BaseModel):
    """Submit an adjustment or a write-off for approval."""

    model_config = ConfigDict(extra="forbid")

    kind: Kind
    adjustment: InventoryAdjustmentCreate | None = None
    write_off: StockWriteOffCreate | None = None

    @model_validator(mode="after")
    def _one_body(self) -> "StockAdjustmentRequestWrite":
        """Require the body the kind names, and only that one."""
        wanted = self.adjustment if self.kind == "ADJUSTMENT" else self.write_off
        other = self.write_off if self.kind == "ADJUSTMENT" else self.adjustment
        if wanted is None or other is not None:
            raise ValueError(
                "Send the adjustment for an ADJUSTMENT, or the write-off for a "
                "WRITE_OFF, and not both."
            )
        return self


class StockAdjustmentRejectWrite(BaseModel):
    """Why a request is turned down."""

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=1000)


class StockAdjustmentRequestResponse(BaseModel):
    """One request and what became of it."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    kind: str
    product_id: UUID
    warehouse_id: UUID
    quantity: Decimal
    estimated_value: Decimal
    status: str
    requested_by: UUID | None
    requested_at: datetime
    decided_by: UUID | None
    decided_at: datetime | None
    decision_remarks: str | None
    transaction_id: UUID | None
    payload: dict[str, object]
    version: int


class StockAdjustmentApprovalService:
    """Keep the limits, judge a post by them, and decide requests."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request's session."""
        self._session = session

    # -- limits ---------------------------------------------------------
    def limits(self, firm_id: UUID) -> list[RoleStockAdjustmentLimit]:
        """Return the firm's limits, by role code."""
        return list(
            self._session.scalars(
                select(RoleStockAdjustmentLimit)
                .where(
                    RoleStockAdjustmentLimit.firm_id == firm_id,
                    RoleStockAdjustmentLimit.is_deleted.is_(False),
                )
                .order_by(RoleStockAdjustmentLimit.role_code)
            )
        )

    def replace_limits(
        self,
        items: Sequence[StockAdjustmentLimitItem],
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> list[RoleStockAdjustmentLimit]:
        """Replace the whole list; a role left out has no limit afterwards."""
        wanted: dict[str, Decimal] = {}
        for item in items:
            key = item.role_code.strip()
            if key in wanted:
                raise ValidationError(f"Role {key} is listed twice.")
            wanted[key] = item.max_value.quantize(_CENT, rounding=ROUND_HALF_UP)
        current = {row.role_code: row for row in self.limits(firm_id)}
        before = {code: str(row.max_value) for code, row in current.items()}
        for code, stale in current.items():
            if code not in wanted:
                stale.is_deleted = True
                stale.deleted_at = utc_now()
                stale.updated_by = actor_id
        self._session.flush()
        for code, value in wanted.items():
            existing = current.get(code)
            if existing is None:
                self._session.add(
                    RoleStockAdjustmentLimit(
                        firm_id=firm_id,
                        role_code=code,
                        max_value=value,
                        created_by=actor_id,
                        updated_by=actor_id,
                    )
                )
            else:
                existing.max_value = value
                existing.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="role_stock_adjustment_limits.replaced",
            entity_type="role_stock_adjustment_limits",
            entity_id=uuid4(),
            actor_id=actor_id,
            firm_id=firm_id,
            before_data={"limits": before},
            after_data={"limits": {code: str(value) for code, value in wanted.items()}},
        )
        self._session.commit()
        return self.limits(firm_id)

    def limit_for(self, firm_id: UUID, user_id: UUID) -> Decimal | None:
        """Return the most a person may move in one post, or None for no limit."""
        codes = FirmMetadataReader(self._session).role_codes(firm_id, user_id)
        if PLATFORM_ADMIN_CODE in codes or not codes:
            return None
        values = [
            row.max_value for row in self.limits(firm_id) if row.role_code in codes
        ]
        return max(values) if values else None

    def estimate(self, firm_id: UUID, product_id: UUID, quantity: Decimal) -> Decimal:
        """Return what a quantity is worth at the product's average cost."""
        valuation = self._session.scalar(
            select(ProductValuation).where(
                ProductValuation.firm_id == firm_id,
                ProductValuation.product_id == product_id,
            )
        )
        cost = Decimal(str(valuation.average_cost)) if valuation else Decimal("0")
        return (abs(quantity) * cost).quantize(_CENT, rounding=ROUND_HALF_UP)

    def assert_within_limit(
        self, firm_id: UUID, actor_id: UUID, *, product_id: UUID, quantity: Decimal
    ) -> None:
        """Refuse a direct post above the poster's limit.

        Raises:
            ValidationError: Naming the value and the limit, and that it can
                be submitted for approval.

        """
        limit = self.limit_for(firm_id, actor_id)
        if limit is None:
            return
        value = self.estimate(firm_id, product_id, quantity)
        if value > limit:
            raise ValidationError(
                f"This moves stock worth {value}, above your limit of {limit}. "
                "Submit it for approval instead.",
                details={"needs_approval": True, "estimated_value": str(value)},
            )

    # -- requests -------------------------------------------------------
    def submit(
        self, data: StockAdjustmentRequestWrite, *, firm_id: UUID, actor_id: UUID
    ) -> StockAdjustmentRequestResponse:
        """Record one request for approval."""
        body = data.adjustment if data.kind == "ADJUSTMENT" else data.write_off
        assert body is not None
        from app.inventory.services import InventoryService

        inventory = InventoryService(self._session)
        inventory.assert_postable(body, firm_scope=firm_id)
        # In the stock unit: three boxes of twelve are worth 36 pieces.
        moved = inventory.moved_base_quantity(body, firm_scope=firm_id)
        row = StockAdjustmentRequest(
            firm_id=firm_id,
            kind=data.kind,
            product_id=body.product_id,
            warehouse_id=body.warehouse_id,
            quantity=moved,
            estimated_value=self.estimate(firm_id, body.product_id, moved),
            payload_json=body.model_dump_json(),
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._session.flush()
        self._audit("stock_adjustment_request.submitted", row, actor_id)
        self._session.commit()
        return self.response(row)

    def list_requests(
        self, firm_id: UUID, *, status: str = "PENDING"
    ) -> list[StockAdjustmentRequestResponse]:
        """Return the firm's requests in one status, newest first."""
        rows = self._session.scalars(
            select(StockAdjustmentRequest)
            .where(
                StockAdjustmentRequest.firm_id == firm_id,
                StockAdjustmentRequest.status == status,
                StockAdjustmentRequest.is_deleted.is_(False),
            )
            .order_by(
                StockAdjustmentRequest.created_at.desc(),
                StockAdjustmentRequest.id.desc(),
            )
            .limit(500)
        ).all()
        # What it is worth now is what an approver is asked to let go; a
        # decided request keeps the figure it was decided at.
        worth = self._worth_now(firm_id, rows) if status == "PENDING" else {}
        return [self.response(row, worth.get(row.id)) for row in rows]

    def _worth_now(
        self, firm_id: UUID, rows: Sequence[StockAdjustmentRequest]
    ) -> dict[UUID, Decimal]:
        """Return each request's value at today's average cost, in one read.

        A request keeps the quantity it was asked for and waits; the cost of
        the goods does not. One asked for at 400 and approved after a dearer
        receipt moved 4,000 under a limit of 500 (D-STK-59).
        """
        if not rows:
            return {}
        costs = {
            product_id: Decimal(str(cost))
            for product_id, cost in self._session.execute(
                select(
                    ProductValuation.product_id, ProductValuation.average_cost
                ).where(
                    ProductValuation.firm_id == firm_id,
                    ProductValuation.product_id.in_({row.product_id for row in rows}),
                )
            )
        }
        return {
            row.id: (
                abs(row.quantity) * costs.get(row.product_id, Decimal("0"))
            ).quantize(_CENT, rounding=ROUND_HALF_UP)
            for row in rows
        }

    def get(self, request_id: UUID, *, firm_id: UUID) -> StockAdjustmentRequest:
        """Return one of the firm's requests."""
        row = self._session.get(StockAdjustmentRequest, request_id)
        if row is None or row.is_deleted or row.firm_id != firm_id:
            raise ResourceNotFoundError("Adjustment request not found.")
        return row

    def approve(
        self, request_id: UUID, *, firm_id: UUID, actor_id: UUID
    ) -> StockAdjustmentRequestResponse:
        """Post a pending request as it was typed, under the approver's limit.

        Raises:
            ValidationError: If it is not pending, or worth more than the
                approver may move.

        """
        from app.inventory.services import InventoryService

        row = self._pending(request_id, firm_id)
        # Judged at what the goods are worth today, not on the day of asking.
        worth = self._worth_now(firm_id, [row])[row.id]
        limit = self.limit_for(firm_id, actor_id)
        if limit is not None and worth > limit:
            raise ValidationError(
                f"This request moves stock worth {worth}, above "
                f"your limit of {limit}. It needs somebody allowed more."
            )
        row.estimated_value = worth
        row.status = "APPROVED"
        row.decided_by = actor_id
        row.decided_at = utc_now()
        row.updated_by = actor_id
        self._audit("stock_adjustment_request.approved", row, actor_id)
        inventory = InventoryService(self._session)
        if row.kind == "ADJUSTMENT":
            transaction = inventory.create_adjustment(
                InventoryAdjustmentCreate.model_validate_json(row.payload_json),
                firm_scope=firm_id,
                actor_id=actor_id,
                enforce_limit=False,
            )
        else:
            transaction = inventory.write_off_stock(
                StockWriteOffCreate.model_validate_json(row.payload_json),
                firm_scope=firm_id,
                actor_id=actor_id,
                enforce_limit=False,
            )
        row.transaction_id = transaction.id
        self._session.commit()
        return self.response(row)

    def reject(
        self, request_id: UUID, reason: str, *, firm_id: UUID, actor_id: UUID
    ) -> StockAdjustmentRequestResponse:
        """Turn a pending request down, keeping why."""
        row = self._pending(request_id, firm_id)
        if not reason.strip():
            raise ValidationError("Say why the request is rejected.")
        row.status = "REJECTED"
        row.decided_by = actor_id
        row.decided_at = utc_now()
        row.decision_remarks = reason.strip()
        row.updated_by = actor_id
        self._audit("stock_adjustment_request.rejected", row, actor_id)
        self._session.commit()
        return self.response(row)

    def response(
        self, row: StockAdjustmentRequest, worth: Decimal | None = None
    ) -> StockAdjustmentRequestResponse:
        """Shape one request for the wire, at ``worth`` where one is given."""
        return StockAdjustmentRequestResponse(
            id=row.id,
            kind=row.kind,
            product_id=row.product_id,
            warehouse_id=row.warehouse_id,
            quantity=row.quantity,
            estimated_value=row.estimated_value if worth is None else worth,
            status=row.status,
            requested_by=row.created_by,
            requested_at=row.created_at,
            decided_by=row.decided_by,
            decided_at=row.decided_at,
            decision_remarks=row.decision_remarks,
            transaction_id=row.transaction_id,
            payload=json.loads(row.payload_json),
            version=row.version,
        )

    def _pending(self, request_id: UUID, firm_id: UUID) -> StockAdjustmentRequest:
        """Return a request still waiting for a decision."""
        row = self.get(request_id, firm_id=firm_id)
        if row.status != "PENDING":
            raise ValidationError(f"This request was already {row.status.lower()}.")
        return row

    def _audit(self, action: str, row: StockAdjustmentRequest, actor_id: UUID) -> None:
        """Write one audit row for a request."""
        record_audit(
            self._session,
            action=action,
            entity_type="stock_adjustment_request",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=row.firm_id,
            after_data={
                "kind": row.kind,
                "quantity": str(row.quantity),
                "estimated_value": str(row.estimated_value),
                "status": row.status,
            },
        )
