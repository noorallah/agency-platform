"""Transactional service for enterprise UOM and packaging operations."""

from __future__ import annotations

from datetime import date
from decimal import (
    ROUND_CEILING,
    ROUND_DOWN,
    ROUND_FLOOR,
    ROUND_HALF_DOWN,
    ROUND_HALF_EVEN,
    ROUND_HALF_UP,
    ROUND_UP,
    Decimal,
)
from uuid import UUID

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.business.gating import resolve_profile_id
from app.common.audit.services import record_audit
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.products.models import Product
from app.uom.models import (
    BusinessProfileUomDefault,
    ConversionRule,
    IndustryTemplate,
    PackagingType,
    ProductPackagingLevel,
    Uom,
    UomGroup,
    UomGroupUnit,
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
    UomCreate,
    UomGroupCreate,
    UomGroupUpdate,
    UomUpdate,
)

# The rule stores a rounding mode and the conversion ignored it, always rounding
# half up. A firm that configured DOWN on a strip conversion still received a
# rounded-up quantity.
ROUNDING_MODES = {
    "HALF_UP": ROUND_HALF_UP,
    "HALF_DOWN": ROUND_HALF_DOWN,
    "HALF_EVEN": ROUND_HALF_EVEN,
    "UP": ROUND_UP,
    "DOWN": ROUND_DOWN,
    "CEILING": ROUND_CEILING,
    "FLOOR": ROUND_FLOOR,
}


