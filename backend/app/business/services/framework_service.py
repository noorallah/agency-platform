"""Service layer for multi-industry business profile configuration."""

# ruff: noqa: D102, D107

from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.business.models import (
    AttributeDefinition,
    BusinessFeature,
    BusinessModule,
    BusinessProfile,
    CategoryAttributeRule,
    FirmBusinessProfile,
    ProfileFeature,
    ProfileModule,
)
from app.business.schemas import (
    AttributeDefinitionCreate,
    AttributeDefinitionUpdate,
    BusinessFeatureCreate,
    BusinessFeatureUpdate,
    BusinessModuleCreate,
    BusinessModuleUpdate,
    BusinessProfileCreate,
    BusinessProfileUpdate,
    CategoryAttributeRuleCreate,
    CategoryAttributeRuleUpdate,
    FirmBusinessProfileAssign,
)
from app.common.audit.services import record_audit
from app.common.firm_metadata import FirmMetadataReader
from app.core.exceptions import (
    ConflictError,
    ResourceNotFoundError,
    ValidationError,
)
from app.core.utils.dates import utc_now


class BusinessProfileFrameworkService:
    """Manage business profiles, features, modules, and firm assignments."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_profiles(
        self,
        page: int,
        page_size: int,
        search: str | None,
        sort_by: str,
        descending: bool,
    ) -> tuple[list[BusinessProfile], int]:
        columns = {
            "code": BusinessProfile.code,
            "name": BusinessProfile.name,
            "created_at": BusinessProfile.created_at,
        }
        statement = select(BusinessProfile).where(BusinessProfile.is_deleted.is_(False))
        count = (
            select(func.count())
            .select_from(BusinessProfile)
            .where(BusinessProfile.is_deleted.is_(False))
        )
        if search:
            condition = or_(
                BusinessProfile.code.ilike(f"%{search.strip()}%"),
                BusinessProfile.name.ilike(f"%{search.strip()}%"),
                BusinessProfile.industry_type.ilike(f"%{search.strip()}%"),
            )
            statement = statement.where(condition)
            count = count.where(condition)
        ordering = columns[sort_by].desc() if descending else columns[sort_by].asc()
        rows = self._session.scalars(
            statement.order_by(ordering).offset((page - 1) * page_size).limit(page_size)
        ).all()
        return list(rows), int(self._session.scalar(count) or 0)

    def create_profile(
        self, data: BusinessProfileCreate, actor_id: UUID
    ) -> BusinessProfile:
        self._assert_unique(BusinessProfile, data.code)
        if data.is_default:
            self._unset_default_profiles()
        profile = BusinessProfile(
            **data.model_dump(), created_by=actor_id, updated_by=actor_id
        )
        self._session.add(profile)
        self._session.flush()
        record_audit(
            self._session,
            action="business_profile.created",
            entity_type="business_profile",
            entity_id=profile.id,
            actor_id=actor_id,
            after_data={"code": profile.code},
        )
        self._session.commit()
        return profile

    def get_profile(self, profile_id: UUID) -> BusinessProfile:
        profile = self._session.scalar(
            select(BusinessProfile).where(
                BusinessProfile.id == profile_id,
                BusinessProfile.is_deleted.is_(False),
            )
        )
        if profile is None:
            raise ResourceNotFoundError("Business profile not found.")
        return profile

    def update_profile(
        self, profile_id: UUID, data: BusinessProfileUpdate, actor_id: UUID
    ) -> BusinessProfile:
        profile = self.get_profile(profile_id)
        self._assert_unique(BusinessProfile, data.code, current_id=profile.id)
        if data.is_default:
            self._unset_default_profiles(except_id=profile.id)
        before: dict[str, object] = {"code": profile.code, "status": profile.status}
        for field, value in data.model_dump().items():
            setattr(profile, field, value)
        profile.updated_by = actor_id
        record_audit(
            self._session,
            action="business_profile.updated",
            entity_type="business_profile",
            entity_id=profile.id,
            actor_id=actor_id,
            before_data=before,
        )
        self._session.commit()
        return profile

    def delete_profile(self, profile_id: UUID, actor_id: UUID) -> None:
        profile = self.get_profile(profile_id)
        has_assignment = self._session.scalar(
            select(FirmBusinessProfile.id).where(
                FirmBusinessProfile.business_profile_id == profile.id,
                FirmBusinessProfile.is_deleted.is_(False),
                FirmBusinessProfile.is_active.is_(True),
            )
        )
        if has_assignment is not None:
            raise ConflictError("Assigned business profiles cannot be deleted.")
        profile.is_deleted = True
        profile.deleted_at = utc_now()
        profile.deleted_by = actor_id
        profile.updated_by = actor_id
        record_audit(
            self._session,
            action="business_profile.deleted",
            entity_type="business_profile",
            entity_id=profile.id,
            actor_id=actor_id,
        )
        self._session.commit()

    def list_features(
        self,
        page: int,
        page_size: int,
        search: str | None,
        sort_by: str,
        descending: bool,
    ) -> tuple[list[BusinessFeature], int]:
        rows, total = self._list_catalog(
            BusinessFeature, page, page_size, search, sort_by, descending
        )
        return cast(list[BusinessFeature], rows), total

    def create_feature(
        self, data: BusinessFeatureCreate, actor_id: UUID
    ) -> BusinessFeature:
        self._assert_unique(BusinessFeature, data.code)
        feature = BusinessFeature(
            **data.model_dump(), created_by=actor_id, updated_by=actor_id
        )
        self._session.add(feature)
        self._session.flush()
        record_audit(
            self._session,
            action="business_feature.created",
            entity_type="business_feature",
            entity_id=feature.id,
            actor_id=actor_id,
        )
        self._session.commit()
        return feature

    def get_feature(self, feature_id: UUID) -> BusinessFeature:
        row = self._session.scalar(
            select(BusinessFeature).where(
                BusinessFeature.id == feature_id, BusinessFeature.is_deleted.is_(False)
            )
        )
        if row is None:
            raise ResourceNotFoundError("Business feature not found.")
        return row

    def update_feature(
        self, feature_id: UUID, data: BusinessFeatureUpdate, actor_id: UUID
    ) -> BusinessFeature:
        feature = self.get_feature(feature_id)
        self._assert_unique(BusinessFeature, data.code, current_id=feature.id)
        for field, value in data.model_dump().items():
            setattr(feature, field, value)
        feature.updated_by = actor_id
        record_audit(
            self._session,
            action="business_feature.updated",
            entity_type="business_feature",
            entity_id=feature.id,
            actor_id=actor_id,
        )
        self._session.commit()
        return feature

    def _assert_feature_unused(self, feature_id: UUID) -> None:
        """Refuse to delete a feature a profile still enables.

        ``resolve_capabilities`` skips deleted features, so removing the master
        row does not merely tidy a catalogue: every firm on a profile that
        enabled it loses the capability at once, and ``require_feature`` starts
        rejecting writes those firms were making yesterday. ``delete_profile``
        already refuses while an assignment exists; this is the same rule one
        level down.
        """
        enabled = self._session.scalar(
            select(ProfileFeature.id)
            .where(
                ProfileFeature.feature_id == feature_id,
                ProfileFeature.is_enabled.is_(True),
                ProfileFeature.is_deleted.is_(False),
            )
            .limit(1)
        )
        if enabled is not None:
            raise ConflictError(
                "Business profiles still enable this feature; disable it there first."
            )

    def _assert_module_unused(self, module_id: UUID) -> None:
        """Refuse to delete a module a profile still enables."""
        enabled = self._session.scalar(
            select(ProfileModule.id)
            .where(
                ProfileModule.module_id == module_id,
                ProfileModule.is_enabled.is_(True),
                ProfileModule.is_deleted.is_(False),
            )
            .limit(1)
        )
        if enabled is not None:
            raise ConflictError(
                "Business profiles still enable this module; disable it there first."
            )

    def delete_feature(self, feature_id: UUID, actor_id: UUID) -> None:
        """Soft delete a feature no profile still enables."""
        feature = self.get_feature(feature_id)
        self._assert_feature_unused(feature.id)
        feature.is_deleted = True
        feature.deleted_at = utc_now()
        feature.deleted_by = actor_id
        feature.updated_by = actor_id
        record_audit(
            self._session,
            action="business_feature.deleted",
            entity_type="business_feature",
            entity_id=feature.id,
            actor_id=actor_id,
        )
        self._session.commit()

    def list_modules(
        self,
        page: int,
        page_size: int,
        search: str | None,
        sort_by: str,
        descending: bool,
    ) -> tuple[list[BusinessModule], int]:
        rows, total = self._list_catalog(
            BusinessModule, page, page_size, search, sort_by, descending
        )
        return cast(list[BusinessModule], rows), total

    def create_module(
        self, data: BusinessModuleCreate, actor_id: UUID
    ) -> BusinessModule:
        self._assert_unique(BusinessModule, data.code)
        module = BusinessModule(
            **data.model_dump(), created_by=actor_id, updated_by=actor_id
        )
        self._session.add(module)
        self._session.flush()
        record_audit(
            self._session,
            action="business_module.created",
            entity_type="business_module",
            entity_id=module.id,
            actor_id=actor_id,
        )
        self._session.commit()
        return module

    def get_module(self, module_id: UUID) -> BusinessModule:
        row = self._session.scalar(
            select(BusinessModule).where(
                BusinessModule.id == module_id, BusinessModule.is_deleted.is_(False)
            )
        )
        if row is None:
            raise ResourceNotFoundError("Business module not found.")
        return row

    def update_module(
        self, module_id: UUID, data: BusinessModuleUpdate, actor_id: UUID
    ) -> BusinessModule:
        module = self.get_module(module_id)
        self._assert_unique(BusinessModule, data.code, current_id=module.id)
        for field, value in data.model_dump().items():
            setattr(module, field, value)
        module.updated_by = actor_id
        record_audit(
            self._session,
            action="business_module.updated",
            entity_type="business_module",
            entity_id=module.id,
            actor_id=actor_id,
        )
        self._session.commit()
        return module

    def delete_module(self, module_id: UUID, actor_id: UUID) -> None:
        """Soft delete a module no profile still enables."""
        module = self.get_module(module_id)
        self._assert_module_unused(module.id)
        module.is_deleted = True
        module.deleted_at = utc_now()
        module.deleted_by = actor_id
        module.updated_by = actor_id
        record_audit(
            self._session,
            action="business_module.deleted",
            entity_type="business_module",
            entity_id=module.id,
            actor_id=actor_id,
        )
        self._session.commit()

    def list_attributes(
        self,
        page: int,
        page_size: int,
        search: str | None,
        sort_by: str,
        descending: bool,
    ) -> tuple[list[AttributeDefinition], int]:
        columns = {
            "code": AttributeDefinition.code,
            "name": AttributeDefinition.name,
            "created_at": AttributeDefinition.created_at,
        }
        statement = select(AttributeDefinition).where(
            AttributeDefinition.is_deleted.is_(False)
        )
        count = (
            select(func.count())
            .select_from(AttributeDefinition)
            .where(AttributeDefinition.is_deleted.is_(False))
        )
        if search:
            condition = or_(
                AttributeDefinition.code.ilike(f"%{search.strip()}%"),
                AttributeDefinition.name.ilike(f"%{search.strip()}%"),
            )
            statement = statement.where(condition)
            count = count.where(condition)
        ordering = columns[sort_by].desc() if descending else columns[sort_by].asc()
        rows = self._session.scalars(
            statement.order_by(ordering).offset((page - 1) * page_size).limit(page_size)
        ).all()
        return list(rows), int(self._session.scalar(count) or 0)

    def create_attribute(
        self, data: AttributeDefinitionCreate, actor_id: UUID
    ) -> AttributeDefinition:
        self._assert_unique(AttributeDefinition, data.code)
        if data.applicable_business_profile_id is not None:
            self.get_profile(data.applicable_business_profile_id)
        row = AttributeDefinition(
            **data.model_dump(), created_by=actor_id, updated_by=actor_id
        )
        self._session.add(row)
        self._session.flush()
        record_audit(
            self._session,
            action="attribute_definition.created",
            entity_type="attribute_definition",
            entity_id=row.id,
            actor_id=actor_id,
        )
        self._session.commit()
        return row

    def get_attribute(self, attribute_id: UUID) -> AttributeDefinition:
        row = self._session.scalar(
            select(AttributeDefinition).where(
                AttributeDefinition.id == attribute_id,
                AttributeDefinition.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Attribute definition not found.")
        return row

    def update_attribute(
        self, attribute_id: UUID, data: AttributeDefinitionUpdate, actor_id: UUID
    ) -> AttributeDefinition:
        row = self.get_attribute(attribute_id)
        self._assert_unique(AttributeDefinition, data.code, current_id=row.id)
        if data.applicable_business_profile_id is not None:
            self.get_profile(data.applicable_business_profile_id)
        for field, value in data.model_dump().items():
            setattr(row, field, value)
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="attribute_definition.updated",
            entity_type="attribute_definition",
            entity_id=row.id,
            actor_id=actor_id,
        )
        self._session.commit()
        return row

    def delete_attribute(self, attribute_id: UUID, actor_id: UUID) -> None:
        row = self.get_attribute(attribute_id)
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.deleted_by = actor_id
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="attribute_definition.deleted",
            entity_type="attribute_definition",
            entity_id=row.id,
            actor_id=actor_id,
        )
        self._session.commit()

    def list_category_rules(self) -> list[CategoryAttributeRule]:
        return list(
            self._session.scalars(
                select(CategoryAttributeRule).where(
                    CategoryAttributeRule.is_deleted.is_(False)
                )
            ).all()
        )

    def create_category_rule(
        self, data: CategoryAttributeRuleCreate, actor_id: UUID
    ) -> CategoryAttributeRule:
        if data.business_profile_id is not None:
            self.get_profile(data.business_profile_id)
        self.get_attribute(data.attribute_definition_id)
        row = CategoryAttributeRule(
            **data.model_dump(), created_by=actor_id, updated_by=actor_id
        )
        self._session.add(row)
        self._session.flush()
        record_audit(
            self._session,
            action="category_attribute_rule.created",
            entity_type="category_attribute_rule",
            entity_id=row.id,
            actor_id=actor_id,
        )
        self._session.commit()
        return row

    def update_category_rule(
        self, rule_id: UUID, data: CategoryAttributeRuleUpdate, actor_id: UUID
    ) -> CategoryAttributeRule:
        row = self.get_category_rule(rule_id)
        if data.business_profile_id is not None:
            self.get_profile(data.business_profile_id)
        self.get_attribute(data.attribute_definition_id)
        for field, value in data.model_dump().items():
            setattr(row, field, value)
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="category_attribute_rule.updated",
            entity_type="category_attribute_rule",
            entity_id=row.id,
            actor_id=actor_id,
        )
        self._session.commit()
        return row

    def delete_category_rule(self, rule_id: UUID, actor_id: UUID) -> None:
        row = self.get_category_rule(rule_id)
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.deleted_by = actor_id
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="category_attribute_rule.deleted",
            entity_type="category_attribute_rule",
            entity_id=row.id,
            actor_id=actor_id,
        )
        self._session.commit()

    def get_category_rule(self, rule_id: UUID) -> CategoryAttributeRule:
        row = self._session.scalar(
            select(CategoryAttributeRule).where(
                CategoryAttributeRule.id == rule_id,
                CategoryAttributeRule.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Category attribute rule not found.")
        return row

    def assign_profile_to_firm(
        self,
        firm_id: UUID,
        data: FirmBusinessProfileAssign,
        actor_id: UUID,
        *,
        effective_from: datetime | None = None,
    ) -> FirmBusinessProfile:
        self._require_firm(firm_id)
        self.get_profile(data.business_profile_id)
        row = self._session.scalar(
            select(FirmBusinessProfile).where(
                FirmBusinessProfile.firm_id == firm_id,
                FirmBusinessProfile.is_deleted.is_(False),
            )
        )
        if row is None:
            row = FirmBusinessProfile(
                firm_id=firm_id,
                business_profile_id=data.business_profile_id,
                is_active=data.is_active,
                effective_from=effective_from or utc_now(),
                notes=data.notes,
                created_by=actor_id,
                updated_by=actor_id,
            )
            self._session.add(row)
            action = "firm_business_profile.created"
        else:
            row.business_profile_id = data.business_profile_id
            row.is_active = data.is_active
            row.notes = data.notes
            row.updated_by = actor_id
            action = "firm_business_profile.updated"
        self._session.flush()
        record_audit(
            self._session,
            action=action,
            entity_type="firm_business_profile",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={"business_profile_id": str(row.business_profile_id)},
        )
        self._session.commit()
        return row

    def get_firm_assignment(self, firm_id: UUID) -> FirmBusinessProfile | None:
        self._require_firm(firm_id)
        return self._session.scalar(
            select(FirmBusinessProfile).where(
                FirmBusinessProfile.firm_id == firm_id,
                FirmBusinessProfile.is_deleted.is_(False),
            )
        )

    def set_profile_features(
        self, profile_id: UUID, feature_ids: list[UUID], actor_id: UUID
    ) -> None:
        profile = self.get_profile(profile_id)
        self._validate_catalog_ids(BusinessFeature, feature_ids, "feature")
        self._reject_unimplemented(feature_ids)
        existing = {
            row.feature_id: row
            for row in self._session.scalars(
                select(ProfileFeature).where(
                    ProfileFeature.business_profile_id == profile.id,
                    ProfileFeature.is_deleted.is_(False),
                )
            )
        }
        requested = set(feature_ids)
        for feature_id, row in existing.items():
            row.is_enabled = feature_id in requested
            row.updated_by = actor_id
        for feature_id in requested - set(existing):
            self._session.add(
                ProfileFeature(
                    business_profile_id=profile.id,
                    feature_id=feature_id,
                    is_enabled=True,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
        record_audit(
            self._session,
            action="business_profile.features.updated",
            entity_type="business_profile",
            entity_id=profile.id,
            actor_id=actor_id,
        )
        self._session.commit()

    def set_profile_modules(
        self, profile_id: UUID, module_ids: list[UUID], actor_id: UUID
    ) -> None:
        profile = self.get_profile(profile_id)
        self._validate_catalog_ids(BusinessModule, module_ids, "module")
        existing = {
            row.module_id: row
            for row in self._session.scalars(
                select(ProfileModule).where(
                    ProfileModule.business_profile_id == profile.id,
                    ProfileModule.is_deleted.is_(False),
                )
            )
        }
        requested = set(module_ids)
        for module_id, row in existing.items():
            row.is_enabled = module_id in requested
            row.is_visible = module_id in requested
            row.updated_by = actor_id
        for module_id in requested - set(existing):
            self._session.add(
                ProfileModule(
                    business_profile_id=profile.id,
                    module_id=module_id,
                    is_enabled=True,
                    is_visible=True,
                    display_order=0,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
        record_audit(
            self._session,
            action="business_profile.modules.updated",
            entity_type="business_profile",
            entity_id=profile.id,
            actor_id=actor_id,
        )
        self._session.commit()

    def profile_configuration(self, profile_id: UUID) -> tuple[list[UUID], list[UUID]]:
        self.get_profile(profile_id)
        feature_ids = [
            row.feature_id
            for row in self._session.scalars(
                select(ProfileFeature).where(
                    ProfileFeature.business_profile_id == profile_id,
                    ProfileFeature.is_deleted.is_(False),
                    ProfileFeature.is_enabled.is_(True),
                )
            )
        ]
        module_ids = [
            row.module_id
            for row in self._session.scalars(
                select(ProfileModule).where(
                    ProfileModule.business_profile_id == profile_id,
                    ProfileModule.is_deleted.is_(False),
                    ProfileModule.is_enabled.is_(True),
                )
            )
        ]
        return feature_ids, module_ids

    def active_features(
        self, firm_id: UUID | None
    ) -> list[tuple[BusinessFeature, dict[str, object]]]:
        profile_id = self._resolved_profile_id(firm_id)
        assignments = {
            row.feature_id: row
            for row in self._session.scalars(
                select(ProfileFeature).where(
                    ProfileFeature.business_profile_id == profile_id,
                    ProfileFeature.is_deleted.is_(False),
                )
            )
        }
        rows = self._session.scalars(
            select(BusinessFeature).where(
                BusinessFeature.is_deleted.is_(False),
                BusinessFeature.is_active.is_(True),
            )
        ).all()
        result: list[tuple[BusinessFeature, dict[str, object]]] = []
        for feature in rows:
            assignment = assignments.get(feature.id)
            enabled = (
                assignment.is_enabled
                if assignment is not None
                else feature.default_enabled
            )
            if enabled:
                result.append(
                    (
                        feature,
                        (
                            assignment.configuration
                            if assignment and assignment.configuration
                            else {}
                        ),
                    )
                )
        return result

    def active_modules(self, firm_id: UUID | None) -> list[tuple[BusinessModule, int]]:
        profile_id = self._resolved_profile_id(firm_id)
        assignments = {
            row.module_id: row
            for row in self._session.scalars(
                select(ProfileModule).where(
                    ProfileModule.business_profile_id == profile_id,
                    ProfileModule.is_deleted.is_(False),
                )
            )
        }
        rows = self._session.scalars(
            select(BusinessModule).where(
                BusinessModule.is_deleted.is_(False),
                BusinessModule.is_active.is_(True),
            )
        ).all()
        result: list[tuple[BusinessModule, int]] = []
        for module in rows:
            assignment = assignments.get(module.id)
            enabled = (
                assignment.is_enabled
                if assignment is not None
                else module.default_enabled
            )
            visible = assignment.is_visible if assignment is not None else enabled
            if enabled and visible:
                result.append((module, assignment.display_order if assignment else 0))
        return sorted(result, key=lambda item: (item[1], item[0].name))

    def _resolved_profile_id(self, firm_id: UUID | None) -> UUID:
        if firm_id is not None:
            assignment = self._session.scalar(
                select(FirmBusinessProfile).where(
                    FirmBusinessProfile.firm_id == firm_id,
                    FirmBusinessProfile.is_deleted.is_(False),
                    FirmBusinessProfile.is_active.is_(True),
                )
            )
            if assignment is not None:
                return assignment.business_profile_id
        default_profile = self._session.scalar(
            select(BusinessProfile).where(
                BusinessProfile.is_deleted.is_(False),
                BusinessProfile.status == "ACTIVE",
                BusinessProfile.is_default.is_(True),
            )
        )
        if default_profile is not None:
            return default_profile.id
        fallback = self._session.scalar(
            select(BusinessProfile).where(
                BusinessProfile.is_deleted.is_(False),
                BusinessProfile.status == "ACTIVE",
            )
        )
        if fallback is None:
            raise ResourceNotFoundError("No active business profile is configured.")
        return fallback.id

    def _require_firm(self, firm_id: UUID) -> None:
        """Confirm the firm exists, via the platform store.

        ``firms`` lives only in the platform schema, so the request session
        cannot see it whenever the caller supplies a firm outside that store.
        """
        if not FirmMetadataReader(self._session).exists(firm_id):
            raise ResourceNotFoundError("Firm not found.")

    def _list_catalog(
        self,
        model: type[BusinessFeature] | type[BusinessModule],
        page: int,
        page_size: int,
        search: str | None,
        sort_by: str,
        descending: bool,
    ) -> tuple[list[object], int]:
        columns = {
            "code": model.code,
            "name": model.name,
            "created_at": model.created_at,
        }
        statement = select(model).where(model.is_deleted.is_(False))
        count = (
            select(func.count()).select_from(model).where(model.is_deleted.is_(False))
        )
        if search:
            condition = or_(
                model.code.ilike(f"%{search.strip()}%"),
                model.name.ilike(f"%{search.strip()}%"),
            )
            statement = statement.where(condition)
            count = count.where(condition)
        ordering = columns[sort_by].desc() if descending else columns[sort_by].asc()
        rows = self._session.scalars(
            statement.order_by(ordering).offset((page - 1) * page_size).limit(page_size)
        ).all()
        return list(rows), int(self._session.scalar(count) or 0)

    def _reject_unimplemented(self, feature_ids: list[UUID]) -> None:
        """Refuse to enable a feature nothing in the codebase implements.

        Seven catalogue entries are roadmap: they name a subsystem that does
        not exist. They stay listed so the intent is not lost, but switching
        one on would tell a firm it had a capability that can never do
        anything, so the write is refused rather than silently stored.

        Raises:
            ValidationError: If any requested feature is not implemented.

        """
        if not feature_ids:
            return
        unimplemented = self._session.scalars(
            select(BusinessFeature.code).where(
                BusinessFeature.id.in_(feature_ids),
                BusinessFeature.is_implemented.is_(False),
                BusinessFeature.is_deleted.is_(False),
            )
        ).all()
        if unimplemented:
            names = ", ".join(sorted(unimplemented))
            raise ValidationError(
                f"These features are not implemented yet and cannot be "
                f"enabled: {names}."
            )

    def _validate_catalog_ids(
        self,
        model: type[BusinessFeature] | type[BusinessModule],
        ids: list[UUID],
        label: str,
    ) -> None:
        if not ids:
            return
        valid_ids = set(
            self._session.scalars(
                select(model.id).where(model.id.in_(ids), model.is_deleted.is_(False))
            ).all()
        )
        missing = [item for item in ids if item not in valid_ids]
        if missing:
            raise ResourceNotFoundError(
                f"One or more {label} identifiers do not exist."
            )

    def _assert_unique(
        self,
        model: (
            type[BusinessProfile]
            | type[BusinessFeature]
            | type[BusinessModule]
            | type[AttributeDefinition]
        ),
        code: str,
        *,
        current_id: UUID | None = None,
    ) -> None:
        statement = select(model.id).where(
            model.code == code, model.is_deleted.is_(False)
        )
        if current_id is not None:
            statement = statement.where(model.id != current_id)
        if self._session.scalar(statement) is not None:
            raise ConflictError(f"{model.__name__} code already exists.")

    def _unset_default_profiles(self, *, except_id: UUID | None = None) -> None:
        statement = select(BusinessProfile).where(
            BusinessProfile.is_deleted.is_(False), BusinessProfile.is_default.is_(True)
        )
        for row in self._session.scalars(statement):
            if except_id is not None and row.id == except_id:
                continue
            row.is_default = False
