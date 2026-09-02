"""Create, read and supersede promotions.

Kept apart from the engine that evaluates them, because the two have different
transaction rules: this owns its commits, and `PromotionService.evaluate` must
never commit at all.

An ACTIVE promotion is superseded rather than edited, exactly as a tax rule is.
A document priced in March has to stay explicable in September, and it cannot
be if the offer behind it was quietly rewritten.
"""

from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ConflictError, ResourceNotFoundError
from app.promotions.models import Promotion, PromotionAction, PromotionCondition
from app.promotions.schemas import (
    PromotionActionResponse,
    PromotionActionType,
    PromotionConditionResponse,
    PromotionResponse,
    PromotionStatus,
    PromotionWrite,
)


class PromotionCrudService:
    """Manage a firm's promotion catalogue."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request unit of work."""
        self._session = session

    def list_promotions(
        self,
        *,
        firm_scope: UUID,
        page: int,
        page_size: int,
        search: str | None = None,
        status: PromotionStatus | None = None,
    ) -> tuple[list[Promotion], int]:
        """List a firm's promotions, newest revision of each first."""
        statement = select(Promotion).where(
            Promotion.firm_id == firm_scope, Promotion.is_deleted.is_(False)
        )
        count = (
            select(func.count())
            .select_from(Promotion)
            .where(Promotion.firm_id == firm_scope, Promotion.is_deleted.is_(False))
        )
        if status is not None:
            statement = statement.where(Promotion.status == status.value)
            count = count.where(Promotion.status == status.value)
        if search:
            token = f"%{search.strip()}%"
            statement = statement.where(Promotion.name.ilike(token))
            count = count.where(Promotion.name.ilike(token))
        rows = list(
            self._session.scalars(
                statement.order_by(
                    Promotion.priority.asc(),
                    Promotion.code.asc(),
                    Promotion.version_number.desc(),
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        return rows, int(self._session.scalar(count) or 0)

    def get_promotion(self, promotion_id: UUID, *, firm_scope: UUID) -> Promotion:
        """Fetch one promotion, scoped to the firm."""
        row = self._session.scalar(
            select(Promotion).where(
                Promotion.id == promotion_id,
                Promotion.firm_id == firm_scope,
                Promotion.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Promotion not found.")
        return row

    def create_promotion(
        self, data: PromotionWrite, *, firm_id: UUID, actor_id: UUID
    ) -> Promotion:
        """Record a new promotion at version one."""
        self._assert_code_is_free(data.code, firm_id=firm_id)
        row = Promotion(
            firm_id=firm_id,
            code=data.code.strip().upper(),
            name=data.name,
            description=data.description,
            priority=data.priority,
            status=data.status.value,
            allow_stacking=data.allow_stacking,
            effective_from=data.effective_from,
            effective_to=data.effective_to,
            version_group_id=uuid4(),
            version_number=1,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._session.flush()
        self._replace_children(row, data, actor_id=actor_id)
        record_audit(
            self._session,
            action="promotion.created",
            entity_type="promotion",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={"code": row.code, "status": row.status},
        )
        self._session.commit()
        return row

    def update_promotion(
        self,
        promotion_id: UUID,
        data: PromotionWrite,
        *,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> Promotion:
        """Edit a draft in place, or supersede anything already published.

        The same rule the tax engine follows: a live promotion is never
        rewritten, because documents priced under it have to stay explicable.
        """
        row = self.get_promotion(promotion_id, firm_scope=firm_scope)
        if row.status == PromotionStatus.DRAFT.value:
            row.name = data.name
            row.description = data.description
            row.priority = data.priority
            row.status = data.status.value
            row.allow_stacking = data.allow_stacking
            row.effective_from = data.effective_from
            row.effective_to = data.effective_to
            row.updated_by = actor_id
            self._replace_children(row, data, actor_id=actor_id)
            record_audit(
                self._session,
                action="promotion.updated",
                entity_type="promotion",
                entity_id=row.id,
                actor_id=actor_id,
                firm_id=firm_scope,
                after_data={"code": row.code, "status": row.status},
            )
            self._session.commit()
            return row

        successor = Promotion(
            firm_id=firm_scope,
            code=row.code,
            name=data.name,
            description=data.description,
            priority=data.priority,
            status=data.status.value,
            allow_stacking=data.allow_stacking,
            effective_from=data.effective_from,
            effective_to=data.effective_to,
            version_group_id=row.version_group_id,
            version_number=row.version_number + 1,
            supersedes_promotion_id=row.id,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(successor)
        self._session.flush()
        self._replace_children(successor, data, actor_id=actor_id)
        row.status = PromotionStatus.INACTIVE.value
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="promotion.superseded",
            entity_type="promotion",
            entity_id=successor.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data={"version_number": row.version_number},
            after_data={"version_number": successor.version_number},
        )
        self._session.commit()
        return successor

    def delete_promotion(
        self, promotion_id: UUID, *, firm_scope: UUID, actor_id: UUID
    ) -> None:
        """Retire a promotion without removing what it already priced."""
        row = self.get_promotion(promotion_id, firm_scope=firm_scope)
        row.is_deleted = True
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="promotion.deleted",
            entity_type="promotion",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data={"code": row.code, "status": row.status},
        )
        self._session.commit()

    def _assert_code_is_free(self, code: str, *, firm_id: UUID) -> None:
        """Refuse a second promotion carrying an existing code."""
        existing = self._session.scalar(
            select(Promotion).where(
                Promotion.firm_id == firm_id,
                Promotion.code == code.strip().upper(),
                Promotion.is_deleted.is_(False),
            )
        )
        if existing is not None:
            raise ConflictError("A promotion with this code already exists.")

    def _replace_children(
        self, row: Promotion, data: PromotionWrite, *, actor_id: UUID
    ) -> None:
        """Rewrite a promotion's conditions and actions."""
        for existing in [*row.conditions, *row.actions]:
            existing.is_deleted = True
            existing.updated_by = actor_id
        self._session.flush()
        for condition in data.conditions:
            self._session.add(
                PromotionCondition(
                    firm_id=row.firm_id,
                    promotion_id=row.id,
                    sequence=condition.sequence,
                    field_key=condition.field_key.value,
                    operator=condition.operator.value,
                    value_text=condition.value_text,
                    value_number=condition.value_number,
                    value_date=condition.value_date,
                    value_boolean=condition.value_boolean,
                    value_json=condition.value_json,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
        for action in data.actions:
            self._session.add(
                PromotionAction(
                    firm_id=row.firm_id,
                    promotion_id=row.id,
                    sequence=action.sequence,
                    action_type=action.action_type.value,
                    parameters=self._parameters(action),
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
        self._session.flush()
        self._session.refresh(row)

    @staticmethod
    def _parameters(action: object) -> dict[str, object]:
        """Store only the numbers this action type actually reads."""
        kind = getattr(action, "action_type", None)
        if kind in {
            PromotionActionType.LINE_DISCOUNT_PERCENT,
            PromotionActionType.BILL_DISCOUNT_PERCENT,
        }:
            return {"percent": str(getattr(action, "percent", None))}
        if kind in {
            PromotionActionType.LINE_DISCOUNT_AMOUNT,
            PromotionActionType.BILL_DISCOUNT_AMOUNT,
        }:
            return {"amount": str(getattr(action, "amount", None))}
        return {
            "buy_quantity": str(getattr(action, "buy_quantity", None)),
            "free_quantity": str(getattr(action, "free_quantity", None)),
        }

    def promotion_response(self, row: Promotion) -> PromotionResponse:
        """Build the API response for one promotion."""
        return PromotionResponse(
            id=row.id,
            firm_id=row.firm_id,
            code=row.code,
            name=row.name,
            description=row.description,
            priority=row.priority,
            status=row.status,
            allow_stacking=row.allow_stacking,
            effective_from=row.effective_from,
            effective_to=row.effective_to,
            version_group_id=row.version_group_id,
            version_number=row.version_number,
            supersedes_promotion_id=row.supersedes_promotion_id,
            conditions=[
                PromotionConditionResponse(
                    id=item.id,
                    sequence=item.sequence,
                    field_key=item.field_key,
                    operator=item.operator,
                    value_text=item.value_text,
                    value_number=item.value_number,
                    value_date=item.value_date,
                    value_boolean=item.value_boolean,
                    value_json=item.value_json,
                )
                for item in row.conditions
            ],
            actions=[
                PromotionActionResponse(
                    id=item.id,
                    sequence=item.sequence,
                    action_type=item.action_type,
                    parameters=item.parameters,
                )
                for item in row.actions
            ],
            version=row.version,
        )
