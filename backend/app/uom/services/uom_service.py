"""Transactional service for enterprise UOM and packaging operations."""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.uom.models import (
    BusinessProfileUomDefault,
    ConversionRule,
    IndustryTemplate,
    PackagingType,
    ProductPackagingLevel,
    ProductUomConfig,
    Uom,
    UomGroup,
)
from app.uom.schemas import (
    BusinessProfileUomDefaultUpsert,
    ConversionRequest,
    ConversionResponse,
    ConversionRuleCreate,
    ConversionRuleListFilters,
    ConversionRuleUpdate,
    IndustryTemplateCreate,
    IndustryTemplateUpdate,
    PackagingLevelCreate,
    PackagingLevelUpdate,
    PackagingTypeCreate,
    PackagingTypeUpdate,
    ProductUomConfigUpsert,
    UomCreate,
    UomGroupCreate,
    UomGroupUpdate,
    UomUpdate,
)


class UomService:
    """Coordinate UOM masters, conversions, and product packaging hierarchy."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_uoms(self, *, include_inactive: bool = False) -> list[Uom]:
        statement = select(Uom).where(Uom.is_deleted.is_(False))
        if not include_inactive:
            statement = statement.where(Uom.status == "ACTIVE")
        return list(self._session.scalars(statement.order_by(Uom.name.asc())).all())

    def create_uom(self, data: UomCreate, *, actor_id: UUID) -> Uom:
        row = Uom(
            code=data.code.strip().upper(),
            name=data.name.strip(),
            symbol=data.symbol,
            dimension=data.dimension.strip().upper(),
            status=data.status.strip().upper(),
            is_decimal_allowed=data.is_decimal_allowed,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._flush_or_conflict("UOM code already exists.")
        self._session.commit()
        return row

    def update_uom(self, uom_id: UUID, data: UomUpdate, *, actor_id: UUID) -> Uom:
        row = self.get_uom(uom_id)
        payload = data.model_dump(exclude_unset=True)
        for field, value in payload.items():
            if isinstance(value, str):
                value = value.strip()
                if field in {"code", "dimension", "status"}:
                    value = value.upper()
            setattr(row, field, value)
        row.updated_by = actor_id
        self._flush_or_conflict("UOM update conflicts with existing data.")
        self._session.commit()
        return row

    def delete_uom(self, uom_id: UUID, *, actor_id: UUID) -> None:
        row = self.get_uom(uom_id)
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.deleted_by = actor_id
        row.updated_by = actor_id
        self._session.commit()

    def get_uom(self, uom_id: UUID) -> Uom:
        row = self._session.scalar(
            select(Uom).where(Uom.id == uom_id, Uom.is_deleted.is_(False))
        )
        if row is None:
            raise ResourceNotFoundError("UOM not found.")
        return row

    def list_uom_groups(self) -> list[UomGroup]:
        return list(
            self._session.scalars(
                select(UomGroup)
                .where(UomGroup.is_deleted.is_(False))
                .order_by(UomGroup.name.asc())
            ).all()
        )

    def create_uom_group(self, data: UomGroupCreate, *, actor_id: UUID) -> UomGroup:
        row = UomGroup(
            code=data.code.strip().upper(),
            name=data.name.strip(),
            description=data.description,
            status=data.status.strip().upper(),
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._flush_or_conflict("UOM group code already exists.")
        self._session.commit()
        return row

    def update_uom_group(
        self, group_id: UUID, data: UomGroupUpdate, *, actor_id: UUID
    ) -> UomGroup:
        row = self._session.scalar(
            select(UomGroup).where(UomGroup.id == group_id, UomGroup.is_deleted.is_(False))
        )
        if row is None:
            raise ResourceNotFoundError("UOM group not found.")
        payload = data.model_dump(exclude_unset=True)
        for field, value in payload.items():
            if isinstance(value, str):
                value = value.strip()
                if field in {"code", "status"}:
                    value = value.upper()
            setattr(row, field, value)
        row.updated_by = actor_id
        self._flush_or_conflict("UOM group update conflicts with existing data.")
        self._session.commit()
        return row

    def delete_uom_group(self, group_id: UUID, *, actor_id: UUID) -> None:
        row = self._session.scalar(
            select(UomGroup).where(UomGroup.id == group_id, UomGroup.is_deleted.is_(False))
        )
        if row is None:
            raise ResourceNotFoundError("UOM group not found.")
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.deleted_by = actor_id
        row.updated_by = actor_id
        self._session.commit()

    def list_packaging_types(self) -> list[PackagingType]:
        return list(
            self._session.scalars(
                select(PackagingType)
                .where(PackagingType.is_deleted.is_(False))
                .order_by(PackagingType.name.asc())
            ).all()
        )

    def create_packaging_type(
        self, data: PackagingTypeCreate, *, actor_id: UUID
    ) -> PackagingType:
        row = PackagingType(
            code=data.code.strip().upper(),
            name=data.name.strip(),
            description=data.description,
            status=data.status.strip().upper(),
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._flush_or_conflict("Packaging type code already exists.")
        self._session.commit()
        return row

    def update_packaging_type(
        self, packaging_type_id: UUID, data: PackagingTypeUpdate, *, actor_id: UUID
    ) -> PackagingType:
        row = self._session.scalar(
            select(PackagingType).where(
                PackagingType.id == packaging_type_id, PackagingType.is_deleted.is_(False)
            )
        )
        if row is None:
            raise ResourceNotFoundError("Packaging type not found.")
        payload = data.model_dump(exclude_unset=True)
        for field, value in payload.items():
            if isinstance(value, str):
                value = value.strip()
                if field in {"code", "status"}:
                    value = value.upper()
            setattr(row, field, value)
        row.updated_by = actor_id
        self._flush_or_conflict("Packaging type update conflicts with existing data.")
        self._session.commit()
        return row

    def delete_packaging_type(self, packaging_type_id: UUID, *, actor_id: UUID) -> None:
        row = self._session.scalar(
            select(PackagingType).where(
                PackagingType.id == packaging_type_id, PackagingType.is_deleted.is_(False)
            )
        )
        if row is None:
            raise ResourceNotFoundError("Packaging type not found.")
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.deleted_by = actor_id
        row.updated_by = actor_id
        self._session.commit()

    def list_conversion_rules(
        self,
        *,
        firm_scope: UUID,
        filters: ConversionRuleListFilters,
        page: int,
        page_size: int,
    ) -> tuple[list[ConversionRule], int]:
        statement = select(ConversionRule).where(
            ConversionRule.firm_id == firm_scope,
            ConversionRule.is_deleted.is_(False),
        )
        count = select(func.count()).select_from(ConversionRule).where(
            ConversionRule.firm_id == firm_scope,
            ConversionRule.is_deleted.is_(False),
        )
        for field, value in {
            ConversionRule.product_id: filters.product_id,
            ConversionRule.business_profile_id: filters.business_profile_id,
            ConversionRule.from_uom_id: filters.from_uom_id,
            ConversionRule.to_uom_id: filters.to_uom_id,
        }.items():
            if value is not None:
                statement = statement.where(field == value)
                count = count.where(field == value)
        if filters.status:
            status = filters.status.strip().upper()
            statement = statement.where(ConversionRule.status == status)
            count = count.where(ConversionRule.status == status)
        if filters.effective_on is not None:
            on = filters.effective_on
            active_on = and_(
                ConversionRule.effective_from <= on,
                or_(ConversionRule.effective_to.is_(None), ConversionRule.effective_to >= on),
            )
            statement = statement.where(active_on)
            count = count.where(active_on)
        rows = list(
            self._session.scalars(
                statement.order_by(
                    ConversionRule.product_id.asc(),
                    ConversionRule.from_uom_id.asc(),
                    ConversionRule.version.desc(),
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        return rows, int(self._session.scalar(count) or 0)

    def create_conversion_rule(
        self, data: ConversionRuleCreate, *, firm_scope: UUID, actor_id: UUID
    ) -> ConversionRule:
        row = ConversionRule(
            firm_id=firm_scope,
            business_profile_id=data.business_profile_id,
            product_id=data.product_id,
            from_uom_id=data.from_uom_id,
            to_uom_id=data.to_uom_id,
            conversion_factor=data.conversion_factor,
            rounding_mode=data.rounding_mode.strip().upper(),
            precision_scale=data.precision_scale,
            effective_from=data.effective_from,
            effective_to=data.effective_to,
            version=data.version,
            status=data.status.strip().upper(),
            reason=data.reason,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._flush_or_conflict("Conversion rule version already exists.")
        record_audit(
            self._session,
            action="uom.conversion.created",
            entity_type="uom_conversion_rule",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
        )
        self._session.commit()
        return row

    def update_conversion_rule(
        self,
        rule_id: UUID,
        data: ConversionRuleUpdate,
        *,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> ConversionRule:
        row = self._session.scalar(
            select(ConversionRule).where(
                ConversionRule.id == rule_id,
                ConversionRule.firm_id == firm_scope,
                ConversionRule.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Conversion rule not found.")
        payload = data.model_dump(exclude_unset=True)
        for field, value in payload.items():
            if isinstance(value, str):
                value = value.strip().upper()
            setattr(row, field, value)
        row.updated_by = actor_id
        self._flush_or_conflict("Conversion rule update conflicts with existing data.")
        record_audit(
            self._session,
            action="uom.conversion.updated",
            entity_type="uom_conversion_rule",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
        )
        self._session.commit()
        return row

    def delete_conversion_rule(
        self, rule_id: UUID, *, firm_scope: UUID, actor_id: UUID
    ) -> None:
        row = self._session.scalar(
            select(ConversionRule).where(
                ConversionRule.id == rule_id,
                ConversionRule.firm_id == firm_scope,
                ConversionRule.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Conversion rule not found.")
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.deleted_by = actor_id
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="uom.conversion.deleted",
            entity_type="uom_conversion_rule",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data={"status": row.status, "version": row.version},
        )
        self._session.commit()

    def convert_quantity(
        self, request: ConversionRequest, *, firm_scope: UUID
    ) -> ConversionResponse:
        on_date = request.conversion_date or date.today()
        rule = self._resolve_conversion_rule(
            firm_scope=firm_scope,
            product_id=request.product_id,
            from_uom_id=request.from_uom_id,
            to_uom_id=request.to_uom_id,
            on_date=on_date,
        )
        precision = Decimal("1").scaleb(-int(rule.precision_scale))
        converted = (request.quantity * rule.conversion_factor).quantize(
            precision, rounding=ROUND_HALF_UP
        )
        return ConversionResponse(
            quantity=request.quantity,
            converted_quantity=converted,
            from_uom_id=request.from_uom_id,
            to_uom_id=request.to_uom_id,
            conversion_factor=rule.conversion_factor,
            version=rule.version,
            conversion_rule_id=rule.id,
            conversion_date=on_date,
        )

    def upsert_profile_default(
        self,
        *,
        firm_scope: UUID | None,
        profile_id: UUID,
        data: BusinessProfileUomDefaultUpsert,
        actor_id: UUID,
    ) -> BusinessProfileUomDefault:
        row = self._session.scalar(
            select(BusinessProfileUomDefault).where(
                BusinessProfileUomDefault.firm_id == firm_scope,
                BusinessProfileUomDefault.business_profile_id == profile_id,
                BusinessProfileUomDefault.is_deleted.is_(False),
            )
        )
        if row is None:
            row = BusinessProfileUomDefault(
                firm_id=firm_scope,
                business_profile_id=profile_id,
                created_by=actor_id,
                updated_by=actor_id,
            )
            self._session.add(row)
        payload = data.model_dump(mode="python")
        for field, value in payload.items():
            setattr(row, field, value)
        row.updated_by = actor_id
        self._flush_or_conflict("Business profile UOM defaults conflict.")
        self._session.commit()
        return row

    def get_profile_default(
        self, *, firm_scope: UUID | None, profile_id: UUID
    ) -> BusinessProfileUomDefault | None:
        return self._session.scalar(
            select(BusinessProfileUomDefault).where(
                BusinessProfileUomDefault.firm_id == firm_scope,
                BusinessProfileUomDefault.business_profile_id == profile_id,
                BusinessProfileUomDefault.is_deleted.is_(False),
            )
        )

    def upsert_product_config(
        self,
        *,
        firm_scope: UUID,
        product_id: UUID,
        data: ProductUomConfigUpsert,
        actor_id: UUID,
    ) -> ProductUomConfig:
        row = self._session.scalar(
            select(ProductUomConfig).where(
                ProductUomConfig.firm_id == firm_scope,
                ProductUomConfig.product_id == product_id,
                ProductUomConfig.is_deleted.is_(False),
            )
        )
        if row is None:
            row = ProductUomConfig(
                firm_id=firm_scope,
                product_id=product_id,
                created_by=actor_id,
                updated_by=actor_id,
            )
            self._session.add(row)
        payload = data.model_dump(mode="python")
        for field, value in payload.items():
            setattr(row, field, value)
        row.updated_by = actor_id
        self._flush_or_conflict("Product UOM config conflicts with existing data.")
        self._session.commit()
        return row

    def get_product_config(self, *, firm_scope: UUID, product_id: UUID) -> ProductUomConfig | None:
        return self._session.scalar(
            select(ProductUomConfig).where(
                ProductUomConfig.firm_id == firm_scope,
                ProductUomConfig.product_id == product_id,
                ProductUomConfig.is_deleted.is_(False),
            )
        )

    def list_packaging_levels(
        self, *, firm_scope: UUID, product_id: UUID
    ) -> list[ProductPackagingLevel]:
        return list(
            self._session.scalars(
                select(ProductPackagingLevel)
                .where(
                    ProductPackagingLevel.firm_id == firm_scope,
                    ProductPackagingLevel.product_id == product_id,
                    ProductPackagingLevel.is_deleted.is_(False),
                )
                .order_by(
                    ProductPackagingLevel.display_order.asc(),
                    ProductPackagingLevel.created_at.asc(),
                )
            ).all()
        )

    def create_packaging_level(
        self,
        *,
        firm_scope: UUID,
        product_id: UUID,
        data: PackagingLevelCreate,
        actor_id: UUID,
    ) -> ProductPackagingLevel:
        row = ProductPackagingLevel(
            firm_id=firm_scope,
            product_id=product_id,
            parent_level_id=data.parent_level_id,
            packaging_type_id=data.packaging_type_id,
            uom_id=data.uom_id,
            level_name=data.level_name.strip(),
            conversion_to_base_factor=data.conversion_to_base_factor,
            barcode=data.barcode,
            qr_code=data.qr_code,
            gtin=data.gtin,
            ean=data.ean,
            upc=data.upc,
            weight=data.weight,
            volume=data.volume,
            length=data.length,
            width=data.width,
            height=data.height,
            status=data.status.strip().upper(),
            display_order=data.display_order,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._flush_or_conflict("Packaging level conflicts with existing data.")
        self._session.commit()
        return row

    def update_packaging_level(
        self,
        *,
        firm_scope: UUID,
        product_id: UUID,
        level_id: UUID,
        data: PackagingLevelUpdate,
        actor_id: UUID,
    ) -> ProductPackagingLevel:
        row = self._session.scalar(
            select(ProductPackagingLevel).where(
                ProductPackagingLevel.id == level_id,
                ProductPackagingLevel.firm_id == firm_scope,
                ProductPackagingLevel.product_id == product_id,
                ProductPackagingLevel.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Packaging level not found.")
        payload = data.model_dump(exclude_unset=True)
        for field, value in payload.items():
            if isinstance(value, str):
                value = value.strip()
                if field == "status":
                    value = value.upper()
            setattr(row, field, value)
        row.updated_by = actor_id
        self._flush_or_conflict("Packaging level update conflicts with existing data.")
        self._session.commit()
        return row

    def delete_packaging_level(
        self,
        *,
        firm_scope: UUID,
        product_id: UUID,
        level_id: UUID,
        actor_id: UUID,
    ) -> None:
        row = self._session.scalar(
            select(ProductPackagingLevel).where(
                ProductPackagingLevel.id == level_id,
                ProductPackagingLevel.firm_id == firm_scope,
                ProductPackagingLevel.product_id == product_id,
                ProductPackagingLevel.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Packaging level not found.")
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.deleted_by = actor_id
        row.updated_by = actor_id
        self._session.commit()

    def list_industry_templates(self, *, include_inactive: bool = False) -> list[IndustryTemplate]:
        statement = select(IndustryTemplate).where(IndustryTemplate.is_deleted.is_(False))
        if not include_inactive:
            statement = statement.where(IndustryTemplate.status == "ACTIVE")
        return list(
            self._session.scalars(
                statement.order_by(IndustryTemplate.industry_type.asc(), IndustryTemplate.code.asc())
            ).all()
        )

    def create_industry_template(
        self, data: IndustryTemplateCreate, *, actor_id: UUID
    ) -> IndustryTemplate:
        row = IndustryTemplate(
            code=data.code.strip().upper(),
            name=data.name.strip(),
            industry_type=data.industry_type.strip().upper(),
            template_payload=data.template_payload,
            status=data.status.strip().upper(),
            is_system=data.is_system,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._flush_or_conflict("Industry template code already exists.")
        self._session.commit()
        return row

    def update_industry_template(
        self, template_id: UUID, data: IndustryTemplateUpdate, *, actor_id: UUID
    ) -> IndustryTemplate:
        row = self._session.scalar(
            select(IndustryTemplate).where(
                IndustryTemplate.id == template_id, IndustryTemplate.is_deleted.is_(False)
            )
        )
        if row is None:
            raise ResourceNotFoundError("Industry template not found.")
        payload = data.model_dump(exclude_unset=True)
        for field, value in payload.items():
            if isinstance(value, str):
                value = value.strip()
                if field in {"code", "industry_type", "status"}:
                    value = value.upper()
            setattr(row, field, value)
        row.updated_by = actor_id
        self._flush_or_conflict("Industry template update conflicts with existing data.")
        self._session.commit()
        return row

    def delete_industry_template(self, template_id: UUID, *, actor_id: UUID) -> None:
        row = self._session.scalar(
            select(IndustryTemplate).where(
                IndustryTemplate.id == template_id, IndustryTemplate.is_deleted.is_(False)
            )
        )
        if row is None:
            raise ResourceNotFoundError("Industry template not found.")
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.deleted_by = actor_id
        row.updated_by = actor_id
        self._session.commit()

    def _resolve_conversion_rule(
        self,
        *,
        firm_scope: UUID,
        product_id: UUID | None,
        from_uom_id: UUID,
        to_uom_id: UUID,
        on_date: date,
    ) -> ConversionRule:
        exact = self._session.scalars(
            select(ConversionRule)
            .where(
                ConversionRule.firm_id == firm_scope,
                ConversionRule.is_deleted.is_(False),
                ConversionRule.status == "ACTIVE",
                ConversionRule.from_uom_id == from_uom_id,
                ConversionRule.to_uom_id == to_uom_id,
                ConversionRule.effective_from <= on_date,
                or_(ConversionRule.effective_to.is_(None), ConversionRule.effective_to >= on_date),
                or_(ConversionRule.product_id == product_id, ConversionRule.product_id.is_(None)),
            )
            .order_by(ConversionRule.product_id.desc(), ConversionRule.version.desc())
        ).first()
        if exact is None:
            raise ValidationError("No active conversion rule is configured for this UOM pair.")
        return exact

    def _flush_or_conflict(self, message: str) -> None:
        try:
            self._session.flush()
        except IntegrityError as error:
            self._session.rollback()
            raise ConflictError(message) from error
