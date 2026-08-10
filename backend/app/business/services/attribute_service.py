"""Configurable custom fields for any module.

A module gains industry-specific fields by calling this service rather than by
adding columns. The flow is the same everywhere:

* an administrator defines an :class:`AttributeDefinition` for an entity type,
  optionally scoped to one business profile;
* the module calls :meth:`AttributeService.replace_values` when saving a record
  and :meth:`AttributeService.values_for` when reading one.

Each module owns a small value table built from :class:`AttributeValueBase`,
so a value carries a real foreign key to its record. This service is
parameterised by that model, which keeps one implementation for every module
while leaving the storage properly constrained and indexable.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.business.models import (
    AttributeDataType,
    AttributeDefinition,
    AttributeValueBase,
    BusinessProfile,
    CategoryAttributeRule,
    FirmBusinessProfile,
)
from app.core.exceptions import ValidationError
from app.core.utils.dates import utc_now

#: The value a caller may submit for a custom attribute.
type AttributeValue = str | int | float | Decimal | bool | date | datetime | None


@dataclass(frozen=True, slots=True)
class AttributeInput:
    """One submitted attribute value."""

    attribute_definition_id: UUID
    value: AttributeValue


@dataclass(frozen=True, slots=True)
class ResolvedAttribute:
    """One stored attribute value with the definition that describes it."""

    definition: AttributeDefinition
    value: AttributeValue


class AttributeService:
    """Resolve, validate, and persist custom attribute values."""

    def __init__(self, session: Session) -> None:
        """Bind the service to one unit of work."""
        self._session = session

    # ------------------------------------------------------------------
    # Definitions
    # ------------------------------------------------------------------

    def definitions_for(
        self,
        entity_type: str,
        *,
        firm_id: UUID,
        category_code: str | None = None,
    ) -> list[AttributeDefinition]:
        """Return the attributes that apply to one entity type for a firm.

        A definition applies when it targets the entity type and is either
        unscoped or scoped to the firm's active business profile.
        """
        profile_id = self._profile_id(firm_id)
        statement = select(AttributeDefinition).where(
            AttributeDefinition.entity_type == entity_type,
            AttributeDefinition.is_active.is_(True),
            AttributeDefinition.is_deleted.is_(False),
        )
        rows = list(self._session.scalars(statement).all())
        applicable = [
            row
            for row in rows
            if row.applicable_business_profile_id in (None, profile_id)
        ]
        if category_code is not None:
            applicable = [
                row
                for row in applicable
                if row.applicable_category in (None, category_code)
            ]
        return sorted(applicable, key=lambda row: row.code)

    def mandatory_ids(
        self,
        entity_type: str,
        *,
        firm_id: UUID,
        category_code: str | None = None,
    ) -> set[UUID]:
        """Return the attribute ids a record of this type must carry."""
        definitions = self.definitions_for(
            entity_type, firm_id=firm_id, category_code=category_code
        )
        required = {row.id for row in definitions if row.mandatory}
        if category_code is not None:
            profile_id = self._profile_id(firm_id)
            allowed = {row.id for row in definitions}
            rules = self._session.scalars(
                select(CategoryAttributeRule).where(
                    CategoryAttributeRule.category_code == category_code,
                    CategoryAttributeRule.is_mandatory.is_(True),
                    CategoryAttributeRule.is_deleted.is_(False),
                )
            ).all()
            required |= {
                rule.attribute_definition_id
                for rule in rules
                if rule.business_profile_id in (None, profile_id)
                and rule.attribute_definition_id in allowed
            }
        return required

    # ------------------------------------------------------------------
    # Values
    # ------------------------------------------------------------------

    def replace_values(
        self,
        model: type[AttributeValueBase],
        owner_id: UUID,
        inputs: list[AttributeInput],
        *,
        firm_id: UUID,
        actor_id: UUID,
        category_code: str | None = None,
    ) -> None:
        """Validate and store the complete attribute set for one record."""
        entity_type = model.ENTITY_TYPE.value
        definitions = {
            row.id: row
            for row in self.definitions_for(
                entity_type, firm_id=firm_id, category_code=category_code
            )
        }
        submitted = {item.attribute_definition_id for item in inputs}

        existing = {
            row.attribute_definition_id: row
            for row in self._session.scalars(
                # Scoped to the firm, not only the record. Most owners are
                # firm-owned, so the owner already implies the firm and this
                # changes nothing -- but `uoms` carries no `firm_id` and one row
                # is shared by every SHARED-mode firm in `firm_shared`. Without
                # this, saving a unit's attributes for one firm would treat
                # another firm's values as its own and clear them.
                select(model).where(
                    model.owner_column() == owner_id,
                    model.firm_id == firm_id,
                )
            ).all()
        }
        # Disabling a definition stops new data; it must not block edits to a
        # record that already carries a value, nor silently destroy that value
        # because a form resubmitted what the user could still see. Retained
        # values keep their definition available for this save only.
        retained = self._retained_definitions(submitted - definitions.keys(), existing)
        definitions.update(retained)

        unknown = sorted(str(item) for item in submitted - definitions.keys())
        if unknown:
            raise ValidationError(
                "One or more attributes do not apply to this record.",
                details={"invalid_attribute_definition_ids": unknown},
            )
        missing = sorted(
            str(item)
            for item in self.mandatory_ids(
                entity_type, firm_id=firm_id, category_code=category_code
            )
            - submitted
        )
        if missing:
            raise ValidationError(
                "Required attributes are missing.",
                details={"missing_attribute_definition_ids": missing},
            )
        if len(submitted) != len(inputs):
            raise ValidationError("An attribute was supplied more than once.")

        for item in inputs:
            definition = definitions[item.attribute_definition_id]
            columns = self._coerce(definition, item.value)
            row = existing.pop(item.attribute_definition_id, None)
            if row is None:
                self._session.add(
                    model(
                        firm_id=firm_id,
                        attribute_definition_id=definition.id,
                        created_by=actor_id,
                        updated_by=actor_id,
                        **{model.OWNER_COLUMN: owner_id},
                        **columns,
                    )
                )
                continue
            for column, value in columns.items():
                setattr(row, column, value)
            row.is_deleted = False
            row.deleted_at = None
            row.updated_by = actor_id
            row.version += 1
        # Anything left was not resubmitted, so it has been cleared.
        for row in existing.values():
            row.is_deleted = True
            row.deleted_at = utc_now()
            row.deleted_by = actor_id
            row.updated_by = actor_id

    def values_for(
        self,
        model: type[AttributeValueBase],
        owner_id: UUID,
        *,
        firm_id: UUID | None = None,
    ) -> list[ResolvedAttribute]:
        """Return the stored attributes of one record in definition-code order.

        Pass ``firm_id`` whenever the owning table is a shared catalogue rather
        than firm-owned data. For a firm-owned owner the record already belongs
        to exactly one firm and the filter is redundant; for a shared owner such
        as a unit of measure it is the only thing keeping one firm's annotations
        out of another's.
        """
        rows = self._session.execute(
            select(model, AttributeDefinition)
            .join(
                AttributeDefinition,
                AttributeDefinition.id == model.attribute_definition_id,
            )
            .where(
                model.owner_column() == owner_id,
                model.is_deleted.is_(False),
                *([] if firm_id is None else [model.firm_id == firm_id]),
            )
            .order_by(AttributeDefinition.code.asc())
        ).all()
        return [
            ResolvedAttribute(
                definition=definition, value=self._read(value, definition)
            )
            for value, definition in rows
        ]

    def values_for_many(
        self,
        model: type[AttributeValueBase],
        owner_ids: list[UUID],
        *,
        firm_id: UUID | None = None,
    ) -> dict[UUID, list[ResolvedAttribute]]:
        """Return attributes for several records without a query per record.

        ``firm_id`` scopes a shared-catalogue owner; see :meth:`values_for`.
        """
        if not owner_ids:
            return {}
        owner = model.owner_column()
        rows = self._session.execute(
            select(model, AttributeDefinition)
            .join(
                AttributeDefinition,
                AttributeDefinition.id == model.attribute_definition_id,
            )
            .where(
                owner.in_(owner_ids),
                model.is_deleted.is_(False),
                *([] if firm_id is None else [model.firm_id == firm_id]),
            )
            .order_by(AttributeDefinition.code.asc())
        ).all()
        grouped: dict[UUID, list[ResolvedAttribute]] = {}
        for value, definition in rows:
            grouped.setdefault(getattr(value, model.OWNER_COLUMN), []).append(
                ResolvedAttribute(
                    definition=definition, value=self._read(value, definition)
                )
            )
        return grouped

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _retained_definitions(
        self,
        unmatched: set[UUID],
        existing: dict[UUID, AttributeValueBase],
    ) -> dict[UUID, AttributeDefinition]:
        """Return definitions the record already carries but no longer offers.

        A definition that has been deactivated, or scoped away from the record's
        profile or category, stays writable for a record that already holds a
        value for it. Anything else the caller submitted remains an error.
        """
        candidates = {
            item
            for item in unmatched
            if item in existing and not existing[item].is_deleted
        }
        if not candidates:
            return {}
        return {
            row.id: row
            for row in self._session.scalars(
                select(AttributeDefinition).where(
                    AttributeDefinition.id.in_(candidates),
                    AttributeDefinition.is_deleted.is_(False),
                )
            ).all()
        }

    def _coerce(
        self, definition: AttributeDefinition, value: AttributeValue
    ) -> dict[str, object]:
        """Convert a submitted value into its typed storage column."""
        blank: dict[str, object] = {
            "value_text": None,
            "value_number": None,
            "value_date": None,
            "value_boolean": None,
        }
        if value is None or (isinstance(value, str) and not value.strip()):
            if definition.mandatory:
                raise ValidationError(
                    f"Attribute {definition.code} is required and cannot be empty."
                )
            return blank

        data_type = definition.data_type.upper()
        if data_type == AttributeDataType.BOOLEAN.value:
            if isinstance(value, bool):
                return {**blank, "value_boolean": value}
            if isinstance(value, str) and value.lower() in {"true", "false"}:
                return {**blank, "value_boolean": value.lower() == "true"}
            raise self._type_error(definition, value, "a true/false value")
        if data_type == AttributeDataType.NUMBER.value:
            if isinstance(value, bool):
                raise self._type_error(definition, value, "a number")
            try:
                return {**blank, "value_number": Decimal(str(value))}
            except (InvalidOperation, ValueError) as error:
                raise self._type_error(definition, value, "a number") from error
        if data_type == AttributeDataType.DATE.value:
            if isinstance(value, datetime):
                return {**blank, "value_date": value.date()}
            if isinstance(value, date):
                return {**blank, "value_date": value}
            if isinstance(value, str):
                try:
                    return {**blank, "value_date": date.fromisoformat(value)}
                except ValueError as error:
                    raise self._type_error(definition, value, "a date") from error
            raise self._type_error(definition, value, "a date")
        return {**blank, "value_text": str(value)}

    def _read(
        self, row: AttributeValueBase, definition: AttributeDefinition
    ) -> AttributeValue:
        """Return the populated column for a stored value."""
        data_type = definition.data_type.upper()
        if data_type == AttributeDataType.BOOLEAN.value:
            return row.value_boolean
        if data_type == AttributeDataType.NUMBER.value:
            return row.value_number
        if data_type == AttributeDataType.DATE.value:
            return row.value_date
        return row.value_text

    def _type_error(
        self, definition: AttributeDefinition, value: object, expected: str
    ) -> ValidationError:
        """Build a consistent message for a mistyped attribute."""
        return ValidationError(
            f"Attribute {definition.code} expects {expected}.",
            details={"attribute_code": definition.code, "received": str(value)},
        )

    def _profile_id(self, firm_id: UUID) -> UUID | None:
        """Return the firm's active profile, falling back to the default."""
        assigned = self._session.scalar(
            select(FirmBusinessProfile.business_profile_id).where(
                FirmBusinessProfile.firm_id == firm_id,
                FirmBusinessProfile.is_active.is_(True),
                FirmBusinessProfile.is_deleted.is_(False),
            )
        )
        if assigned is not None:
            return assigned
        return self._session.scalar(
            select(BusinessProfile.id).where(
                BusinessProfile.is_default.is_(True),
                BusinessProfile.status == "ACTIVE",
                BusinessProfile.is_deleted.is_(False),
            )
        )