class UomService:
    """Coordinate UOM masters, conversions, and product packaging hierarchy."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request unit of work."""
        self._session = session

    def list_uoms(self, *, include_inactive: bool = False) -> list[Uom]:
        """Return the unit catalogue, active units only by default."""
        statement = select(Uom).where(Uom.is_deleted.is_(False))
        if not include_inactive:
            statement = statement.where(Uom.status == "ACTIVE")
        return list(self._session.scalars(statement.order_by(Uom.name.asc())).all())

    def create_uom(self, data: UomCreate, *, actor_id: UUID) -> Uom:
        """Add a unit to the catalogue."""
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
        """Change a unit in the catalogue."""
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
        """Soft delete a unit nothing still references."""
        row = self.get_uom(uom_id)
        self._assert_uom_unused(uom_id)
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.deleted_by = actor_id
        row.updated_by = actor_id
        self._session.commit()

    def get_uom(self, uom_id: UUID) -> Uom:
        """Return one live unit."""
        row = self._session.scalar(
            select(Uom).where(Uom.id == uom_id, Uom.is_deleted.is_(False))
        )
        if row is None:
            raise ResourceNotFoundError("UOM not found.")
        return row

    @staticmethod
    def _rounding_mode(value: str) -> str:
        """Return a rounding mode the conversion can actually apply."""
        mode = value.strip().upper()
        if mode not in ROUNDING_MODES:
            raise ValidationError(
                f"rounding_mode must be one of {', '.join(sorted(ROUNDING_MODES))}."
            )
        return mode

    def _assert_uom_unused(self, uom_id: UUID) -> None:
        """Refuse to delete a unit anything still points at.

        The UOM catalogue has no firm_id: in a SHARED deployment every firm in
        the store reads the same rows, so an unguarded delete took a unit out
        from under another firm's products and conversion rules. Usage is
        therefore checked across the whole store, not just the caller's firm.

        A product's units are columns on ``products``. This checked
        ``product_uom_configs`` instead -- a parallel table holding the same
        seven slots that nothing ever wrote, so the guard passed no matter how
        many products used the unit, and deleting STRIP left every medicine
        pointing at a unit the catalogue no longer offered. That table is gone
        (``20260812_0068``); this reads the columns documents actually convert
        with.
        """
        references = (
            (
                ConversionRule,
                or_(
                    ConversionRule.from_uom_id == uom_id,
                    ConversionRule.to_uom_id == uom_id,
                ),
            ),
            (UomGroupUnit, UomGroupUnit.uom_id == uom_id),
            (ProductPackagingLevel, ProductPackagingLevel.uom_id == uom_id),
            (
                Product,
                or_(
                    Product.base_uom_id == uom_id,
                    Product.inventory_uom_id == uom_id,
                    Product.purchase_uom_id == uom_id,
                    Product.sales_uom_id == uom_id,
                    Product.default_receiving_uom_id == uom_id,
                    Product.default_dispatch_uom_id == uom_id,
                    Product.minimum_sales_uom_id == uom_id,
                ),
            ),
            (
                BusinessProfileUomDefault,
                or_(
                    BusinessProfileUomDefault.base_uom_id == uom_id,
                    BusinessProfileUomDefault.inventory_uom_id == uom_id,
                    BusinessProfileUomDefault.purchase_uom_id == uom_id,
                    BusinessProfileUomDefault.sales_uom_id == uom_id,
                ),
            ),
        )
        for model, condition in references:
            in_use = self._session.scalar(
                select(model.id).where(condition, model.is_deleted.is_(False)).limit(1)
            )
            if in_use is not None:
                raise ValidationError(
                    "This unit is in use and cannot be deleted. Deactivate it instead."
                )

    def list_uom_groups(self) -> list[UomGroup]:
        """Return the unit groups by name."""
        return list(
            self._session.scalars(
                select(UomGroup)
                .where(UomGroup.is_deleted.is_(False))
                .order_by(UomGroup.name.asc())
            ).all()
        )

    def create_uom_group(self, data: UomGroupCreate, *, actor_id: UUID) -> UomGroup:
        """Add a unit group."""
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
        """Change a unit group."""
        row = self._session.scalar(
            select(UomGroup).where(
                UomGroup.id == group_id, UomGroup.is_deleted.is_(False)
            )
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
        """Soft delete a group that holds no units."""
        row = self._session.scalar(
            select(UomGroup).where(
                UomGroup.id == group_id, UomGroup.is_deleted.is_(False)
            )
        )
        if row is None:
            raise ResourceNotFoundError("UOM group not found.")
        if self._session.scalar(
            select(UomGroupUnit.id)
            .where(
                UomGroupUnit.uom_group_id == group_id,
                UomGroupUnit.is_deleted.is_(False),
            )
            .limit(1)
        ):
            raise ValidationError("This group still holds units and cannot be deleted.")
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.deleted_by = actor_id
        row.updated_by = actor_id
        self._session.commit()

    def list_packaging_types(self) -> list[PackagingType]:
        """Return the packaging types by name."""
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
        """Add a packaging type."""
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
        """Change a packaging type."""
        row = self._session.scalar(
            select(PackagingType).where(
                PackagingType.id == packaging_type_id,
                PackagingType.is_deleted.is_(False),
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
        """Soft delete a packaging type no level uses."""
        row = self._session.scalar(
            select(PackagingType).where(
                PackagingType.id == packaging_type_id,
                PackagingType.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Packaging type not found.")
        if self._session.scalar(
            select(ProductPackagingLevel.id)
            .where(
                ProductPackagingLevel.packaging_type_id == packaging_type_id,
                ProductPackagingLevel.is_deleted.is_(False),
            )
            .limit(1)
        ):
            raise ValidationError(
                "This packaging type is used by a packaging level and cannot be "
                "deleted."
            )
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
        """Return a page of this firm's conversion rules."""
        statement = select(ConversionRule).where(
            ConversionRule.firm_id == firm_scope,
            ConversionRule.is_deleted.is_(False),
        )
        count = (
            select(func.count())
            .select_from(ConversionRule)
            .where(
                ConversionRule.firm_id == firm_scope,
                ConversionRule.is_deleted.is_(False),
            )
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
                or_(
                    ConversionRule.effective_to.is_(None),
                    ConversionRule.effective_to >= on,
                ),
            )
            statement = statement.where(active_on)
            count = count.where(active_on)
        rows = list(
            self._session.scalars(
                statement.order_by(
                    ConversionRule.product_id.asc(),
                    ConversionRule.from_uom_id.asc(),
                    ConversionRule.version_number.desc(),
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        return rows, int(self._session.scalar(count) or 0)

    def create_conversion_rule(
        self, data: ConversionRuleCreate, *, firm_scope: UUID, actor_id: UUID
    ) -> ConversionRule:
        """Publish a conversion rule version for one unit pair."""
        row = ConversionRule(
            firm_id=firm_scope,
            business_profile_id=data.business_profile_id,
            product_id=data.product_id,
            from_uom_id=data.from_uom_id,
            to_uom_id=data.to_uom_id,
            conversion_factor=data.conversion_factor,
            rounding_mode=self._rounding_mode(data.rounding_mode),
            precision_scale=data.precision_scale,
            effective_from=data.effective_from,
            effective_to=data.effective_to,
            version_number=data.version,
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
        """Change a conversion rule this firm owns."""
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
        if "rounding_mode" in payload and payload["rounding_mode"] is not None:
            payload["rounding_mode"] = self._rounding_mode(payload["rounding_mode"])
        # The request field is still called version; the column behind it is
        # version_number, because version is the concurrency counter and writing
        # to it here would corrupt the check that protects this very update.
        if "version" in payload:
            payload["version_number"] = payload.pop("version")
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
        """Retire a conversion rule and record the audit entry."""
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
            before_data={"status": row.status, "version": row.version_number},
        )
        self._session.commit()

    def convert_quantity(
        self, request: ConversionRequest, *, firm_scope: UUID
    ) -> ConversionResponse:
        """Convert a quantity with the rule in force on the given date."""
        # utc_now(), not date.today(): the server's local date can already be
        # tomorrow, which selects a rule that is not yet effective.
        on_date = request.conversion_date or utc_now().date()
        rule = self._resolve_conversion_rule(
            firm_scope=firm_scope,
            product_id=request.product_id,
            from_uom_id=request.from_uom_id,
            to_uom_id=request.to_uom_id,
            on_date=on_date,
        )
        precision = Decimal("1").scaleb(-int(rule.precision_scale))
        converted = (request.quantity * rule.conversion_factor).quantize(
            precision, rounding=ROUNDING_MODES.get(rule.rounding_mode, ROUND_HALF_UP)
        )
        return ConversionResponse(
            quantity=request.quantity,
            converted_quantity=converted,
            from_uom_id=request.from_uom_id,
            to_uom_id=request.to_uom_id,
            conversion_factor=rule.conversion_factor,
            version=rule.version_number,
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
        audit_firm_id: UUID | None = None,
    ) -> BusinessProfileUomDefault:
        """Store default unit behaviour for one firm, or for a whole profile.

        ``firm_scope`` is the row's owner, not merely a filter: a firm id
        writes that firm's override, and None writes the profile-wide row every
        firm on the profile inherits. The caller decides which, because the two
        differ in blast radius -- the profile-wide row reaches every firm on
        the profile and the router demands platform authority for it.

        Args:
            firm_scope: The firm whose override to write, or None for the
                profile-wide default.
            profile_id: The business profile these units belong to.
            data: The units and quantity flags to store.
            actor_id: The acting user.
            audit_firm_id: The firm the audit entry belongs to. A profile-wide
                write has no owning firm, so the trail would otherwise lose the
                store it happened in.

        """
        row = self._session.scalar(
            select(BusinessProfileUomDefault).where(
                BusinessProfileUomDefault.firm_id == firm_scope,
                BusinessProfileUomDefault.business_profile_id == profile_id,
                BusinessProfileUomDefault.is_deleted.is_(False),
            )
        )
        created = row is None
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
        record_audit(
            self._session,
            action=(
                "uom.profile_default.created"
                if created
                else "uom.profile_default.updated"
            ),
            entity_type="business_profile_uom_default",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=audit_firm_id if firm_scope is None else firm_scope,
        )
        self._session.commit()
        return row

    def get_profile_default(
        self, *, firm_scope: UUID | None, profile_id: UUID
    ) -> BusinessProfileUomDefault | None:
        """Return a business profile's default unit behaviour.

        ``firm_id`` is nullable so one row can serve every firm on a profile
        while a firm may override it: NULL is the profile-wide default, a set
        value is that firm's own. Only the override half was implemented, so
        this filtered on the caller's firm and never matched the seeded rows --
        every industry default shipped invisible, and ``GET
        /uom-framework/profiles/{id}/defaults`` answered ``null`` for a profile
        whose row was sitting in the same store.

        The firm's own row wins; the profile-wide row is the fallback. The rank
        is explicit rather than an ``ORDER BY firm_id``: PostgreSQL sorts NULLs
        first in DESC and SQLite last, which is how a firm-wide UOM conversion
        rule once outranked a product's own factor in production while the unit
        suite saw the right answer.
        """
        return self._session.scalar(
            select(BusinessProfileUomDefault)
            .where(
                BusinessProfileUomDefault.business_profile_id == profile_id,
                BusinessProfileUomDefault.is_deleted.is_(False),
                or_(
                    BusinessProfileUomDefault.firm_id == firm_scope,
                    BusinessProfileUomDefault.firm_id.is_(None),
                ),
            )
            .order_by(
                case(
                    (BusinessProfileUomDefault.firm_id.is_(None), 1),
                    else_=0,
                )
            )
            .limit(1)
        )

    def resolve_firm_profile_default(
        self, *, firm_scope: UUID | None
    ) -> BusinessProfileUomDefault | None:
        """Return the default units the calling firm's own profile carries.

        A firm cannot look this up for itself through
        ``/profiles/{id}/defaults``: it would need its own profile id, and
        every route that reveals one is platform-admin only. So a client had no
        way to reach the defaults meant for it.

        The profile is resolved through ``app.business.gating`` rather than
        queried here, so the units a firm is offered come from the same
        assignment its feature gates use.
        """
        profile_id = resolve_profile_id(self._session, firm_scope)
        if profile_id is None:
            return None
        return self.get_profile_default(firm_scope=firm_scope, profile_id=profile_id)

    def list_packaging_levels(
        self, *, firm_scope: UUID, product_id: UUID
    ) -> list[ProductPackagingLevel]:
        """Return a product's packaging hierarchy in display order."""
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
        """Add a level to a product's packaging hierarchy."""
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
        """Change a packaging level."""
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
        """Soft delete a packaging level."""
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

    def list_industry_templates(
        self, *, include_inactive: bool = False
    ) -> list[IndustryTemplate]:
        """Return the industry UOM templates."""
        statement = select(IndustryTemplate).where(
            IndustryTemplate.is_deleted.is_(False)
        )
        if not include_inactive:
            statement = statement.where(IndustryTemplate.status == "ACTIVE")
        return list(
            self._session.scalars(
                statement.order_by(
                    IndustryTemplate.industry_type.asc(), IndustryTemplate.code.asc()
                )
            ).all()
        )

    def create_industry_template(
        self, data: IndustryTemplateCreate, *, actor_id: UUID
    ) -> IndustryTemplate:
        """Add an industry UOM template."""
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
        """Change an industry UOM template."""
        row = self._session.scalar(
            select(IndustryTemplate).where(
                IndustryTemplate.id == template_id,
                IndustryTemplate.is_deleted.is_(False),
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
        self._flush_or_conflict(
            "Industry template update conflicts with existing data."
        )
        self._session.commit()
        return row

    def delete_industry_template(self, template_id: UUID, *, actor_id: UUID) -> None:
        """Soft delete an industry UOM template."""
        row = self._session.scalar(
            select(IndustryTemplate).where(
                IndustryTemplate.id == template_id,
                IndustryTemplate.is_deleted.is_(False),
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
            select(ConversionRule).where(
                ConversionRule.firm_id == firm_scope,
                ConversionRule.is_deleted.is_(False),
                ConversionRule.status == "ACTIVE",
                ConversionRule.from_uom_id == from_uom_id,
                ConversionRule.to_uom_id == to_uom_id,
                ConversionRule.effective_from <= on_date,
                or_(
                    ConversionRule.effective_to.is_(None),
                    ConversionRule.effective_to >= on_date,
                ),
                or_(
                    ConversionRule.product_id == product_id,
                    ConversionRule.product_id.is_(None),
                ),
            )
            # Specificity is expressed explicitly. Ordering by product_id DESC
            # relied on where the backend sorts NULLs: PostgreSQL puts them
            # first, so the firm-wide fallback beat the product's own rule and
            # every quantity for that product converted with the wrong factor.
            # SQLite sorts them last, which is why no unit test could see it.
            .order_by(
                case((ConversionRule.product_id.is_(None), 1), else_=0).asc(),
                ConversionRule.version_number.desc(),
            )
        ).first()
        if exact is None:
            raise ValidationError(
                "No active conversion rule is configured for this UOM pair."
            )
        return exact

    def _flush_or_conflict(self, message: str) -> None:
        try:
            self._session.flush()
        except IntegrityError as error:
            self._session.rollback()
            raise ConflictError(message) from error
