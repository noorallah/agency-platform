"""A firm's own custom fields (MST-8, decision A120).

Custom field definitions live in each firm store, and several firms share
``firm_shared``; until now a definition there reached every one of them.
A row with ``firm_id`` is that firm's own -- offered on its forms and no
other's -- and its administrator keeps it here. A row without one is the
platform's shared catalogue, offered to every firm and read-only to them.
A firm's code is unique among its own and the shared live rows. The
lifecycle guards the platform screen keeps (a held type cannot change, a
held field cannot be deleted) apply the same way.
"""

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.business.models import (
    RULE_KIND_COLUMNS,
    AttributeDefinition,
    CategoryAttributeRule,
    FirmAttributeSwitch,
)
from app.business.schemas import (
    AttributeDefinitionCreate,
    AttributeDefinitionUpdate,
    CategoryAttributeRuleCreate,
)
from app.business.services.field_rules import assert_rule_new, assert_rule_target
from app.business.services.framework_service import BusinessProfileFrameworkService
from app.common.audit.services import record_audit
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now


class FirmCustomFieldService:
    """Keep one firm's own custom fields and the rules that require them."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the firm's store session."""
        self._session = session
        self._framework = BusinessProfileFrameworkService(session)

    def list_fields(self, firm_id: UUID) -> list[AttributeDefinition]:
        """Return the firm's own fields and the shared ones, by code."""
        return list(
            self._session.scalars(
                select(AttributeDefinition)
                .where(
                    AttributeDefinition.is_deleted.is_(False),
                    or_(
                        AttributeDefinition.firm_id.is_(None),
                        AttributeDefinition.firm_id == firm_id,
                    ),
                )
                .order_by(AttributeDefinition.code.asc())
            ).all()
        )

    def create(
        self, data: AttributeDefinitionCreate, *, firm_id: UUID, actor_id: UUID
    ) -> AttributeDefinition:
        """Add a field of the firm's own; commit."""
        self._assert_code_free(data.code, firm_id=firm_id)
        row = AttributeDefinition(
            **data.model_dump(),
            firm_id=firm_id,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._session.flush()
        self._audit("firm_custom_field.created", row, firm_id, actor_id)
        self._session.commit()
        return row

    def update(
        self,
        field_id: UUID,
        data: AttributeDefinitionUpdate,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> AttributeDefinition:
        """Change a field of the firm's own; a held type cannot change.

        Raises:
            ConflictError: If values are held and the type would change, or the
                new code is taken.

        """
        row = self._own(field_id, firm_id)
        values = data.model_dump(exclude_unset=True)
        if "code" in values and values["code"] != row.code:
            self._assert_code_free(str(values["code"]), firm_id=firm_id, current=row.id)
        new_type = values.get("data_type", row.data_type)
        if str(new_type) != row.data_type:
            held = self._framework.attribute_value_count(row)
            if held:
                raise ConflictError(
                    f"{row.code} holds {held} stored value(s), so its type "
                    f"cannot change from {row.data_type} to {new_type}. Add a "
                    "new field of the new type and retire this one."
                )
        for field, value in values.items():
            setattr(row, field, value)
        row.updated_by = actor_id
        self._audit("firm_custom_field.updated", row, firm_id, actor_id)
        self._session.commit()
        return row

    def delete(self, field_id: UUID, *, firm_id: UUID, actor_id: UUID) -> None:
        """Remove a field of the firm's own that holds no values."""
        row = self._own(field_id, firm_id)
        held = self._framework.attribute_value_count(row)
        if held:
            raise ConflictError(
                f"{row.code} holds {held} stored value(s), so it cannot be "
                "deleted. Deactivate it instead."
            )
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.updated_by = actor_id
        self._audit("firm_custom_field.deleted", row, firm_id, actor_id)
        self._session.commit()

    def switched_off(self, firm_id: UUID) -> set[UUID]:
        """Return the shared fields this firm has switched off."""
        return set(
            self._session.scalars(
                select(FirmAttributeSwitch.attribute_definition_id).where(
                    FirmAttributeSwitch.firm_id == firm_id,
                    FirmAttributeSwitch.is_enabled.is_(False),
                    FirmAttributeSwitch.is_deleted.is_(False),
                )
            )
        )

    def set_use(
        self, field_id: UUID, *, enabled: bool, firm_id: UUID, actor_id: UUID
    ) -> AttributeDefinition:
        """Switch one shared field on or off for this firm; commit.

        Off hides the field from the firm's forms and keeps every value
        already stored: nothing is deleted, and switching it on shows them
        again. A firm's own field is retired with its ``is_active`` instead.

        Raises:
            ResourceNotFoundError: If the field is not in the shared list.

        """
        field = self._session.get(AttributeDefinition, field_id)
        if field is None or field.is_deleted or field.firm_id is not None:
            raise ResourceNotFoundError(
                "Custom field not found in the shared list. One of the firm's "
                "own is switched off by making it inactive."
            )
        row = self._session.scalar(
            select(FirmAttributeSwitch).where(
                FirmAttributeSwitch.firm_id == firm_id,
                FirmAttributeSwitch.attribute_definition_id == field_id,
                FirmAttributeSwitch.is_deleted.is_(False),
            )
        )
        was = True if row is None else row.is_enabled
        if was == enabled:
            return field
        if row is None:
            self._session.add(
                FirmAttributeSwitch(
                    firm_id=firm_id,
                    attribute_definition_id=field_id,
                    is_enabled=enabled,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
        else:
            row.is_enabled = enabled
            row.updated_by = actor_id
        record_audit(
            self._session,
            action="firm_custom_field.use_changed",
            entity_type="attribute_definition",
            entity_id=field.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data={"code": field.code, "is_enabled": was},
            after_data={"code": field.code, "is_enabled": enabled},
        )
        self._session.commit()
        return field

    def list_rules(self, firm_id: UUID) -> list[CategoryAttributeRule]:
        """Return the firm's own field rules."""
        return list(
            self._session.scalars(
                select(CategoryAttributeRule).where(
                    CategoryAttributeRule.firm_id == firm_id,
                    CategoryAttributeRule.is_deleted.is_(False),
                )
            ).all()
        )

    def create_rule(
        self, data: CategoryAttributeRuleCreate, *, firm_id: UUID, actor_id: UUID
    ) -> CategoryAttributeRule:
        """Tie a field to a kind of record, or require it in a category; commit.

        The rule names a product category, a goods type, a customer group or
        a supplier type, and holds for this firm alone.

        Raises:
            ValidationError: If the field is another firm's, or the kind is
                not one this firm can name for that field.
            ConflictError: If the firm already has that rule.

        """
        field = self._session.get(AttributeDefinition, data.attribute_definition_id)
        if field is None or field.is_deleted or field.firm_id not in (None, firm_id):
            raise ValidationError("That field is not one this firm can use.")
        assert_rule_target(self._session, data, field, firm_id=firm_id)
        assert_rule_new(self._session, data, firm_id=firm_id)
        row = CategoryAttributeRule(
            **data.model_dump(),
            firm_id=firm_id,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._session.flush()
        record_audit(
            self._session,
            action="firm_custom_field_rule.created",
            entity_type="category_attribute_rule",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={
                "field": field.code,
                "is_mandatory": row.is_mandatory,
                **{
                    column: str(value)
                    for column in ("category_code", *RULE_KIND_COLUMNS)
                    if (value := getattr(row, column)) is not None
                },
            },
        )
        self._session.commit()
        return row

    def delete_rule(self, rule_id: UUID, *, firm_id: UUID, actor_id: UUID) -> None:
        """Remove one of the firm's own rules."""
        row = self._session.get(CategoryAttributeRule, rule_id)
        if row is None or row.is_deleted or row.firm_id != firm_id:
            raise ResourceNotFoundError("Rule not found.")
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="firm_custom_field_rule.deleted",
            entity_type="category_attribute_rule",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
        )
        self._session.commit()

    def _own(self, field_id: UUID, firm_id: UUID) -> AttributeDefinition:
        """Return a field of the firm's own; a shared one is not theirs to change."""
        row = self._session.get(AttributeDefinition, field_id)
        if row is None or row.is_deleted or row.firm_id != firm_id:
            raise ResourceNotFoundError(
                "Custom field not found among this firm's own fields."
            )
        return row

    def _assert_code_free(
        self, code: str, *, firm_id: UUID, current: UUID | None = None
    ) -> None:
        """Refuse a code the firm or the shared catalogue already uses."""
        statement = select(AttributeDefinition.id).where(
            AttributeDefinition.code == code,
            AttributeDefinition.is_deleted.is_(False),
            or_(
                AttributeDefinition.firm_id.is_(None),
                AttributeDefinition.firm_id == firm_id,
            ),
        )
        if current is not None:
            statement = statement.where(AttributeDefinition.id != current)
        if self._session.scalar(statement) is not None:
            raise ConflictError(f"A field with code {code} already exists.")

    def _audit(
        self, action: str, row: AttributeDefinition, firm_id: UUID, actor_id: UUID
    ) -> None:
        """Write one audit row for a field."""
        record_audit(
            self._session,
            action=action,
            entity_type="attribute_definition",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={"code": row.code, "data_type": row.data_type},
        )
