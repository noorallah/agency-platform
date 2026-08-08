"""Transactional service for enterprise tax framework operations."""

from collections.abc import Iterable
from datetime import date
from io import StringIO
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.sql import Select

from app.common.audit.models.audit_log import AuditLog
from app.common.audit.services import record_audit
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.products.models import Product
from app.tax.models import (
    TaxComponent,
    TaxCountryMapping,
    TaxMigrationMapping,
    TaxProfile,
    TaxProfileComponent,
    TaxSettings,
    TaxSystem,
)
from app.tax.schemas import (
    EffectiveDateRecord,
    TaxComponentSetupInput,
    TaxComponentWrite,
    TaxCountryMappingWrite,
    TaxHistoryRecord,
    TaxMigrationMappingWrite,
    TaxProfileComponentSetupInput,
    TaxProfileSetupInput,
    TaxProfileWrite,
    TaxSettingsWrite,
    TaxSetupWrite,
    TaxStatus,
    TaxSystemWrite,
)


class TaxFrameworkService:
    """Coordinate CRUD, search, bulk, import, and export for tax framework."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_systems(
        self,
        *,
        firm_scope: UUID,
        page: int,
        page_size: int,
        search: str | None,
        country_id: UUID | None,
        business_profile_id: UUID | None,
        status: TaxStatus | None,
        include_deleted: bool,
    ) -> tuple[list[TaxSystem], int]:
        statement = select(TaxSystem).where(TaxSystem.firm_id == firm_scope)
        count = select(func.count()).select_from(TaxSystem).where(
            TaxSystem.firm_id == firm_scope
        )
        if not include_deleted:
            statement = statement.where(TaxSystem.is_deleted.is_(False))
            count = count.where(TaxSystem.is_deleted.is_(False))
        if country_id is not None:
            statement = statement.where(TaxSystem.country_id == country_id)
            count = count.where(TaxSystem.country_id == country_id)
        if business_profile_id is not None:
            statement = statement.where(
                TaxSystem.business_profile_id == business_profile_id
            )
            count = count.where(TaxSystem.business_profile_id == business_profile_id)
        if status is not None:
            statement = statement.where(TaxSystem.status == status.value)
            count = count.where(TaxSystem.status == status.value)
        if search:
            term = f"%{search.strip()}%"
            condition = or_(
                TaxSystem.code.ilike(term),
                TaxSystem.name.ilike(term),
                TaxSystem.display_name.ilike(term),
                TaxSystem.description.ilike(term),
            )
            statement = statement.where(condition)
            count = count.where(condition)
        rows = self._session.scalars(
            statement
            .order_by(TaxSystem.display_order.asc(), TaxSystem.code.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return list(rows), int(self._session.scalar(count) or 0)

    def list_components(
        self,
        *,
        firm_scope: UUID,
        page: int,
        page_size: int,
        search: str | None,
        tax_system_id: UUID | None,
        status: TaxStatus | None,
        include_deleted: bool,
    ) -> tuple[list[TaxComponent], int]:
        statement = select(TaxComponent).where(TaxComponent.firm_id == firm_scope)
        count = select(func.count()).select_from(TaxComponent).where(
            TaxComponent.firm_id == firm_scope
        )
        if not include_deleted:
            statement = statement.where(TaxComponent.is_deleted.is_(False))
            count = count.where(TaxComponent.is_deleted.is_(False))
        if tax_system_id is not None:
            statement = statement.where(TaxComponent.tax_system_id == tax_system_id)
            count = count.where(TaxComponent.tax_system_id == tax_system_id)
        if status is not None:
            statement = statement.where(TaxComponent.status == status.value)
            count = count.where(TaxComponent.status == status.value)
        if search:
            term = f"%{search.strip()}%"
            condition = or_(
                TaxComponent.code.ilike(term),
                TaxComponent.name.ilike(term),
                TaxComponent.label.ilike(term),
            )
            statement = statement.where(condition)
            count = count.where(condition)
        rows = self._session.scalars(
            statement
            .order_by(TaxComponent.calculation_order.asc(), TaxComponent.code.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return list(rows), int(self._session.scalar(count) or 0)

    def list_profiles(
        self,
        *,
        firm_scope: UUID,
        page: int,
        page_size: int,
        search: str | None,
        tax_system_id: UUID | None,
        business_profile_id: UUID | None,
        status: TaxStatus | None,
        include_deleted: bool,
    ) -> tuple[list[TaxProfile], int]:
        statement = (
            select(TaxProfile)
            .where(TaxProfile.firm_id == firm_scope)
            .options(selectinload(TaxProfile.components))
        )
        count = select(func.count()).select_from(TaxProfile).where(
            TaxProfile.firm_id == firm_scope
        )
        if not include_deleted:
            statement = statement.where(TaxProfile.is_deleted.is_(False))
            count = count.where(TaxProfile.is_deleted.is_(False))
        if tax_system_id is not None:
            statement = statement.where(TaxProfile.tax_system_id == tax_system_id)
            count = count.where(TaxProfile.tax_system_id == tax_system_id)
        if business_profile_id is not None:
            statement = statement.where(
                TaxProfile.business_profile_id == business_profile_id
            )
            count = count.where(TaxProfile.business_profile_id == business_profile_id)
        if status is not None:
            statement = statement.where(TaxProfile.status == status.value)
            count = count.where(TaxProfile.status == status.value)
        if search:
            term = f"%{search.strip()}%"
            condition = or_(
                TaxProfile.code.ilike(term),
                TaxProfile.name.ilike(term),
                TaxProfile.label.ilike(term),
                TaxProfile.description.ilike(term),
            )
            statement = statement.where(condition)
            count = count.where(condition)
        rows = self._session.scalars(
            statement
            .order_by(TaxProfile.display_order.asc(), TaxProfile.code.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return list(rows), int(self._session.scalar(count) or 0)

    def list_country_mappings(
        self, *, firm_scope: UUID, include_deleted: bool
    ) -> list[TaxCountryMapping]:
        statement = select(TaxCountryMapping).where(TaxCountryMapping.firm_id == firm_scope)
        if not include_deleted:
            statement = statement.where(TaxCountryMapping.is_deleted.is_(False))
        return list(
            self._session.scalars(
                statement.order_by(
                    TaxCountryMapping.country_id.asc(),
                    TaxCountryMapping.created_at.desc(),
                )
            ).all()
        )

    def list_migration_mappings(
        self, *, firm_scope: UUID, include_deleted: bool
    ) -> list[TaxMigrationMapping]:
        statement = select(TaxMigrationMapping).where(
            TaxMigrationMapping.firm_id == firm_scope
        )
        if not include_deleted:
            statement = statement.where(TaxMigrationMapping.is_deleted.is_(False))
        return list(
            self._session.scalars(
                statement.order_by(TaxMigrationMapping.legacy_tax_code.asc())
            ).all()
        )

    def create_system(self, data: TaxSystemWrite, *, firm_id: UUID, actor_id: UUID) -> TaxSystem:
        now = utc_now()
        row = TaxSystem(
            firm_id=firm_id,
            country_id=data.country_id,
            business_profile_id=data.business_profile_id,
            code=data.code,
            name=data.name,
            display_name=data.display_name or data.name,
            description=data.description,
            status=data.status.value,
            display_order=data.display_order,
            created_by=actor_id,
            created_at=now,
            updated_by=actor_id,
            updated_at=now,
        )
        self._session.add(row)
        self._flush_conflicts("Tax system code already exists in this firm.")
        record_audit(
            self._session,
            action="tax.system.created",
            entity_type="tax_system",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={"code": row.code},
        )
        self._commit()
        return row

    def update_system(
        self, system_id: UUID, data: TaxSystemWrite, *, firm_scope: UUID, actor_id: UUID
    ) -> TaxSystem:
        row = self.get_system(system_id, firm_scope=firm_scope, include_deleted=True)
        before = {"code": row.code, "status": row.status}
        row.country_id = data.country_id
        row.business_profile_id = data.business_profile_id
        row.code = data.code
        row.name = data.name
        row.display_name = data.display_name or data.name
        row.description = data.description
        row.status = data.status.value
        row.display_order = data.display_order
        row.updated_by = actor_id
        self._flush_conflicts("Tax system code already exists in this firm.")
        record_audit(
            self._session,
            action="tax.system.updated",
            entity_type="tax_system",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data=before,
            after_data={"code": row.code, "status": row.status},
        )
        self._commit()
        return row

    def create_component(
        self, data: TaxComponentWrite, *, firm_id: UUID, actor_id: UUID
    ) -> TaxComponent:
        self._assert_system_exists(data.tax_system_id, firm_id)
        now = utc_now()
        row = TaxComponent(
            firm_id=firm_id,
            tax_system_id=data.tax_system_id,
            code=data.code,
            name=data.name,
            label=data.label or data.name,
            short_label=data.short_label,
            display_order=data.display_order,
            calculation_order=data.calculation_order,
            percentage=data.percentage,
            included_in_price=data.included_in_price,
            recoverable=data.recoverable,
            status=data.status.value,
            created_by=actor_id,
            created_at=now,
            updated_by=actor_id,
            updated_at=now,
        )
        self._session.add(row)
        self._flush_conflicts("Tax component code already exists in this tax system.")
        record_audit(
            self._session,
            action="tax.component.created",
            entity_type="tax_component",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={"code": row.code, "tax_system_id": str(row.tax_system_id)},
        )
        self._commit()
        return row

    def update_component(
        self,
        component_id: UUID,
        data: TaxComponentWrite,
        *,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> TaxComponent:
        row = self.get_component(component_id, firm_scope=firm_scope, include_deleted=True)
        self._assert_system_exists(data.tax_system_id, firm_scope)
        before = {"code": row.code, "status": row.status}
        row.tax_system_id = data.tax_system_id
        row.code = data.code
        row.name = data.name
        row.label = data.label or data.name
        row.short_label = data.short_label
        row.display_order = data.display_order
        row.calculation_order = data.calculation_order
        row.percentage = data.percentage
        row.included_in_price = data.included_in_price
        row.recoverable = data.recoverable
        row.status = data.status.value
        row.updated_by = actor_id
        self._flush_conflicts("Tax component code already exists in this tax system.")
        record_audit(
            self._session,
            action="tax.component.updated",
            entity_type="tax_component",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data=before,
            after_data={"code": row.code, "status": row.status},
        )
        self._commit()
        return row

    def create_profile(self, data: TaxProfileWrite, *, firm_id: UUID, actor_id: UUID) -> TaxProfile:
        self._assert_system_exists(data.tax_system_id, firm_id)
        now = utc_now()
        row = TaxProfile(
            firm_id=firm_id,
            tax_system_id=data.tax_system_id,
            business_profile_id=data.business_profile_id,
            code=data.code,
            name=data.name,
            label=data.label or data.name,
            description=data.description,
            status=data.status.value,
            display_order=data.display_order,
            is_historical=data.is_historical,
            group_code=data.group_code or data.code,
            effective_from=data.effective_from,
            effective_to=data.effective_to,
            created_by=actor_id,
            created_at=now,
            updated_by=actor_id,
            updated_at=now,
        )
        row.components = self._build_profile_components(
            data.components,
            firm_id=firm_id,
            tax_system_id=data.tax_system_id,
            tax_profile_id=row.id,
            actor_id=actor_id,
        )
        self._session.add(row)
        self._flush_conflicts("Tax profile code already exists in this firm.")
        record_audit(
            self._session,
            action="tax.profile.created",
            entity_type="tax_profile",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={"code": row.code},
        )
        self._commit()
        self._session.refresh(row)
        return row

    def update_profile(
        self, profile_id: UUID, data: TaxProfileWrite, *, firm_scope: UUID, actor_id: UUID
    ) -> TaxProfile:
        row = self.get_profile(profile_id, firm_scope=firm_scope, include_deleted=True)
        self._assert_system_exists(data.tax_system_id, firm_scope)
        before = {"code": row.code, "status": row.status}
        row.tax_system_id = data.tax_system_id
        row.business_profile_id = data.business_profile_id
        row.code = data.code
        row.name = data.name
        row.label = data.label or data.name
        row.description = data.description
        row.status = data.status.value
        row.display_order = data.display_order
        row.is_historical = data.is_historical
        row.group_code = data.group_code or data.code
        row.effective_from = data.effective_from
        row.effective_to = data.effective_to
        row.updated_by = actor_id
        self._reconcile_profile_components(
            row,
            data.components,
            actor_id=actor_id,
            firm_id=firm_scope,
            tax_system_id=data.tax_system_id,
        )
        self._flush_conflicts("Tax profile code already exists in this firm.")
        record_audit(
            self._session,
            action="tax.profile.updated",
            entity_type="tax_profile",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data=before,
            after_data={"code": row.code, "status": row.status},
        )
        self._commit()
        self._session.refresh(row)
        return row

    def create_country_mapping(
        self, data: TaxCountryMappingWrite, *, firm_id: UUID, actor_id: UUID
    ) -> TaxCountryMapping:
        self._assert_system_exists(data.tax_system_id, firm_id)
        now = utc_now()
        row = TaxCountryMapping(
            firm_id=firm_id,
            country_id=data.country_id,
            business_profile_id=data.business_profile_id,
            tax_system_id=data.tax_system_id,
            status=data.status.value,
            is_default=data.is_default,
            effective_from=data.effective_from,
            effective_to=data.effective_to,
            created_by=actor_id,
            created_at=now,
            updated_by=actor_id,
            updated_at=now,
        )
        self._session.add(row)
        self._flush_conflicts("Country mapping already exists for this combination.")
        record_audit(
            self._session,
            action="tax.country_mapping.created",
            entity_type="tax_country_mapping",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
        )
        self._commit()
        return row

    def update_country_mapping(
        self,
        mapping_id: UUID,
        data: TaxCountryMappingWrite,
        *,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> TaxCountryMapping:
        row = self.get_country_mapping(mapping_id, firm_scope=firm_scope, include_deleted=True)
        self._assert_system_exists(data.tax_system_id, firm_scope)
        row.country_id = data.country_id
        row.business_profile_id = data.business_profile_id
        row.tax_system_id = data.tax_system_id
        row.status = data.status.value
        row.is_default = data.is_default
        row.effective_from = data.effective_from
        row.effective_to = data.effective_to
        row.updated_by = actor_id
        self._flush_conflicts("Country mapping already exists for this combination.")
        self._commit()
        return row

    def create_migration_mapping(
        self, data: TaxMigrationMappingWrite, *, firm_id: UUID, actor_id: UUID
    ) -> TaxMigrationMapping:
        if data.target_tax_profile_id is not None:
            self.get_profile(data.target_tax_profile_id, firm_scope=firm_id)
        now = utc_now()
        row = TaxMigrationMapping(
            firm_id=firm_id,
            legacy_tax_code=data.legacy_tax_code,
            legacy_tax_name=data.legacy_tax_name,
            source_system=data.source_system,
            legacy_rate=data.legacy_rate,
            target_tax_profile_id=data.target_tax_profile_id,
            keep_historical=data.keep_historical,
            status=data.status.value,
            notes=data.notes,
            created_by=actor_id,
            created_at=now,
            updated_by=actor_id,
            updated_at=now,
        )
        self._session.add(row)
        self._flush_conflicts("Legacy mapping already exists for this tax code and name.")
        record_audit(
            self._session,
            action="tax.migration_mapping.created",
            entity_type="tax_migration_mapping",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
        )
        self._commit()
        return row

    def update_migration_mapping(
        self,
        mapping_id: UUID,
        data: TaxMigrationMappingWrite,
        *,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> TaxMigrationMapping:
        row = self.get_migration_mapping(mapping_id, firm_scope=firm_scope, include_deleted=True)
        if data.target_tax_profile_id is not None:
            self.get_profile(data.target_tax_profile_id, firm_scope=firm_scope)
        row.legacy_tax_code = data.legacy_tax_code
        row.legacy_tax_name = data.legacy_tax_name
        row.source_system = data.source_system
        row.legacy_rate = data.legacy_rate
        row.target_tax_profile_id = data.target_tax_profile_id
        row.keep_historical = data.keep_historical
        row.status = data.status.value
        row.notes = data.notes
        row.updated_by = actor_id
        self._flush_conflicts("Legacy mapping already exists for this tax code and name.")
        self._commit()
        return row

    def get_settings(self, *, firm_scope: UUID) -> TaxSettings:
        row = self._session.scalar(
            select(TaxSettings).where(
                TaxSettings.firm_id == firm_scope,
                TaxSettings.is_deleted.is_(False),
            )
        )
        if row is not None:
            return row
        created = TaxSettings(
            firm_id=firm_scope,
            primary_label="Tax",
            component_label="Component",
            profile_label="Profile",
            report_label="Tax",
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        self._session.add(created)
        self._session.flush()
        self._commit()
        return created

    def update_settings(
        self, data: TaxSettingsWrite, *, firm_scope: UUID, actor_id: UUID
    ) -> TaxSettings:
        row = self.get_settings(firm_scope=firm_scope)
        row.primary_label = data.primary_label
        row.component_label = data.component_label
        row.profile_label = data.profile_label
        row.report_label = data.report_label
        row.allow_mixed_historical = data.allow_mixed_historical
        row.additional_settings = data.additional_settings
        row.updated_by = actor_id
        self._commit()
        return row

    def export_systems_csv(self, *, firm_scope: UUID, search: str | None) -> str:
        rows, _ = self.list_systems(
            firm_scope=firm_scope,
            page=1,
            page_size=5000,
            search=search,
            country_id=None,
            business_profile_id=None,
            status=None,
            include_deleted=False,
        )
        output = StringIO()
        output.write(
            "Code,Name,DisplayName,Status,DisplayOrder\n"
        )
        for row in rows:
            output.write(
                f"{row.code},{row.name},{row.display_name},{row.status},{row.display_order}\n"
            )
        return output.getvalue()

    def import_systems(
        self, systems: list[TaxSystemWrite], *, firm_scope: UUID, actor_id: UUID
    ) -> list[TaxSystem]:
        created: list[TaxSystem] = []
        for entry in systems:
            created.append(self.create_system(entry, firm_id=firm_scope, actor_id=actor_id))
        return created

    def bulk_delete_systems(
        self, ids: Iterable[UUID], *, firm_scope: UUID, actor_id: UUID
    ) -> int:
        return self._bulk_mark_deleted(
            TaxSystem,
            ids,
            firm_scope=firm_scope,
            actor_id=actor_id,
            checker=self._ensure_system_can_be_deleted,
        )

    def bulk_restore_systems(
        self, ids: Iterable[UUID], *, firm_scope: UUID, actor_id: UUID
    ) -> int:
        return self._bulk_restore(TaxSystem, ids, firm_scope=firm_scope, actor_id=actor_id)

    def bulk_delete_components(
        self, ids: Iterable[UUID], *, firm_scope: UUID, actor_id: UUID
    ) -> int:
        return self._bulk_mark_deleted(TaxComponent, ids, firm_scope=firm_scope, actor_id=actor_id)

    def bulk_restore_components(
        self, ids: Iterable[UUID], *, firm_scope: UUID, actor_id: UUID
    ) -> int:
        return self._bulk_restore(
            TaxComponent, ids, firm_scope=firm_scope, actor_id=actor_id
        )

    def bulk_delete_profiles(
        self, ids: Iterable[UUID], *, firm_scope: UUID, actor_id: UUID
    ) -> int:
        return self._bulk_mark_deleted(
            TaxProfile,
            ids,
            firm_scope=firm_scope,
            actor_id=actor_id,
            checker=self._ensure_profile_can_be_deleted,
        )

    def bulk_restore_profiles(
        self, ids: Iterable[UUID], *, firm_scope: UUID, actor_id: UUID
    ) -> int:
        return self._bulk_restore(TaxProfile, ids, firm_scope=firm_scope, actor_id=actor_id)

    def bulk_profile_status(
        self, ids: Iterable[UUID], status: TaxStatus, *, firm_scope: UUID, actor_id: UUID
    ) -> int:
        rows = self._session.scalars(
            select(TaxProfile).where(
                TaxProfile.id.in_(list(ids)),
                TaxProfile.firm_id == firm_scope,
                TaxProfile.is_deleted.is_(False),
            )
        ).all()
        for row in rows:
            row.status = status.value
            row.updated_by = actor_id
        if rows:
            self._commit()
        return len(rows)

    def effective_dates(self, *, firm_scope: UUID) -> list[EffectiveDateRecord]:
        result: list[EffectiveDateRecord] = []
        profiles = self._session.scalars(
            select(TaxProfile).where(
                TaxProfile.firm_id == firm_scope,
                TaxProfile.is_deleted.is_(False),
            )
        ).all()
        for row in profiles:
            result.append(
                EffectiveDateRecord(
                    entity_type="PROFILE",
                    entity_id=row.id,
                    code=row.code,
                    name=row.name,
                    status=row.status,
                    effective_from=row.effective_from,
                    effective_to=row.effective_to,
                )
            )
        result.sort(key=lambda item: item.code)
        return result

    def resolve_profile_for_product(
        self,
        product: Product,
        document_date: date,
        *,
        firm_scope: UUID,
    ) -> TaxProfile | None:
        """Return the tax profile version a product attracts on a document date.

        Products reference a tax group by its version-stable ``group_code``, so
        the rate a document carries is decided by the document's own date. That
        keeps a back-dated document on the rate that applied when it was
        supplied, and lets a rate change take effect without touching products.
        """
        if not product.tax_profile_group_code:
            return None
        return self.resolve_active_profile(
            product.tax_profile_group_code, document_date, firm_scope=firm_scope
        )

    def assert_profile_effective_on(
        self, profile_id: UUID, document_date: date, *, firm_scope: UUID
    ) -> TaxProfile:
        """Return a profile only when it was in effect on the document date.

        A caller may name a profile version explicitly. Accepting one whose
        effective window does not cover the document would post a rate that was
        never in force, so the window is checked rather than assumed.
        """
        profile = self._session.scalar(
            select(TaxProfile).where(
                TaxProfile.id == profile_id,
                TaxProfile.firm_id == firm_scope,
                TaxProfile.is_deleted.is_(False),
            )
        )
        if profile is None:
            raise ValidationError("Selected tax profile is not available in this firm.")
        if profile.status != TaxStatus.ACTIVE.value:
            raise ValidationError("Inactive tax profiles cannot be used.")
        starts = profile.effective_from
        ends = profile.effective_to
        if (starts is not None and document_date < starts) or (
            ends is not None and document_date > ends
        ):
            raise ValidationError(
                f"Tax profile {profile.code} was not in effect on {document_date}.",
                details={
                    "effective_from": str(starts) if starts else None,
                    "effective_to": str(ends) if ends else None,
                },
            )
        return profile

    def resolve_active_profile(
        self, group_code: str, transaction_date: date, *, firm_scope: UUID
    ) -> TaxProfile | None:
        """Return the active profile for a group_code on a given transaction date."""
        return self._session.scalar(
            select(TaxProfile)
            .where(
                TaxProfile.firm_id == firm_scope,
                TaxProfile.group_code == group_code,
                TaxProfile.is_deleted.is_(False),
                TaxProfile.status == "ACTIVE",
                or_(
                    TaxProfile.effective_from.is_(None),
                    TaxProfile.effective_from <= transaction_date,
                ),
                or_(
                    TaxProfile.effective_to.is_(None),
                    TaxProfile.effective_to >= transaction_date,
                ),
            )
            .options(selectinload(TaxProfile.components))
            .order_by(TaxProfile.effective_from.desc().nullslast())
            .limit(1)
        )

    def history(self, *, firm_scope: UUID, limit: int = 200) -> list[TaxHistoryRecord]:
        rows = self._session.scalars(
            select(AuditLog)
            .where(
                AuditLog.firm_id == firm_scope,
                AuditLog.entity_type.in_(
                    [
                        "tax_system",
                        "tax_component",
                        "tax_profile",
                        "tax_country_mapping",
                        "tax_migration_mapping",
                    ]
                ),
            )
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        ).all()
        return [
            TaxHistoryRecord(
                id=row.id,
                action=row.action,
                entity_type=row.entity_type,
                entity_id=row.entity_id,
                actor_id=row.actor_id,
                created_at=row.created_at,
            )
            for row in rows
        ]

    def get_system(self, system_id: UUID, *, firm_scope: UUID, include_deleted: bool = False) -> TaxSystem:
        row = self._session.scalar(
            self._by_id(TaxSystem, system_id, firm_scope=firm_scope, include_deleted=include_deleted)
        )
        if row is None:
            raise ResourceNotFoundError("Tax system not found.")
        return row

    def get_component(
        self, component_id: UUID, *, firm_scope: UUID, include_deleted: bool = False
    ) -> TaxComponent:
        row = self._session.scalar(
            self._by_id(
                TaxComponent,
                component_id,
                firm_scope=firm_scope,
                include_deleted=include_deleted,
            )
        )
        if row is None:
            raise ResourceNotFoundError("Tax component not found.")
        return row

    def get_profile(self, profile_id: UUID, *, firm_scope: UUID, include_deleted: bool = False) -> TaxProfile:
        row = self._session.scalar(
            self._by_id(
                TaxProfile,
                profile_id,
                firm_scope=firm_scope,
                include_deleted=include_deleted,
                options=[selectinload(TaxProfile.components)],
            )
        )
        if row is None:
            raise ResourceNotFoundError("Tax profile not found.")
        return row

    def get_country_mapping(
        self, mapping_id: UUID, *, firm_scope: UUID, include_deleted: bool = False
    ) -> TaxCountryMapping:
        row = self._session.scalar(
            self._by_id(
                TaxCountryMapping,
                mapping_id,
                firm_scope=firm_scope,
                include_deleted=include_deleted,
            )
        )
        if row is None:
            raise ResourceNotFoundError("Tax country mapping not found.")
        return row

    def get_migration_mapping(
        self, mapping_id: UUID, *, firm_scope: UUID, include_deleted: bool = False
    ) -> TaxMigrationMapping:
        row = self._session.scalar(
            self._by_id(
                TaxMigrationMapping,
                mapping_id,
                firm_scope=firm_scope,
                include_deleted=include_deleted,
            )
        )
        if row is None:
            raise ResourceNotFoundError("Tax migration mapping not found.")
        return row

    def delete_system(self, system_id: UUID, *, firm_scope: UUID, actor_id: UUID) -> None:
        row = self.get_system(system_id, firm_scope=firm_scope)
        self._ensure_system_can_be_deleted(row.id, firm_scope=firm_scope)
        self._soft_delete(row, actor_id=actor_id)
        self._commit()

    def restore_system(self, system_id: UUID, *, firm_scope: UUID, actor_id: UUID) -> TaxSystem:
        row = self.get_system(system_id, firm_scope=firm_scope, include_deleted=True)
        self._restore_row(row, actor_id=actor_id)
        self._commit()
        return row

    def delete_component(self, component_id: UUID, *, firm_scope: UUID, actor_id: UUID) -> None:
        row = self.get_component(component_id, firm_scope=firm_scope)
        self._soft_delete(row, actor_id=actor_id)
        self._commit()

    def restore_component(
        self, component_id: UUID, *, firm_scope: UUID, actor_id: UUID
    ) -> TaxComponent:
        row = self.get_component(component_id, firm_scope=firm_scope, include_deleted=True)
        self._restore_row(row, actor_id=actor_id)
        self._commit()
        return row

    def delete_profile(self, profile_id: UUID, *, firm_scope: UUID, actor_id: UUID) -> None:
        row = self.get_profile(profile_id, firm_scope=firm_scope)
        self._ensure_profile_can_be_deleted(row.id, firm_scope=firm_scope)
        self._soft_delete(row, actor_id=actor_id)
        self._commit()

    def restore_profile(self, profile_id: UUID, *, firm_scope: UUID, actor_id: UUID) -> TaxProfile:
        row = self.get_profile(profile_id, firm_scope=firm_scope, include_deleted=True)
        self._restore_row(row, actor_id=actor_id)
        self._commit()
        self._session.refresh(row)
        return row

    def delete_country_mapping(
        self, mapping_id: UUID, *, firm_scope: UUID, actor_id: UUID
    ) -> None:
        row = self.get_country_mapping(mapping_id, firm_scope=firm_scope)
        self._soft_delete(row, actor_id=actor_id)
        self._commit()

    def delete_migration_mapping(
        self, mapping_id: UUID, *, firm_scope: UUID, actor_id: UUID
    ) -> None:
        row = self.get_migration_mapping(mapping_id, firm_scope=firm_scope)
        self._soft_delete(row, actor_id=actor_id)
        self._commit()

    def _assert_system_exists(self, system_id: UUID, firm_scope: UUID) -> None:
        self.get_system(system_id, firm_scope=firm_scope)

    def _build_profile_components(
        self,
        components: list[Any],
        *,
        firm_id: UUID,
        tax_system_id: UUID,
        tax_profile_id: UUID,
        actor_id: UUID,
    ) -> list[TaxProfileComponent]:
        result: list[TaxProfileComponent] = []
        for item in components:
            component = self.get_component(item.tax_component_id, firm_scope=firm_id)
            if component.tax_system_id != tax_system_id:
                raise ValidationError(
                    "Profile components must belong to the selected tax system."
                )
            result.append(
                TaxProfileComponent(
                    firm_id=firm_id,
                    tax_profile_id=tax_profile_id,
                    tax_component_id=item.tax_component_id,
                    label=item.label,
                    short_label=item.short_label,
                    calculation_order=item.calculation_order,
                    percentage=item.percentage,
                    included_in_price=item.included_in_price,
                    recoverable=item.recoverable,
                    created_by=actor_id,
                    created_at=utc_now(),
                    updated_by=actor_id,
                    updated_at=utc_now(),
                )
            )
        return result

    def _reconcile_profile_components(
        self,
        profile: TaxProfile,
        components: list[Any],
        *,
        actor_id: UUID,
        firm_id: UUID,
        tax_system_id: UUID,
    ) -> None:
        existing = {row.tax_component_id: row for row in profile.components}
        requested = {item.tax_component_id for item in components}
        now = utc_now()
        for item in components:
            component = self.get_component(item.tax_component_id, firm_scope=firm_id)
            if component.tax_system_id != tax_system_id:
                raise ValidationError(
                    "Profile components must belong to the selected tax system."
                )
            current = existing.get(item.tax_component_id)
            if current is None:
                profile.components.append(
                    TaxProfileComponent(
                        firm_id=firm_id,
                        tax_profile_id=profile.id,
                        tax_component_id=item.tax_component_id,
                        label=item.label,
                        short_label=item.short_label,
                        calculation_order=item.calculation_order,
                        percentage=item.percentage,
                        included_in_price=item.included_in_price,
                        recoverable=item.recoverable,
                        created_by=actor_id,
                        created_at=utc_now(),
                        updated_by=actor_id,
                        updated_at=utc_now(),
                    )
                )
                continue
            current.label = item.label
            current.short_label = item.short_label
            current.calculation_order = item.calculation_order
            current.percentage = item.percentage
            current.included_in_price = item.included_in_price
            current.recoverable = item.recoverable
            current.is_deleted = False
            current.deleted_at = None
            current.deleted_by = None
            current.updated_by = actor_id
        for component_id, row in existing.items():
            if component_id not in requested:
                row.is_deleted = True
                row.deleted_at = now
                row.deleted_by = actor_id
                row.updated_by = actor_id

    def _bulk_mark_deleted(
        self,
        model: Any,
        ids: Iterable[UUID],
        *,
        firm_scope: UUID,
        actor_id: UUID,
        checker: Any = None,
    ) -> int:
        count = 0
        for row_id in ids:
            row = self._session.scalar(self._by_id(model, row_id, firm_scope=firm_scope))
            if row is None or row.is_deleted:
                continue
            if checker is not None:
                checker(row.id, firm_scope=firm_scope)
            self._soft_delete(row, actor_id=actor_id)
            count += 1
        if count:
            self._commit()
        return count

    def _bulk_restore(
        self, model: Any, ids: Iterable[UUID], *, firm_scope: UUID, actor_id: UUID
    ) -> int:
        count = 0
        for row_id in ids:
            row = self._session.scalar(
                self._by_id(model, row_id, firm_scope=firm_scope, include_deleted=True)
            )
            if row is None or not row.is_deleted:
                continue
            self._restore_row(row, actor_id=actor_id)
            count += 1
        if count:
            self._commit()
        return count

    def _ensure_system_can_be_deleted(self, system_id: UUID, *, firm_scope: UUID) -> None:
        has_component = self._session.scalar(
            select(TaxComponent.id).where(
                TaxComponent.firm_id == firm_scope,
                TaxComponent.tax_system_id == system_id,
                TaxComponent.is_deleted.is_(False),
            )
        )
        if has_component is not None:
            raise ValidationError("Tax systems with active components cannot be deleted.")
        has_profile = self._session.scalar(
            select(TaxProfile.id).where(
                TaxProfile.firm_id == firm_scope,
                TaxProfile.tax_system_id == system_id,
                TaxProfile.is_deleted.is_(False),
            )
        )
        if has_profile is not None:
            raise ValidationError("Tax systems with active profiles cannot be deleted.")

    def _ensure_profile_can_be_deleted(self, profile_id: UUID, *, firm_scope: UUID) -> None:
        profile = self.get_profile(profile_id, firm_scope=firm_scope)
        if profile.group_code:
            in_use = self._session.scalar(
                select(Product.id).where(
                    Product.firm_id == firm_scope,
                    Product.tax_profile_group_code == profile.group_code,
                    Product.is_deleted.is_(False),
                )
            )
            if in_use is not None:
                raise ValidationError("Tax profile group assigned to active products cannot be deleted.")

    @staticmethod
    def _soft_delete(row: Any, *, actor_id: UUID) -> None:
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.deleted_by = actor_id
        row.updated_by = actor_id

    @staticmethod
    def _restore_row(row: Any, *, actor_id: UUID) -> None:
        row.is_deleted = False
        row.deleted_at = None
        row.deleted_by = None
        row.updated_by = actor_id

    @staticmethod
    def _by_id(
        model: Any,
        row_id: UUID,
        *,
        firm_scope: UUID,
        include_deleted: bool = False,
        options: list[Any] | None = None,
    ) -> Select[Any]:
        statement = select(model).where(model.id == row_id, model.firm_id == firm_scope)
        if options:
            statement = statement.options(*options)
        if not include_deleted:
            statement = statement.where(model.is_deleted.is_(False))
        return statement

    def create_setup(
        self,
        data: TaxSetupWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> tuple[TaxSystem, list[TaxComponent], list[TaxProfile]]:
        """Create a full tax system with components and profiles in one transaction."""
        # 1. Create system
        system = self._create_system_no_commit(data, firm_id=firm_id, actor_id=actor_id)
        self._session.flush()

        # 2. Create components — build code→component map
        components: list[TaxComponent] = []
        code_to_component: dict[str, TaxComponent] = {}
        for comp_input in data.components:
            comp = self._create_component_no_commit(
                system_id=system.id,
                data=comp_input,
                firm_id=firm_id,
                actor_id=actor_id,
            )
            components.append(comp)
            code_to_component[comp_input.code] = comp
        self._session.flush()

        # 3. Create profiles — resolve component codes to objects
        profiles: list[TaxProfile] = []
        for prof_input in data.profiles:
            prof = self._create_profile_no_commit(
                system_id=system.id,
                data=prof_input,
                code_to_component=code_to_component,
                firm_id=firm_id,
                actor_id=actor_id,
            )
            profiles.append(prof)
        self._session.flush()

        record_audit(
            self._session,
            action="tax.setup.created",
            entity_type="tax_system",
            entity_id=system.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={
                "code": system.code,
                "component_count": len(components),
                "profile_count": len(profiles),
            },
        )
        self._commit()
        self._session.refresh(system)
        for comp in components:
            self._session.refresh(comp)
        for prof in profiles:
            self._session.refresh(prof)
        return system, components, profiles

    def update_setup(
        self,
        system_id: UUID,
        data: TaxSetupWrite,
        *,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> tuple[TaxSystem, list[TaxComponent], list[TaxProfile]]:
        """Update a tax system's components and profiles in one transaction.

        - Component/profile with id → update existing
        - Component/profile without id → create new
        - Components/profiles not mentioned → left untouched (soft-delete manually if needed)
        """
        # 1. Update system
        system = self.get_system(system_id, firm_scope=firm_scope, include_deleted=False)
        before = {"code": system.code, "status": system.status}
        system.country_id = data.country_id
        system.business_profile_id = data.business_profile_id
        system.code = data.code
        system.name = data.name
        system.display_name = data.display_name or data.name
        system.description = data.description
        system.status = data.status.value
        system.display_order = data.display_order
        system.updated_by = actor_id
        self._session.flush()

        # 2. Upsert components
        components: list[TaxComponent] = []
        code_to_component: dict[str, TaxComponent] = {}
        for comp_input in data.components:
            if comp_input.id is not None:
                comp = self.get_component(comp_input.id, firm_scope=firm_scope, include_deleted=False)
                comp.code = comp_input.code
                comp.name = comp_input.name
                comp.label = comp_input.label or comp_input.name
                comp.short_label = comp_input.short_label or comp_input.code
                comp.display_order = comp_input.display_order
                comp.calculation_order = comp_input.calculation_order
                comp.percentage = comp_input.percentage
                comp.included_in_price = comp_input.included_in_price
                comp.recoverable = comp_input.recoverable
                comp.status = comp_input.status.value
                comp.updated_by = actor_id
            else:
                comp = self._create_component_no_commit(
                    system_id=system_id,
                    data=comp_input,
                    firm_id=firm_scope,
                    actor_id=actor_id,
                )
            components.append(comp)
            code_to_component[comp_input.code] = comp
        self._session.flush()

        # 3. Upsert profiles
        profiles: list[TaxProfile] = []
        for prof_input in data.profiles:
            if prof_input.id is not None:
                prof = self.get_profile(prof_input.id, firm_scope=firm_scope, include_deleted=False)
                prof.code = prof_input.code
                prof.name = prof_input.name
                prof.label = prof_input.label or prof_input.name
                prof.description = prof_input.description
                prof.status = prof_input.status.value
                prof.display_order = prof_input.display_order
                prof.is_historical = prof_input.is_historical
                prof.group_code = prof_input.group_code or prof_input.code
                prof.effective_from = prof_input.effective_from
                prof.effective_to = prof_input.effective_to
                prof.business_profile_id = prof_input.business_profile_id
                prof.updated_by = actor_id
                self._reconcile_profile_components_from_setup(
                    prof, prof_input.components, code_to_component,
                    actor_id=actor_id, firm_id=firm_scope,
                )
            else:
                prof = self._create_profile_no_commit(
                    system_id=system_id,
                    data=prof_input,
                    code_to_component=code_to_component,
                    firm_id=firm_scope,
                    actor_id=actor_id,
                )
            profiles.append(prof)
        self._session.flush()

        record_audit(
            self._session,
            action="tax.setup.updated",
            entity_type="tax_system",
            entity_id=system.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data=before,
            after_data={
                "code": system.code,
                "component_count": len(components),
                "profile_count": len(profiles),
            },
        )
        self._commit()
        self._session.refresh(system)
        for comp in components:
            self._session.refresh(comp)
        for prof in profiles:
            self._session.refresh(prof)
        return system, components, profiles

    def get_setup(
        self,
        system_id: UUID,
        *,
        firm_scope: UUID,
    ) -> tuple[TaxSystem, list[TaxComponent], list[TaxProfile]]:
        """Fetch full setup (system + all components + all profiles) for one system."""
        system = self.get_system(system_id, firm_scope=firm_scope, include_deleted=False)
        components = list(
            self._session.scalars(
                select(TaxComponent)
                .where(
                    TaxComponent.firm_id == firm_scope,
                    TaxComponent.tax_system_id == system_id,
                    TaxComponent.is_deleted.is_(False),
                )
                .order_by(TaxComponent.calculation_order.asc(), TaxComponent.code.asc())
            ).all()
        )
        profiles = list(
            self._session.scalars(
                select(TaxProfile)
                .where(
                    TaxProfile.firm_id == firm_scope,
                    TaxProfile.tax_system_id == system_id,
                    TaxProfile.is_deleted.is_(False),
                )
                .options(selectinload(TaxProfile.components))
                .order_by(TaxProfile.display_order.asc(), TaxProfile.code.asc())
            ).all()
        )
        return system, components, profiles

    def _create_system_no_commit(
        self, data: TaxSetupWrite, *, firm_id: UUID, actor_id: UUID
    ) -> TaxSystem:
        now = utc_now()
        row = TaxSystem(
            firm_id=firm_id,
            country_id=data.country_id,
            business_profile_id=data.business_profile_id,
            code=data.code,
            name=data.name,
            display_name=data.display_name or data.name,
            description=data.description,
            status=data.status.value,
            display_order=data.display_order,
            created_by=actor_id,
            created_at=now,
            updated_by=actor_id,
            updated_at=now,
        )
        self._session.add(row)
        self._flush_conflicts("Tax system code already exists in this firm.")
        return row

    def _create_component_no_commit(
        self,
        *,
        system_id: UUID,
        data: TaxComponentSetupInput,
        firm_id: UUID,
        actor_id: UUID,
    ) -> TaxComponent:
        now = utc_now()
        row = TaxComponent(
            firm_id=firm_id,
            tax_system_id=system_id,
            code=data.code,
            name=data.name,
            label=data.label or data.name,
            short_label=data.short_label or data.code,
            display_order=data.display_order,
            calculation_order=data.calculation_order,
            percentage=data.percentage,
            included_in_price=data.included_in_price,
            recoverable=data.recoverable,
            status=data.status.value,
            created_by=actor_id,
            created_at=now,
            updated_by=actor_id,
            updated_at=now,
        )
        self._session.add(row)
        return row

    def _create_profile_no_commit(
        self,
        *,
        system_id: UUID,
        data: TaxProfileSetupInput,
        code_to_component: dict[str, TaxComponent],
        firm_id: UUID,
        actor_id: UUID,
    ) -> TaxProfile:
        now = utc_now()
        row = TaxProfile(
            firm_id=firm_id,
            tax_system_id=system_id,
            business_profile_id=data.business_profile_id,
            code=data.code,
            name=data.name,
            label=data.label or data.name,
            description=data.description,
            status=data.status.value,
            display_order=data.display_order,
            is_historical=data.is_historical,
            group_code=data.group_code or data.code,
            effective_from=data.effective_from,
            effective_to=data.effective_to,
            created_by=actor_id,
            created_at=now,
            updated_by=actor_id,
            updated_at=now,
        )
        profile_components = []
        for pc_input in data.components:
            comp = code_to_component[pc_input.component_code]
            pc = TaxProfileComponent(
                firm_id=firm_id,
                tax_profile_id=row.id,
                tax_component_id=comp.id,
                label=pc_input.label or comp.label,
                short_label=pc_input.short_label or comp.short_label,
                calculation_order=pc_input.calculation_order,
                percentage=pc_input.percentage,
                included_in_price=pc_input.included_in_price,
                recoverable=pc_input.recoverable,
                created_by=actor_id,
                created_at=now,
                updated_by=actor_id,
                updated_at=now,
            )
            profile_components.append(pc)
        row.components = profile_components
        self._session.add(row)
        return row

    def _reconcile_profile_components_from_setup(
        self,
        profile: TaxProfile,
        inputs: list[TaxProfileComponentSetupInput],
        code_to_component: dict[str, TaxComponent],
        *,
        actor_id: UUID,
        firm_id: UUID,
    ) -> None:
        now = utc_now()
        existing = {pc.tax_component_id: pc for pc in profile.components if not pc.is_deleted}
        wanted = {code_to_component[pc_input.component_code].id: pc_input for pc_input in inputs}

        # Remove components not in the new list
        for comp_id, pc in existing.items():
            if comp_id not in wanted:
                self._soft_delete(pc, actor_id=actor_id)

        # Add or update
        for comp_id, pc_input in wanted.items():
            comp = code_to_component[pc_input.component_code]
            if comp_id in existing:
                pc = existing[comp_id]
                pc.label = pc_input.label or comp.label
                pc.short_label = pc_input.short_label or comp.short_label
                pc.calculation_order = pc_input.calculation_order
                pc.percentage = pc_input.percentage
                pc.included_in_price = pc_input.included_in_price
                pc.recoverable = pc_input.recoverable
                pc.updated_by = actor_id
            else:
                new_pc = TaxProfileComponent(
                    firm_id=firm_id,
                    tax_profile_id=profile.id,
                    tax_component_id=comp_id,
                    label=pc_input.label or comp.label,
                    short_label=pc_input.short_label or comp.short_label,
                    calculation_order=pc_input.calculation_order,
                    percentage=pc_input.percentage,
                    included_in_price=pc_input.included_in_price,
                    recoverable=pc_input.recoverable,
                    created_by=actor_id,
                    created_at=now,
                    updated_by=actor_id,
                    updated_at=now,
                )
                self._session.add(new_pc)

    def _flush_conflicts(self, conflict_message: str) -> None:
        try:
            self._session.flush()
        except IntegrityError as error:
            self._session.rollback()
            raise ConflictError(conflict_message) from error

    def _commit(self) -> None:
        self._session.commit()
