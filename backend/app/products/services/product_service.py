"""Transactional service for profile-driven product master operations."""

# ruff: noqa: D102, D107

import csv
import io
from collections.abc import Callable, Iterable
from decimal import Decimal, InvalidOperation
from functools import partial
from io import BytesIO
from typing import Any, cast
from uuid import UUID

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import String, case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.sql import Select
from sqlalchemy.sql.elements import ColumnElement

from app.business.gating import (
    assert_feature_fields,
    resolve_capabilities,
    resolve_profile,
)
from app.business.models import (
    AttributeDefinition,
    AttributeEntityType,
    BusinessProfile,
)
from app.business.services import AttributeInput, AttributeService
from app.common.audit.services import record_audit, record_change, row_state
from app.common.firm_metadata import FirmMetadataReader
from app.common.master_codes import assert_codes_free
from app.common.open_documents import (
    describe_documents,
    describe_stock,
    find_open_documents,
    find_stock_holdings,
)
from app.core.concurrency import assert_version
from app.core.exceptions import (
    ApplicationError,
    AuthorizationError,
    ConflictError,
    ResourceNotFoundError,
    ValidationError,
)
from app.core.utils.dates import utc_now
from app.products.models import (
    Product,
    ProductAttributeValue,
    ProductCategory,
    ProductMedia,
)
from app.products.schemas import (
    ProductAttributeInput,
    ProductAttributeResponse,
    ProductCategoryCreate,
    ProductCategoryFilter,
    ProductCategoryUpdate,
    ProductCreate,
    ProductListFilters,
    ProductMediaInput,
    ProductMetadataResponse,
    ProductSummary,
    ProductTaxProfileOption,
    ProductUpdate,
)
from app.products.schemas.product import ProductCategoryResponse
from app.tax.models import TaxProfile
from app.uom.models import Uom

#: The product fields that are somebody's separate duty, by the code that owns
#: them, with what each is called in a refusal. A price decides what the firm
#: earns and a tax group what it charges and remits, so each has had a code of
#: its own since the seed was written -- and until D-MST-10 no route read
#: either: both rode on ``PRODUCT_UPDATE``.
PRODUCT_DUTY_FIELDS: dict[str, dict[str, str]] = {
    "PRODUCT_PRICING_MANAGE": {
        "purchase_price": "purchase price",
        "selling_price": "selling price",
        "mrp": "MRP",
    },
    "PRODUCT_TAX_MANAGE": {"tax_profile_group_code": "tax group"},
}
#: The custom fields are the third duty, over a collection rather than a
#: column, so it is judged by ``_assert_attribute_duty_held`` instead.
ATTRIBUTE_DUTY = "PRODUCT_ATTRIBUTE_MANAGE"
#: Every product duty a router projects from the principal.
PRODUCT_DUTIES: frozenset[str] = frozenset(PRODUCT_DUTY_FIELDS) | {ATTRIBUTE_DUTY}

#: The fields that say how a product's stock is counted and traced, and what
#: each is called in a refusal. Changing one under stock is refused (D-MST-7).
_STOCK_SHAPE_FIELDS = {
    "base_uom_id": "base unit",
    "inventory_uom_id": "inventory unit",
    "track_batch": "batch tracking",
    "track_serial": "serial tracking",
    "require_batch_on_issue": "batch-on-issue rule",
    "require_serial_on_issue": "serial-on-issue rule",
}


