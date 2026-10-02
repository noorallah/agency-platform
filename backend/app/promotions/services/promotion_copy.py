"""Copy last season's offers with new dates (SEL-8, decision A71).

Diwali comes back every year with the same offers at new dates. Copying them
one by one meant retyping every condition and benefit. This copies a set of
offers in one go as **drafts** -- nothing goes live until somebody approves the
copy -- each with the new window, a new code (the old code plus a suffix, as a
code names one offer for good), its own version history from one, and the
same conditions and benefits. Coupons are not copied: they were a campaign's,
and the new campaign mints its own. The originals are not touched.

All or nothing: one clashing code refuses the whole copy by name, so a
half-copied season never has to be found and finished by hand.
"""

from collections.abc import Sequence
from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.promotions.models import Promotion, PromotionAction, PromotionCondition
from app.promotions.schemas import PromotionStatus


class PromotionCopyService:
    """Copy offers as drafts with a new window."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request unit of work."""
        self._session = session

    def copy(
        self,
        promotion_ids: Sequence[UUID],
        *,
        effective_from: date,
        effective_to: date,
        code_suffix: str,
        firm_id: UUID,
        actor_id: UUID,
    ) -> list[Promotion]:
        """Copy each offer as a draft with the new window, all or none.

        Raises:
            ValidationError: If the window is backwards, the suffix is empty or
                not letters and digits, or an id is listed twice.
            ResourceNotFoundError: If an offer is not the firm's.
            ConflictError: If a new code is already taken.

        """
        if effective_to < effective_from:
            raise ValidationError("An offer cannot end before it starts.")
        suffix = code_suffix.strip().upper()
        if not suffix or not all(c.isalnum() or c in "-_" for c in suffix):
            raise ValidationError(
                "Give a suffix for the new codes, such as -26, in letters and "
                "digits."
            )
        if len(set(promotion_ids)) != len(promotion_ids):
            raise ValidationError("An offer is listed twice.")
        sources = {
            row.id: row
            for row in self._session.scalars(
                select(Promotion).where(
                    Promotion.firm_id == firm_id,
                    Promotion.id.in_(promotion_ids),
                    Promotion.is_deleted.is_(False),
                )
            )
        }
        if len(sources) != len(promotion_ids):
            raise ResourceNotFoundError("Promotion not found.")
        ordered = [sources[promotion_id] for promotion_id in promotion_ids]
        codes = {row.id: f"{row.code}{suffix}" for row in ordered}
        too_long = [code for code in codes.values() if len(code) > 50]
        if too_long:
            raise ValidationError(f"{too_long[0]} is longer than 50 characters.")
        taken = sorted(
            self._session.scalars(
                select(Promotion.code).where(
                    Promotion.firm_id == firm_id,
                    Promotion.code.in_(codes.values()),
                    Promotion.is_deleted.is_(False),
                )
            )
        )
        if taken:
            raise ConflictError(
                f"An offer coded {', '.join(taken)} already exists; choose "
                "another suffix."
            )

        copies: list[Promotion] = []
        for source in ordered:
            row = Promotion(
                firm_id=firm_id,
                code=codes[source.id],
                name=source.name,
                description=source.description,
                priority=source.priority,
                status=PromotionStatus.DRAFT.value,
                allow_stacking=source.allow_stacking,
                effective_from=effective_from,
                effective_to=effective_to,
                requires_coupon=source.requires_coupon,
                max_redemptions=source.max_redemptions,
                max_redemptions_per_customer=source.max_redemptions_per_customer,
                version_group_id=uuid4(),
                version_number=1,
                created_by=actor_id,
                updated_by=actor_id,
            )
            self._session.add(row)
            self._session.flush()
            for condition in source.conditions:
                if condition.is_deleted:
                    continue
                self._session.add(
                    PromotionCondition(
                        firm_id=firm_id,
                        promotion_id=row.id,
                        sequence=condition.sequence,
                        field_key=condition.field_key,
                        operator=condition.operator,
                        value_text=condition.value_text,
                        value_number=condition.value_number,
                        value_date=condition.value_date,
                        value_boolean=condition.value_boolean,
                        value_json=condition.value_json,
                        created_by=actor_id,
                        updated_by=actor_id,
                    )
                )
            for action in source.actions:
                if action.is_deleted:
                    continue
                self._session.add(
                    PromotionAction(
                        firm_id=firm_id,
                        promotion_id=row.id,
                        sequence=action.sequence,
                        action_type=action.action_type,
                        parameters=dict(action.parameters or {}),
                        created_by=actor_id,
                        updated_by=actor_id,
                    )
                )
            record_audit(
                self._session,
                action="promotion.copied",
                entity_type="promotion",
                entity_id=row.id,
                actor_id=actor_id,
                firm_id=firm_id,
                after_data={
                    "code": row.code,
                    "copied_from": source.code,
                    "copied_from_id": str(source.id),
                    "effective_from": effective_from.isoformat(),
                    "effective_to": effective_to.isoformat(),
                },
            )
            copies.append(row)
        self._session.flush()
        for row in copies:
            self._session.refresh(row)
        self._session.commit()
        return copies