class ProductService:
    """Coordinate dynamic product validation, persistence, and retrieval."""

    def __init__(
        self, session: Session, *, withheld_duties: frozenset[str] = frozenset()
    ) -> None:
        """Bind the service to one request.

        ``withheld_duties`` names the codes of ``PRODUCT_DUTY_FIELDS`` the
        caller does **not** hold. It is empty for a trusted caller -- a seeder,
        a test, another service -- and the router fills it from the principal.
        """
        self._session = session
        self._withheld_duties = withheld_duties

    def list_products(
        self,
        *,
        firm_scope: UUID,
        filters: ProductListFilters,
        page: int,
        page_size: int,
        search: str | None,
        sort_by: str,
        descending: bool,
    ) -> tuple[list[Product], int]:
        columns = {
            "code": Product.code,
            "name": Product.name,
            "status": Product.status,
            "selling_price": Product.selling_price,
            "created_at": Product.created_at,
        }
        statement = (
            select(Product)
            .where(Product.firm_id == firm_scope)
            .options(selectinload(Product.media))
        )
        count = (
            select(func.count())
            .select_from(Product)
            .where(Product.firm_id == firm_scope)
        )
        statement, count = self._apply_filters(statement, count, filters=filters)
        # The search runs in the database, and so does the page (D-MST-11).
        # This loaded every product of the firm, matched in Python and sliced
        # the list, so a page of twenty cost the whole catalogue.
        matches: list[ColumnElement[bool]] = []
        if search and search.strip():
            needle = f"%{search.strip().lower()}%"
            matches.append(
                or_(
                    *(
                        func.lower(column).like(needle)
                        for column in (
                            Product.code,
                            Product.barcode,
                            Product.qr_code,
                            Product.name,
                            Product.short_name,
                            Product.brand,
                            Product.hsn_sac,
                        )
                    )
                )
            )
        if filters.attribute_query and filters.attribute_query.strip():
            matches.append(
                Product.id.in_(
                    self._attribute_match_select(
                        firm_scope, filters.attribute_query.strip().lower()
                    )
                )
            )
        if matches:
            statement = statement.where(or_(*matches))
            count = count.where(or_(*matches))
        ordering = columns[sort_by].desc() if descending else columns[sort_by].asc()
        rows = list(
            self._session.scalars(
                # The id breaks ties, so a page boundary is stable.
                statement.order_by(ordering, Product.id.asc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        return rows, int(self._session.scalar(count) or 0)

    def summary(
        self, *, firm_scope: UUID, filters: ProductListFilters
    ) -> ProductSummary:
        base = select(Product).where(Product.firm_id == firm_scope)
        base, _ = self._apply_filters(base, base, filters=filters)
        subquery = base.subquery()
        total, active, inactive, draft, archived, deleted = self._session.execute(
            select(
                func.count(subquery.c.id),
                func.sum(case((subquery.c.status == "ACTIVE", 1), else_=0)),
                func.sum(case((subquery.c.status == "INACTIVE", 1), else_=0)),
                func.sum(case((subquery.c.status == "DRAFT", 1), else_=0)),
                func.sum(case((subquery.c.status == "ARCHIVED", 1), else_=0)),
                func.sum(case((subquery.c.is_deleted.is_(True), 1), else_=0)),
            )
        ).one()
        return ProductSummary(
            total=int(total or 0),
            active=int(active or 0),
            inactive=int(inactive or 0),
            draft=int(draft or 0),
            archived=int(archived or 0),
            deleted=int(deleted or 0),
        )

    def create_product(
        self, data: ProductCreate, *, firm_id: UUID, actor_id: UUID
    ) -> Product:
        product = self.stage_product(data, firm_id=firm_id, actor_id=actor_id)
        self._commit()
        self._session.refresh(product)
        return product

    def stage_product(
        self, data: ProductCreate, *, firm_id: UUID, actor_id: UUID
    ) -> Product:
        """Build, flush and audit one product without committing it.

        Split out so the import can stage a whole file and commit once. Nothing
        here is durable until the caller commits.
        """
        # The form and all three import formats end here, so one check covers
        # every way a product is created (D-MST-10).
        self._assert_duties_held(None, self._product_values(data), code=data.code)
        self._assert_attribute_duty_held(None, data.attributes, code=data.code)
        self._assert_unique_code(firm_id, data.code)
        self._assert_unique_barcode(firm_id, data.barcode)
        category = self._validate_category_reference(firm_id, data.category_id)
        self._validate_sub_category_reference(
            firm_id=firm_id,
            category_id=data.category_id,
            sub_category_id=data.sub_category_id,
        )
        self._validate_tax_profile_group_code(firm_id, data.tax_profile_group_code)
        self._validate_uom_references(data)
        self._validate_feature_gated_fields(data, firm_id)
        product = Product(
            **self._product_values(data),
            firm_id=firm_id,
            created_by=actor_id,
            updated_by=actor_id,
        )
        product.media = [
            self._build_media(firm_id, item, actor_id) for item in data.media
        ]
        self._session.add(product)
        self._session.flush()
        self._store_attributes(
            product, data.attributes, category=category, actor_id=actor_id
        )
        record_audit(
            self._session,
            action="product.created",
            entity_type="product",
            entity_id=product.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={"code": product.code},
        )
        return product

    def get_product(
        self,
        product_id: UUID,
        *,
        firm_scope: UUID,
        include_deleted: bool = False,
    ) -> Product:
        statement = (
            select(Product)
            .where(Product.id == product_id, Product.firm_id == firm_scope)
            .options(selectinload(Product.media))
        )
        if not include_deleted:
            statement = statement.where(Product.is_deleted.is_(False))
        row = self._session.scalar(statement)
        if row is None:
            raise ResourceNotFoundError("Product not found.")
        return row

    def update_product(
        self,
        product_id: UUID,
        data: ProductUpdate,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        may_write_cost_price: bool = True,
    ) -> Product:
        """Apply the fields the caller sent, and only those (D-MST-5).

        The update dumped its whole write model, so a ``PUT`` naming a code, a
        name and a type wrote every other field back at its schema default --
        no category, no tax group, no units, no price -- and replaced the
        custom fields and the images with nothing. Absent now means leave
        alone; an explicit ``null`` still clears, which is what keeps a
        complete client able to empty a field. ``attributes`` and ``media``
        are replaced only when the caller sent them: omitted leaves them, an
        empty list clears them.

        ``may_write_cost_price`` says the caller can *see* the cost price. One
        who cannot is served ``purchase_price: null`` and a form sends that
        null straight back, so their save leaves the stored cost alone.
        """
        product = self.get_product(
            product_id, firm_scope=firm_scope, include_deleted=True
        )
        values = self._product_values(data, partial=True)
        if not may_write_cost_price:
            values.pop("purchase_price", None)
        self._assert_unique_code(firm_scope, data.code, current_id=product.id)
        if "barcode" in values:
            self._assert_unique_barcode(firm_scope, data.barcode, current_id=product.id)
        # Read with the row as the fallback: a category the caller did not
        # mention is still the category the custom-field rules are judged by.
        category_id = self._as_uuid(values.get("category_id", product.category_id))
        sub_category_id = self._as_uuid(
            values.get("sub_category_id", product.sub_category_id)
        )
        self._assert_duties_held(product, values, code=data.code)
        if "attributes" in data.model_fields_set:
            self._assert_attribute_duty_held(product, data.attributes, code=data.code)
        if "category_id" in values:
            category = self._validate_category_reference(firm_scope, category_id)
        else:
            category = self._stored_category(firm_scope, category_id)
        if "category_id" in values or "sub_category_id" in values:
            self._validate_sub_category_reference(
                firm_id=firm_scope,
                category_id=category_id,
                sub_category_id=sub_category_id,
            )
        if "tax_profile_group_code" in values:
            self._validate_tax_profile_group_code(
                firm_scope, data.tax_profile_group_code
            )
        self._validate_uom_references(data)
        self._validate_feature_gated_fields(data, firm_scope)
        self._assert_stock_shape_unchanged(product, self._product_values(data))
        self._assert_price_within_mrp(product, values)
        before: dict[str, object] = {
            "code": product.code,
            "category_id": str(product.category_id),
        }
        for field, value in values.items():
            setattr(product, field, value)
        product.updated_by = actor_id
        if "attributes" in data.model_fields_set:
            self._store_attributes(
                product, data.attributes, category=category, actor_id=actor_id
            )
        if "media" in data.model_fields_set:
            self._reconcile_media(product, data.media, actor_id)
        record_audit(
            self._session,
            action="product.updated",
            entity_type="product",
            entity_id=product.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data=before,
            after_data={"code": product.code, "status": product.status},
        )
        self._commit()
        self._session.refresh(product)
        return product

    def delete_product(
        self, product_id: UUID, *, firm_scope: UUID, actor_id: UUID
    ) -> None:
        product = self.get_product(product_id, firm_scope=firm_scope)
        self._assert_product_removable(product)
        product.is_deleted = True
        product.deleted_at = utc_now()
        product.deleted_by = actor_id
        product.updated_by = actor_id
        record_audit(
            self._session,
            action="product.deleted",
            entity_type="product",
            entity_id=product.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data={"code": product.code},
        )
        self._commit()

    def restore_product(
        self, product_id: UUID, *, firm_scope: UUID, actor_id: UUID
    ) -> Product:
        product = self.get_product(
            product_id, firm_scope=firm_scope, include_deleted=True
        )
        if not product.is_deleted:
            return product
        self._assert_restorable(product)
        product.is_deleted = False
        product.deleted_at = None
        product.deleted_by = None
        product.updated_by = actor_id
        record_audit(
            self._session,
            action="product.restored",
            entity_type="product",
            entity_id=product.id,
            actor_id=actor_id,
            firm_id=firm_scope,
        )
        self._commit()
        return product

    def duplicate_product(
        self, product_id: UUID, *, firm_scope: UUID, actor_id: UUID
    ) -> Product:
        source = self.get_product(product_id, firm_scope=firm_scope)
        duplicated = ProductCreate.model_validate(
            {
                **self._product_values_from_model(source),
                "code": self._next_duplicate_code(firm_scope, source.code),
                "attributes": self._attribute_inputs_for(source),
                "media": [
                    self._media_input_from_model(media)
                    for media in source.media
                    if not media.is_deleted
                ],
            }
        )
        product = self.create_product(duplicated, firm_id=firm_scope, actor_id=actor_id)
        record_audit(
            self._session,
            action="product.duplicated",
            entity_type="product",
            entity_id=product.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data={"source_product_id": str(source.id)},
        )
        self._commit()
        return product

    def bulk_delete(
        self, ids: Iterable[UUID], *, firm_scope: UUID, actor_id: UUID
    ) -> int:
        # Every row is judged before any is touched, so a batch whose fifth
        # product still holds stock deletes none of them (D-MST-1).
        products = [
            self.get_product(product_id, firm_scope=firm_scope) for product_id in ids
        ]
        for product in products:
            self._assert_product_removable(product)
        count = 0
        for product in products:
            if product.is_deleted:
                continue
            product.is_deleted = True
            product.deleted_at = utc_now()
            product.deleted_by = actor_id
            product.updated_by = actor_id
            self._audit_bulk(product, action="product.deleted", actor_id=actor_id)
            count += 1
        if count > 0:
            self._commit()
        return count

    def bulk_restore(
        self, ids: Iterable[UUID], *, firm_scope: UUID, actor_id: UUID
    ) -> int:
        count = 0
        for product_id in ids:
            product = self.get_product(
                product_id, firm_scope=firm_scope, include_deleted=True
            )
            if not product.is_deleted:
                continue
            self._assert_restorable(product)
            product.is_deleted = False
            product.deleted_at = None
            product.deleted_by = None
            product.updated_by = actor_id
            self._audit_bulk(product, action="product.restored", actor_id=actor_id)
            count += 1
        if count > 0:
            self._commit()
        return count

    def _assert_stock_shape_unchanged(
        self, product: Product, values: dict[str, object]
    ) -> None:
        """Refuse to change how stock is counted or traced while stock exists.

        ``inventories.current_quantity`` is held in the product's base unit,
        so moving the unit from PIECE to BOX re-reads 50 pieces as 50 boxes
        without a single movement; and switching serial or batch tracking on
        over stock received without serials or batches leaves quantity the
        picker then refuses to dispatch (D-MST-7). The rule every stock
        package keeps: the unit and the tracking mode are settled before the
        first receipt, and changed only once the product is back at nothing --
        no quantity anywhere, no reservation, no document still to ship,
        receive or bill it.

        ``values`` is what the update is about to write, so only a field that
        is present **and different** is a change: a form resending what is
        stored saves as before. Naming a unit for a product that had none is
        not a change of unit -- nothing is re-read -- and is how a product
        created without one is repaired, so it is let through.
        """
        changing = [
            label
            for field, label in _STOCK_SHAPE_FIELDS.items()
            if field in values
            and values[field] != getattr(product, field)
            and not (field.endswith("_uom_id") and getattr(product, field) is None)
        ]
        if not changing:
            return
        reasons: list[str] = []
        holdings = find_stock_holdings(
            self._session, product.firm_id, product_id=product.id
        )
        if holdings:
            reasons.append(f"holds {describe_stock(holdings)}")
        documents = find_open_documents(
            self._session, product.firm_id, product_id=product.id
        )
        if documents:
            reasons.append(f"is on {describe_documents(documents)}")
        if reasons:
            raise ValidationError(
                f"{product.code}: the {', '.join(changing)} cannot be changed "
                f"while it {' and '.join(reasons)}. Move or write off the "
                "stock and finish, cancel or close what is open first."
            )

    def _assert_product_removable(self, product: Product) -> None:
        """Refuse to delete a product that still holds stock or is in flight.

        Deleting one hid it and nothing else (D-MST-1): the stock rows and the
        valuation stayed on the books, the stock summary filters deleted
        products out, and every movement of one is refused -- "Product does
        not belong to the active firm." -- so the quantity could be neither
        seen nor written off until somebody restored the product. The rule
        every stock package keeps: a product with quantity on hand, a
        reservation, or a document still to be shipped, received or billed is
        retired by setting it inactive, not by deleting it.
        """
        reasons: list[str] = []
        holdings = find_stock_holdings(
            self._session, product.firm_id, product_id=product.id
        )
        if holdings:
            reasons.append(f"holds {describe_stock(holdings)}")
        documents = find_open_documents(
            self._session, product.firm_id, product_id=product.id
        )
        if documents:
            reasons.append(f"is on {describe_documents(documents)}")
        if reasons:
            raise ValidationError(
                f"{product.code} cannot be deleted: it {' and '.join(reasons)}. "
                "Move or write off the stock and finish, cancel or close what "
                "is open first, or set the product inactive to stop trading it."
            )

    def _assert_duties_held(
        self, product: Product | None, values: dict[str, object], *, code: str
    ) -> None:
        """Refuse a write to a field whose duty the caller does not hold.

        ``values`` is what is about to be written. On an update a field counts
        only when it is present **and different** from the row, so a form
        resending the stored price saves as before; on a create (``product``
        is None) it counts when it carries a value at all. The form and all
        three import formats end in ``create_product``, so one check covers
        them. A duplicate copies what is already stored rather than deciding
        a price, and its route withholds nothing.
        """
        for duty in sorted(self._withheld_duties):
            for field, label in PRODUCT_DUTY_FIELDS.get(duty, {}).items():
                if field not in values:
                    continue
                stored = None if product is None else getattr(product, field)
                if values[field] == stored:
                    continue
                raise AuthorizationError(
                    f"{code}: setting a product's {label} needs the "
                    f"{duty.replace('_', ' ').lower()} permission ({duty})."
                )

    def _assert_attribute_duty_held(
        self,
        product: Product | None,
        attributes: list[ProductAttributeInput],
        *,
        code: str,
    ) -> None:
        """Refuse a change to the custom fields without ``PRODUCT_ATTRIBUTE_MANAGE``.

        The custom fields are the third duty the seed split off ``PRODUCT_UPDATE``
        and no route read (D-MST-10). On a create any value at all counts; on an
        update only a set that differs from what is stored, so a form resending
        the values it was served saves as before. Numbers compare as decimals,
        because a stored ``10.00`` and a resent ``10`` are the same value.
        """
        if ATTRIBUTE_DUTY not in self._withheld_duties:
            return
        sent = {
            self._attribute_key(item.attribute_definition_id, item.value)
            for item in attributes
        }
        stored: set[tuple[str, str]] = set()
        if product is not None:
            stored = {
                self._attribute_key(
                    cast(UUID, item["attribute_definition_id"]), item["value"]
                )
                for item in self._attribute_inputs_for(product)
            }
        if sent != stored:
            raise AuthorizationError(
                f"{code}: setting a product's custom fields needs the manage "
                f"product attributes permission ({ATTRIBUTE_DUTY})."
            )

    @staticmethod
    def _attribute_key(definition_id: UUID, value: object) -> tuple[str, str]:
        """Normalise one attribute value so a resend compares equal to the row."""
        if isinstance(value, bool):
            return (str(definition_id), str(value))
        if isinstance(value, int | float | Decimal):
            return (str(definition_id), str(Decimal(str(value)).normalize()))
        return (str(definition_id), str(value))

    def _audit_bulk(self, product: Product, *, action: str, actor_id: UUID) -> None:
        """Record a bulk mutation the way the single-row endpoint records it.

        The bulk delete and restore endpoints wrote nothing, so removing a
        hundred products from the toolbar left no trace while removing one from
        the row menu was recorded.
        """
        record_audit(
            self._session,
            action=action,
            entity_type="product",
            entity_id=product.id,
            actor_id=actor_id,
            firm_id=product.firm_id,
            before_data={"code": product.code},
            after_data={"is_deleted": product.is_deleted},
        )

    def metadata(
        self, *, firm_scope: UUID, category_id: UUID | None = None
    ) -> ProductMetadataResponse:
        capabilities = resolve_capabilities(self._session, firm_scope)
        profile = self._resolved_profile(firm_scope)
        feature_codes = capabilities.features
        categories = self._session.scalars(
            select(ProductCategory)
            .where(
                ProductCategory.firm_id == firm_scope,
                ProductCategory.is_deleted.is_(False),
                ProductCategory.is_active.is_(True),
            )
            .order_by(ProductCategory.path.asc())
        ).all()
        required_ids, optional_ids = self._category_attribute_ids(
            firm_scope, category_id
        )
        return ProductMetadataResponse(
            profile_code=profile.code,
            features=[
                {"code": code, "enabled": True} for code in sorted(feature_codes)
            ],
            categories=[
                ProductCategoryResponse.model_validate(item) for item in categories
            ],
            tax_profiles=[
                ProductTaxProfileOption(
                    id=item.id,
                    code=item.code,
                    group_code=item.group_code,
                    label=item.label,
                    tax_system_id=item.tax_system_id,
                )
                for item in self._session.scalars(
                    select(TaxProfile)
                    .where(
                        TaxProfile.firm_id == firm_scope,
                        TaxProfile.is_deleted.is_(False),
                        TaxProfile.status == "ACTIVE",
                    )
                    .order_by(TaxProfile.display_order.asc(), TaxProfile.code.asc())
                ).all()
            ],
            required_attribute_definition_ids=required_ids,
            optional_attribute_definition_ids=optional_ids,
        )

    def create_category(
        self, data: ProductCategoryCreate, *, firm_id: UUID, actor_id: UUID
    ) -> ProductCategory:
        parent = self._validate_category_reference(firm_id, data.parent_id)
        self._assert_category_free(
            firm_id, code=data.code, name=data.name, parent_id=data.parent_id
        )
        level = 0 if parent is None else parent.level + 1
        path = data.code if parent is None else f"{parent.path}/{data.code}"
        row = ProductCategory(
            firm_id=firm_id,
            code=data.code,
            name=data.name,
            parent_id=data.parent_id,
            level=level,
            path=path,
            is_active=data.is_active,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._session.flush()
        # A category's create and edit left no trail (D-MST-11).
        record_change(
            self._session,
            action="product.category.created",
            entity_type="product_category",
            row=row,
            actor_id=actor_id,
            firm_id=firm_id,
        )
        self._commit()
        return row

    def list_categories(
        self, *, firm_scope: UUID, filters: ProductCategoryFilter
    ) -> list[ProductCategory]:
        statement = select(ProductCategory).where(
            ProductCategory.firm_id == firm_scope,
            ProductCategory.is_deleted.is_(False),
        )
        if filters.parent_id is not None:
            statement = statement.where(ProductCategory.parent_id == filters.parent_id)
        if not filters.include_inactive:
            statement = statement.where(ProductCategory.is_active.is_(True))
        return list(
            self._session.scalars(statement.order_by(ProductCategory.path.asc())).all()
        )

    def get_category(self, category_id: UUID, *, firm_scope: UUID) -> ProductCategory:
        row = self._validate_category_reference(firm_scope, category_id)
        if row is None:
            raise ResourceNotFoundError("Product category not found.")
        return row

    def update_category(
        self,
        category_id: UUID,
        data: ProductCategoryUpdate,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        expected_version: int | None = None,
    ) -> ProductCategory:
        """Edit a category, moving its whole subtree with it (D-MST-11).

        A category could be put under its own child -- a loop no tree can draw
        -- and a move or a new code rewrote this row's path and left every
        descendant's pointing at where it used to be.
        """
        row = self.get_category(category_id, firm_scope=firm_scope)
        assert_version(row.version, expected_version)
        parent = self._validate_category_reference(firm_scope, data.parent_id)
        if parent is not None and (
            parent.id == row.id or self._is_descendant(parent, of=row)
        ):
            what = (
                "the category itself"
                if parent.id == row.id
                else "one of its own sub-categories"
            )
            raise ValidationError(
                f"{row.code} cannot be placed under {parent.code}: it is {what}."
            )
        self._assert_category_free(
            firm_scope,
            code=data.code,
            name=data.name,
            parent_id=data.parent_id,
            excluding_id=row.id,
        )
        before = row_state(row)
        old_path = row.path
        row.code = data.code
        row.name = data.name
        row.parent_id = data.parent_id
        row.level = 0 if parent is None else parent.level + 1
        row.path = data.code if parent is None else f"{parent.path}/{data.code}"
        row.is_active = data.is_active
        row.updated_by = actor_id
        if row.path != old_path:
            self._repath_category_descendants(row)
        record_change(
            self._session,
            action="product.category.updated",
            entity_type="product_category",
            row=row,
            actor_id=actor_id,
            before=before,
            firm_id=firm_scope,
        )
        self._commit()
        return row

    def _category_descendants(self, row: ProductCategory) -> list[ProductCategory]:
        """Return every live category below ``row``, walked by parent id.

        Walked rather than matched on the path, because a path is exactly what
        an older move left stale.
        """
        found: list[ProductCategory] = []
        frontier = [row.id]
        while frontier:
            children = list(
                self._session.scalars(
                    select(ProductCategory).where(
                        ProductCategory.firm_id == row.firm_id,
                        ProductCategory.parent_id.in_(frontier),
                        ProductCategory.is_deleted.is_(False),
                    )
                ).all()
            )
            children = [child for child in children if child not in found]
            found.extend(children)
            frontier = [child.id for child in children]
        return found

    def _is_descendant(
        self, candidate: ProductCategory, *, of: ProductCategory
    ) -> bool:
        """Return whether ``candidate`` sits somewhere below ``of``."""
        return any(item.id == candidate.id for item in self._category_descendants(of))

    def _repath_category_descendants(self, row: ProductCategory) -> None:
        """Rebuild each descendant's path and level from its new ancestor.

        Rebuilt down the parent chain rather than string-replaced, so a path
        an older move left stale is corrected too.
        """
        paths = {row.id: row.path}
        levels = {row.id: row.level}
        for child in self._category_descendants(row):
            if child.parent_id is None or child.parent_id not in paths:
                continue
            child.path = f"{paths[child.parent_id]}/{child.code}"
            child.level = levels[child.parent_id] + 1
            paths[child.id], levels[child.id] = child.path, child.level

    def _assert_category_free(
        self,
        firm_id: UUID,
        *,
        code: str,
        name: str,
        parent_id: UUID | None,
        excluding_id: UUID | None = None,
    ) -> None:
        """Refuse a code the firm, or a name the parent, already uses."""
        assert_codes_free(
            self._session,
            ProductCategory,
            scope={"firm_id": firm_id},
            values={"code": code},
            excluding_id=excluding_id,
            message="A product category with this code already exists.",
        )
        assert_codes_free(
            self._session,
            ProductCategory,
            scope={"firm_id": firm_id, "parent_id": parent_id},
            values={"name": name},
            excluding_id=excluding_id,
            message="A product category with this name already exists at this level.",
        )

    def _assert_restorable(self, product: Product) -> None:
        """Refuse a restore into a code or barcode a live product now holds."""
        assert_codes_free(
            self._session,
            Product,
            scope={"firm_id": product.firm_id},
            values={"code": product.code, "barcode": product.barcode},
            excluding_id=product.id,
            message=(
                f"{product.code} cannot be restored: a live product now holds "
                "its code or barcode."
            ),
        )

    def delete_category(
        self, category_id: UUID, *, firm_scope: UUID, actor_id: UUID
    ) -> None:
        row = self.get_category(category_id, firm_scope=firm_scope)
        # A sub-category is a category too, and a live child would be left
        # hanging from a parent no list shows (D-MST-11): this looked only at
        # `category_id`.
        has_products = self._session.scalar(
            select(Product.id).where(
                Product.firm_id == firm_scope,
                or_(
                    Product.category_id == row.id,
                    Product.sub_category_id == row.id,
                ),
                Product.is_deleted.is_(False),
            )
        )
        if has_products is not None:
            raise ValidationError("Categories used by products cannot be deleted.")
        has_children = self._session.scalar(
            select(ProductCategory.id).where(
                ProductCategory.firm_id == firm_scope,
                ProductCategory.parent_id == row.id,
                ProductCategory.is_deleted.is_(False),
            )
        )
        if has_children is not None:
            raise ValidationError(
                f"{row.code} has sub-categories. Move or delete them first."
            )
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.deleted_by = actor_id
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="product.category.deleted",
            entity_type="product_category",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data={"code": row.code, "name": row.name},
            after_data={"is_deleted": True},
        )
        self._commit()

    def export_products_csv(self, *, firm_scope: UUID, search: str | None) -> str:
        rows, _ = self.list_products(
            firm_scope=firm_scope,
            filters=ProductListFilters(include_deleted=False),
            page=1,
            page_size=5000,
            search=search,
            sort_by="code",
            descending=False,
        )
        # Written by the csv module (D-MST-11): a plain join put a name like
        # "Rice, basmati" across two columns and shifted every one after it.
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(
            ["Code", "Name", "Type", "Brand", "HSN", "SellingPrice", "Status"]
        )
        for item in rows:
            writer.writerow(
                [
                    item.code,
                    item.name,
                    item.product_type,
                    item.brand or "",
                    item.hsn_sac or "",
                    str(item.selling_price or ""),
                    item.status,
                ]
            )
        return buffer.getvalue().rstrip("\n")

    def export_products_xlsx(self, *, firm_scope: UUID, search: str | None) -> bytes:
        try:
            from openpyxl import Workbook  # type: ignore[import-untyped]
        except ImportError as error:
            raise ValidationError(
                "XLSX export dependency is unavailable. Install openpyxl."
            ) from error
        rows, _ = self.list_products(
            firm_scope=firm_scope,
            filters=ProductListFilters(include_deleted=False),
            page=1,
            page_size=5000,
            search=search,
            sort_by="code",
            descending=False,
        )
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Products"
        sheet.append(["Code", "Name", "Type", "Brand", "HSN", "SellingPrice", "Status"])
        for item in rows:
            sheet.append(
                [
                    item.code,
                    item.name,
                    item.product_type,
                    item.brand or "",
                    item.hsn_sac or "",
                    float(item.selling_price or 0),
                    item.status,
                ]
            )
        buffer = BytesIO()
        workbook.save(buffer)
        return buffer.getvalue()

    def import_products_json(
        self, records: list[ProductCreate], *, firm_scope: UUID, actor_id: UUID
    ) -> list[Product]:
        """Import a batch of products in one transaction.

        This looped over ``create_product``, which commits -- so a file whose
        second row clashed answered 409 with the first row written, and the
        corrected file was then refused as a duplicate of what the failed one
        had left behind (D-MST-9). Every row is staged, and the batch commits
        once; a row that fails rolls the whole file back and is named by its
        position, because a 409 that does not say which of 3,000 rows clashed
        is not much of an answer.
        """
        result: list[Product] = []
        try:
            for position, item in enumerate(records, start=1):
                try:
                    result.append(
                        self.stage_product(item, firm_id=firm_scope, actor_id=actor_id)
                    )
                except ApplicationError as error:
                    raise type(error)(
                        f"Row {position} ({item.code}): {error.message} "
                        "Nothing was imported.",
                        details=error.details,
                    ) from error
        except Exception:
            self._session.rollback()
            raise
        self._commit()
        for product in result:
            self._session.refresh(product)
        return result

    def import_products_csv(
        self, csv_content: str, *, firm_scope: UUID, actor_id: UUID
    ) -> list[Product]:
        reader = csv.DictReader(io.StringIO(csv_content))
        records = [
            self._import_record(number, row.get)
            for number, row in enumerate(reader, start=2)
        ]
        return self.import_products_json(
            [record for record in records if record is not None],
            firm_scope=firm_scope,
            actor_id=actor_id,
        )

    def import_products_xlsx(
        self, workbook_bytes: bytes, *, firm_scope: UUID, actor_id: UUID
    ) -> list[Product]:
        try:
            from openpyxl import load_workbook
        except ImportError as error:
            raise ValidationError(
                "XLSX import dependency is unavailable. Install openpyxl."
            ) from error
        workbook = load_workbook(filename=BytesIO(workbook_bytes), read_only=True)
        sheet = workbook.active
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            return []
        header = [str(value or "").strip() for value in rows[0]]
        index = {name: position for position, name in enumerate(header)}

        def cell(values: tuple[object, ...], name: str) -> object:
            """Read a named column, or nothing when the sheet has no such one.

            Looked up with ``index.get(name, -1)`` before, which read a missing
            column as the **last** one.
            """
            position = index.get(name)
            if position is None or position >= len(values):
                return None
            return values[position]

        records = [
            self._import_record(number, partial(cell, values))
            for number, values in enumerate(rows[1:], start=2)
        ]
        return self.import_products_json(
            [record for record in records if record is not None],
            firm_scope=firm_scope,
            actor_id=actor_id,
        )

    @staticmethod
    def _import_record(
        row_number: int, read: Callable[[str], object]
    ) -> ProductCreate | None:
        """Build one product from a spreadsheet row, or skip a row with no code.

        The two readers each spelled this out and called ``Decimal(...)`` and
        the schema bare, so a bad number or an unknown status surfaced as a
        server error naming nothing. It is refused here by row number -- the
        header is row 1, as a spreadsheet shows it.
        """

        def text(name: str) -> str:
            """Read a column as trimmed text."""
            value = read(name)
            return "" if value is None else str(value).strip()

        code = text("Code").upper()
        if not code:
            return None
        price = text("SellingPrice")
        try:
            selling_price = Decimal(price) if price else None
        except InvalidOperation as error:
            raise ValidationError(
                f"Row {row_number} ({code}): SellingPrice: '{price}' is not a "
                "number. Nothing was imported."
            ) from error
        try:
            return ProductCreate.model_validate(
                {
                    "code": code,
                    "name": text("Name"),
                    "product_type": (text("Type") or "STOCK_ITEM").upper(),
                    "brand": text("Brand") or None,
                    "hsn_sac": text("HSN").upper() or None,
                    "selling_price": selling_price,
                    "status": (text("Status") or "ACTIVE").upper(),
                }
            )
        except PydanticValidationError as error:
            first = error.errors()[0]
            column = ".".join(str(part) for part in first["loc"]) or "row"
            raise ValidationError(
                f"Row {row_number} ({code}): {column}: {first['msg']}. "
                "Nothing was imported."
            ) from error

    def _apply_filters(
        self,
        statement: Select[Any],
        count: Select[Any],
        *,
        filters: ProductListFilters,
    ) -> tuple[Select[Any], Select[Any]]:
        if not filters.include_deleted:
            statement = statement.where(Product.is_deleted.is_(False))
            count = count.where(Product.is_deleted.is_(False))
        if filters.status is not None:
            statement = statement.where(Product.status == filters.status.value)
            count = count.where(Product.status == filters.status.value)
        if filters.product_type is not None:
            statement = statement.where(
                Product.product_type == filters.product_type.value
            )
            count = count.where(Product.product_type == filters.product_type.value)
        if filters.category_id is not None:
            statement = statement.where(Product.category_id == filters.category_id)
            count = count.where(Product.category_id == filters.category_id)
        if filters.sub_category_id is not None:
            statement = statement.where(
                Product.sub_category_id == filters.sub_category_id
            )
            count = count.where(Product.sub_category_id == filters.sub_category_id)
        if filters.tax_profile_group_code is not None:
            statement = statement.where(
                Product.tax_profile_group_code == filters.tax_profile_group_code
            )
            count = count.where(
                Product.tax_profile_group_code == filters.tax_profile_group_code
            )
        if filters.brand:
            statement = statement.where(
                Product.brand.ilike(f"%{filters.brand.strip()}%")
            )
            count = count.where(Product.brand.ilike(f"%{filters.brand.strip()}%"))
        if filters.hsn_sac:
            statement = statement.where(
                Product.hsn_sac == filters.hsn_sac.strip().upper()
            )
            count = count.where(Product.hsn_sac == filters.hsn_sac.strip().upper())
        return statement, count

    def _resolved_profile(self, firm_id: UUID) -> BusinessProfile:
        """Return the profile whose attribute rules shape a product form.

        Delegated to ``resolve_profile`` so this answers exactly what
        ``resolve_capabilities`` answers two lines above it in ``metadata``:
        a private copy that filtered the assignment differently would offer a
        field the gate then refuses on save. The refusal stays here rather than
        in the resolver -- a form cannot be rendered without a profile to shape
        it, where a gate with no profile is right to enforce nothing.
        """
        profile = resolve_profile(self._session, firm_id)
        if profile is None:
            raise ValidationError("No active business profile is configured.")
        return profile

    def _category_attribute_ids(
        self, firm_id: UUID, category_id: UUID | None
    ) -> tuple[list[UUID], list[UUID]]:
        """Return the attribute fields a product form should offer.

        This asked `category_attribute_rules` and nothing else until
        2026-09-16, which was wrong in both directions and made the product
        the odd one out: customers, vendors, branches and warehouses all offer
        what **applies** (`AttributeService.definitions_for`), and the product
        offered only what a rule named.

        Three defects came out of that. A definition that simply applies -- the
        ordinary case, and the one `docs/CUSTOM_FIELDS_FRAMEWORK.md` describes
        -- was offered on no product at all. A definition marked mandatory was
        demanded by `AttributeService` on the save and shown on no form, so
        **no product could be created from the desktop** once a firm set one.
        And a rule naming a definition scoped to another profile was listed as
        required here while `mandatory_ids` correctly ignored it, so the form
        refused an empty box the server would have accepted and the server
        refused the filled one as not applicable -- a category nobody could
        save.

        The service answers both halves now: `mandatory_ids` already unions
        the definition-level flag with the rules **intersected against what
        applies**, and the rest of what applies is offered as optional. Rules
        are still read by the category's name as well as its code, because
        that tolerance predates this and a firm may have written either.
        """
        attributes = AttributeService(self._session)
        entity_type = AttributeEntityType.PRODUCT.value
        category = (
            self._session.scalar(
                select(ProductCategory).where(ProductCategory.id == category_id)
            )
            if category_id is not None
            else None
        )
        if category_id is not None and category is None:
            return [], []
        spellings: list[str | None] = (
            [category.code, category.name.upper()] if category is not None else [None]
        )
        required: set[UUID] = set()
        applicable: dict[UUID, AttributeDefinition] = {}
        for spelling in spellings:
            required |= attributes.mandatory_ids(
                entity_type, firm_id=firm_id, category_code=spelling
            )
            for definition in attributes.definitions_for(
                entity_type, firm_id=firm_id, category_code=spelling
            ):
                applicable[definition.id] = definition
        if category is None:
            # A product with no category yet is offered the fields that need
            # none. One scoped to a category it does not have is not a field
            # this product can carry.
            applicable = {
                key: row
                for key, row in applicable.items()
                if row.applicable_category is None
            }
            required &= applicable.keys()
        ordered = sorted(applicable.values(), key=lambda row: row.code)
        return (
            [row.id for row in ordered if row.id in required],
            [row.id for row in ordered if row.id not in required],
        )

    def _validate_feature_gated_fields(
        self, data: ProductCreate | ProductUpdate, firm_id: UUID
    ) -> None:
        """Check the optional product fields against the firm's profile.

        This used to resolve the firm's features through a private query that
        filtered neither ``is_active`` nor ``is_deleted``, so deactivating or
        deleting BARCODE in the catalogue left barcodes still accepted here
        while every ``require_feature`` endpoint correctly refused. One
        resolver, one answer.
        """
        for feature, fields in (
            ("BARCODE", {"barcode": data.barcode}),
            ("QR_CODE", {"qr_code": data.qr_code}),
            ("WARRANTY", {"track_warranty": data.track_warranty}),
        ):
            assert_feature_fields(
                self._session, firm_id, feature=feature, values=fields
            )

    def _attribute_inputs_for(self, product: Product) -> list[dict[str, object]]:
        """Return a product's attributes shaped for ProductCreate validation."""
        return [
            {
                "attribute_definition_id": resolved.definition.id,
                "value": resolved.value,
            }
            for resolved in AttributeService(self._session).values_for(
                ProductAttributeValue, product.id
            )
            if resolved.value is not None
        ]

    def _store_attributes(
        self,
        product: Product,
        attributes: list[ProductAttributeInput],
        *,
        category: ProductCategory | None,
        actor_id: UUID,
    ) -> None:
        """Validate and persist a product's configurable attributes."""
        AttributeService(self._session).replace_values(
            ProductAttributeValue,
            product.id,
            [
                AttributeInput(
                    attribute_definition_id=item.attribute_definition_id,
                    value=item.value,
                )
                for item in attributes
            ],
            firm_id=product.firm_id,
            actor_id=actor_id,
            category_code=category.code if category is not None else None,
        )

    def attribute_responses_for_many(
        self, products: list[Product]
    ) -> dict[UUID, list[ProductAttributeResponse]]:
        """Return a page of products' attributes in one query (D-CFG-20)."""
        grouped = AttributeService(self._session).value_rows_for_many(
            ProductAttributeValue, [row.id for row in products]
        )
        return {
            owner: [
                ProductAttributeResponse(
                    id=row.id,
                    attribute_definition_id=row.attribute_definition_id,
                    value_text=row.value_text,
                    value_number=row.value_number,
                    value_date=row.value_date,
                    value_boolean=row.value_boolean,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
                for row in rows
            ]
            for owner, rows in grouped.items()
        }

    def attribute_responses(self, product: Product) -> list[ProductAttributeResponse]:
        """Return one product's stored attributes in response shape."""
        rows = self._session.scalars(
            select(ProductAttributeValue)
            .where(
                ProductAttributeValue.product_id == product.id,
                ProductAttributeValue.is_deleted.is_(False),
            )
            .order_by(ProductAttributeValue.created_at.asc())
        ).all()
        return [
            ProductAttributeResponse(
                id=row.id,
                attribute_definition_id=row.attribute_definition_id,
                value_text=row.value_text,
                value_number=row.value_number,
                value_date=row.value_date,
                value_boolean=row.value_boolean,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]

    def _assert_unique_code(
        self, firm_id: UUID, code: str, current_id: UUID | None = None
    ) -> None:
        statement = select(Product.id).where(
            Product.firm_id == firm_id,
            Product.code == code,
            Product.is_deleted.is_(False),
        )
        if current_id is not None:
            statement = statement.where(Product.id != current_id)
        if self._session.scalar(statement) is not None:
            raise ConflictError("Product code already exists in this firm.")

    def _assert_unique_barcode(
        self, firm_id: UUID, barcode: str | None, current_id: UUID | None = None
    ) -> None:
        normalized = (barcode or "").strip()
        if not normalized:
            return
        statement = select(Product.id).where(
            Product.firm_id == firm_id,
            Product.barcode == normalized,
            Product.is_deleted.is_(False),
        )
        if current_id is not None:
            statement = statement.where(Product.id != current_id)
        if self._session.scalar(statement) is not None:
            raise ConflictError("Barcode already exists in this firm.")

    def _validate_category_reference(
        self, firm_id: UUID, category_id: UUID | None
    ) -> ProductCategory | None:
        if category_id is None:
            return None
        row = self._session.scalar(
            select(ProductCategory).where(
                ProductCategory.id == category_id,
                ProductCategory.firm_id == firm_id,
                ProductCategory.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ValidationError("Selected product category is unavailable.")
        return row

    def _validate_sub_category_reference(
        self,
        *,
        firm_id: UUID,
        category_id: UUID | None,
        sub_category_id: UUID | None,
    ) -> None:
        if sub_category_id is None:
            return
        if category_id is None:
            raise ValidationError("Category is required when sub category is selected.")
        sub_category = self._session.scalar(
            select(ProductCategory).where(
                ProductCategory.id == sub_category_id,
                ProductCategory.firm_id == firm_id,
                ProductCategory.is_deleted.is_(False),
            )
        )
        if sub_category is None:
            raise ValidationError("Selected sub category is unavailable.")
        if sub_category.parent_id != category_id:
            raise ValidationError(
                "Selected sub category does not belong to the selected category."
            )

    def _validate_tax_profile_group_code(
        self, firm_id: UUID, tax_profile_group_code: str | None
    ) -> None:
        if tax_profile_group_code is None:
            return
        row = self._session.scalar(
            select(TaxProfile.id).where(
                TaxProfile.firm_id == firm_id,
                TaxProfile.group_code == tax_profile_group_code,
                TaxProfile.is_deleted.is_(False),
                TaxProfile.status == "ACTIVE",
            )
        )
        if row is None:
            raise ValidationError(
                "No active tax profile found for the given group code."
            )

    def _validate_uom_references(self, data: ProductCreate | ProductUpdate) -> None:
        references = {
            data.base_uom_id,
            data.inventory_uom_id,
            data.purchase_uom_id,
            data.sales_uom_id,
            data.default_receiving_uom_id,
            data.default_dispatch_uom_id,
            data.minimum_sales_uom_id,
        }
        ids = {item for item in references if item is not None}
        if not ids:
            return
        available = set(
            self._session.scalars(
                select(Uom.id).where(Uom.id.in_(ids), Uom.is_deleted.is_(False))
            ).all()
        )
        missing = [item for item in ids if item not in available]
        if missing:
            raise ValidationError(
                "One or more selected UOM references are unavailable.",
                details={"unknown_uom_ids": [str(item) for item in missing]},
            )

    @staticmethod
    def _product_values(
        data: ProductCreate | ProductUpdate, *, partial: bool = False
    ) -> dict[str, object]:
        """Return the columns to write.

        ``partial`` is what an update passes: only the fields the caller sent.
        Create keeps the full dump, because there a default really is the
        value to store.
        """
        payload = data.model_dump(
            exclude={"attributes", "media"}, mode="python", exclude_unset=partial
        )
        payload["product_type"] = data.product_type.value
        if "status" in payload:
            payload["status"] = data.status.value
        return payload

    @staticmethod
    def _as_uuid(value: object) -> UUID | None:
        """Read an id out of the untyped dump."""
        return None if value is None else UUID(str(value))

    def _stored_category(
        self, firm_id: UUID, category_id: UUID | None
    ) -> ProductCategory | None:
        """Return the category a product already holds, without judging it.

        A save that does not mention the category must not be refused because
        the one on file was retired since; it is only read for its rules.
        """
        if category_id is None:
            return None
        return self._session.scalar(
            select(ProductCategory).where(
                ProductCategory.id == category_id,
                ProductCategory.firm_id == firm_id,
            )
        )

    @staticmethod
    def _assert_price_within_mrp(product: Product, values: dict[str, object]) -> None:
        """Hold the MRP rule across what was sent and what is stored.

        The schema compares the two only when both arrive in one request, so a
        partial save of either could otherwise cross the other on file.
        """
        if "mrp" not in values and "selling_price" not in values:
            return
        mrp = values.get("mrp", product.mrp)
        selling_price = values.get("selling_price", product.selling_price)
        if (
            mrp is not None
            and selling_price is not None
            and Decimal(str(mrp)) < Decimal(str(selling_price))
        ):
            raise ValidationError("MRP must be greater than or equal to selling price.")

    @staticmethod
    def _build_media(
        firm_id: UUID, data: ProductMediaInput, actor_id: UUID
    ) -> ProductMedia:
        return ProductMedia(
            firm_id=firm_id,
            media_kind=data.media_kind,
            file_name=data.file_name,
            mime_type=data.mime_type,
            storage_path=data.storage_path,
            is_primary=data.is_primary,
            file_size_bytes=data.file_size_bytes,
            created_by=actor_id,
            updated_by=actor_id,
        )

    @staticmethod
    def _attribute_match_select(firm_id: UUID, needle: str) -> Select[tuple[UUID]]:
        """Select every product in a firm whose custom fields contain the text."""
        pattern = f"%{needle}%"
        return select(ProductAttributeValue.product_id).where(
            ProductAttributeValue.firm_id == firm_id,
            ProductAttributeValue.is_deleted.is_(False),
            or_(
                func.lower(ProductAttributeValue.value_text).like(pattern),
                func.lower(func.cast(ProductAttributeValue.value_number, String)).like(
                    pattern
                ),
                func.lower(func.cast(ProductAttributeValue.value_date, String)).like(
                    pattern
                ),
            ),
        )

    def _reconcile_media(
        self, product: Product, inputs: list[ProductMediaInput], actor_id: UUID
    ) -> None:
        existing = {
            (row.media_kind, row.file_name, row.storage_path): row
            for row in product.media
        }
        requested_keys = {
            (item.media_kind, item.file_name, item.storage_path) for item in inputs
        }
        now = utc_now()
        for item in inputs:
            key = (item.media_kind, item.file_name, item.storage_path)
            current = existing.get(key)
            if current is None:
                product.media.append(self._build_media(product.firm_id, item, actor_id))
                continue
            current.mime_type = item.mime_type
            current.is_primary = item.is_primary
            current.file_size_bytes = item.file_size_bytes
            current.updated_by = actor_id
            current.is_deleted = False
            current.deleted_at = None
            current.deleted_by = None
        for key, row in existing.items():
            if key not in requested_keys:
                row.is_deleted = True
                row.deleted_at = now
                row.deleted_by = actor_id
                row.updated_by = actor_id

    def _product_values_from_model(self, product: Product) -> dict[str, object]:
        return {
            "code": product.code,
            "barcode": product.barcode,
            "qr_code": product.qr_code,
            "name": product.name,
            "short_name": product.short_name,
            "description": product.description,
            "product_type": product.product_type,
            "category_id": product.category_id,
            "sub_category_id": product.sub_category_id,
            "unit": product.unit,
            "brand": product.brand,
            "model": product.model,
            "hsn_sac": product.hsn_sac,
            "tax_profile_group_code": product.tax_profile_group_code,
            "base_uom_id": product.base_uom_id,
            "inventory_uom_id": product.inventory_uom_id,
            "purchase_uom_id": product.purchase_uom_id,
            "sales_uom_id": product.sales_uom_id,
            "default_receiving_uom_id": product.default_receiving_uom_id,
            "default_dispatch_uom_id": product.default_dispatch_uom_id,
            "minimum_sales_uom_id": product.minimum_sales_uom_id,
            "weight": product.weight,
            "volume": product.volume,
            "length": product.length,
            "width": product.width,
            "height": product.height,
            "allow_fraction": product.allow_fraction,
            "allow_decimal": product.allow_decimal,
            "purchase_price": product.purchase_price,
            "selling_price": product.selling_price,
            "mrp": product.mrp,
            "status": product.status,
            "remarks": product.remarks,
            "track_batch": product.track_batch,
            "track_lot": product.track_lot,
            "track_serial": product.track_serial,
            "track_expiry": product.track_expiry,
            "track_manufacturing_date": product.track_manufacturing_date,
            "track_warranty": product.track_warranty,
            "allow_negative_stock": product.allow_negative_stock,
            "require_batch_on_receipt": product.require_batch_on_receipt,
            "require_batch_on_issue": product.require_batch_on_issue,
            "require_serial_on_receipt": product.require_serial_on_receipt,
            "require_serial_on_issue": product.require_serial_on_issue,
        }

    @staticmethod
    def _media_input_from_model(row: ProductMedia) -> dict[str, object]:
        return {
            "media_kind": row.media_kind,
            "file_name": row.file_name,
            "mime_type": row.mime_type,
            "storage_path": row.storage_path,
            "is_primary": row.is_primary,
            "file_size_bytes": row.file_size_bytes,
        }

    def _next_duplicate_code(self, firm_id: UUID, code: str) -> str:
        base = f"{code}-COPY"
        candidate = base
        index = 1
        while (
            self._session.scalar(
                select(Product.id).where(
                    Product.firm_id == firm_id,
                    Product.code == candidate,
                    Product.is_deleted.is_(False),
                )
            )
            is not None
        ):
            candidate = f"{base}-{index}"
            index += 1
        return candidate

    def _commit(self) -> None:
        try:
            self._session.commit()
        except IntegrityError as error:
            self._session.rollback()
            raise ConflictError(
                "Product operation conflicts with existing data."
            ) from error

    def ensure_firm(self, firm_id: UUID) -> None:
        """Confirm the firm exists.

        Resolved through the platform store: ``firms`` is not in a firm schema,
        so querying it on the request session fails outside the platform store.
        """
        if not FirmMetadataReader(self._session).exists(firm_id):
            raise ResourceNotFoundError("Firm not found.")
