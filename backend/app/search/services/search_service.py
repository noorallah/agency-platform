"""Cross-module global search service with permission and firm awareness."""

from contextlib import ExitStack
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import Select, String, cast, or_, select
from sqlalchemy.orm import Session

from app.batch_serial.models import BatchRecord, LotRecord, SerialNumber
from app.branches.models import Branch, Warehouse, WarehouseStorageNode
from app.business.models import BusinessFeature, BusinessProfile
from app.common.firm_metadata import platform_reader
from app.core.database.entity import BaseEntity
from app.core.security.authorization import Principal
from app.customers.models import Customer
from app.delivery_note.models import DeliveryNote
from app.firms.models import Firm
from app.goods_receipt.models import GoodsReceipt
from app.identity.models import Permission, Role, User
from app.inventory.models import InventoryRecord, OpeningStockBatch, StockLedgerEntry
from app.products.models import Product, ProductCategory
from app.purchase.models import PurchaseOrder
from app.purchase_invoice.models import PurchaseInvoice
from app.purchase_return.models import PurchaseReturn
from app.sales.models import (
    GeoCity,
    GeoCountry,
    GeoDistrict,
    GeoLocality,
    GeoState,
    SalesTerritoryNode,
)
from app.sales_invoice.models import SalesInvoice
from app.sales_order.models import SalesOrder
from app.search.schemas import SearchCategory, SearchResultItem, SearchResultPage
from app.tax.models import TaxProfile, TaxRule, TaxSettings, TaxSystem
from app.uom.models import PackagingType, Uom
from app.vendors.models import Vendor


@dataclass(frozen=True, slots=True)
class SearchDefinition:
    """One searchable entity: where it lives, who may see it, what matches."""

    entity_type: str
    model: type
    module: str
    tab: str | None
    icon: str
    permission: str | None
    platform_admin_only: bool
    firm_column: str | None
    title_columns: tuple[str, ...]
    subtitle_columns: tuple[str, ...] = ()
    status_column: str | None = None
    badge_columns: tuple[str, ...] = ()
    category: SearchCategory = "all"
    #: The table exists **only in the platform schema**, so it has to be read
    #: on the platform connection rather than on the request's session.
    #:
    #: Not the same question as `firm_column is None`: `geo_countries` and its
    #: siblings have no firm column either, and they live in every firm store.
    #: The authority is `_PLATFORM_TABLES` in `app/core/tenancy/lifecycle.py`,
    #: which is the list provisioning drops from a firm store, and
    #: `test_search_reads_platform_tables_on_the_platform_store` compares this
    #: flag against it.
    platform_store: bool = False


_DEFINITIONS: tuple[SearchDefinition, ...] = (
    SearchDefinition(
        "users",
        User,
        "administration",
        "users",
        "user",
        "USER_VIEW",
        False,
        None,
        ("full_name", "email"),
        category="organization",
        platform_store=True,
    ),
    SearchDefinition(
        "roles",
        Role,
        "administration",
        "roles",
        "shield",
        "ROLE_VIEW",
        False,
        "firm_id",
        ("name", "code"),
        category="organization",
        platform_store=True,
    ),
    SearchDefinition(
        "permissions",
        Permission,
        "administration",
        "permissions",
        "key",
        "PERMISSION_VIEW",
        False,
        None,
        ("name", "code"),
        category="organization",
        platform_store=True,
    ),
    SearchDefinition(
        "firms",
        Firm,
        "administration",
        "user-firms",
        "apartment",
        "FIRM_VIEW",
        False,
        None,
        ("name", "code"),
        subtitle_columns=("city", "state"),
        status_column="is_active",
        category="organization",
        platform_store=True,
    ),
    SearchDefinition(
        "business_profiles",
        BusinessProfile,
        "administration",
        "business-profiles",
        "business",
        "PLATFORM_VIEW",
        True,
        None,
        ("name", "code", "industry_type"),
        status_column="status",
        category="masters",
    ),
    SearchDefinition(
        "feature_flags",
        BusinessFeature,
        "administration",
        "feature-management",
        "toggle",
        "PLATFORM_VIEW",
        True,
        None,
        ("name", "code"),
        subtitle_columns=("category",),
        status_column="is_active",
        category="masters",
    ),
    SearchDefinition(
        "customers",
        Customer,
        "masters",
        "customers",
        "groups",
        "CUSTOMER_VIEW",
        False,
        "firm_id",
        ("name", "code"),
        subtitle_columns=("email", "phone"),
        status_column="status",
        category="masters",
    ),
    SearchDefinition(
        "vendors",
        Vendor,
        "masters",
        "vendors",
        "store",
        "VENDOR_VIEW",
        False,
        "firm_id",
        ("name", "code"),
        subtitle_columns=("email", "phone"),
        status_column="status",
        category="masters",
    ),
    SearchDefinition(
        "products",
        Product,
        "masters",
        "products",
        "inventory",
        "PRODUCT_VIEW",
        False,
        "firm_id",
        ("name", "code", "barcode", "qr_code"),
        status_column="status",
        category="masters",
    ),
    SearchDefinition(
        "purchase_orders",
        PurchaseOrder,
        "purchases",
        "purchases",
        "shopping_cart",
        "PURCHASE_VIEW",
        False,
        "firm_id",
        ("po_number", "reference_number", "external_reference"),
        subtitle_columns=("vendor_contact",),
        status_column="status",
        category="masters",
    ),
    SearchDefinition(
        "sales_orders",
        SalesOrder,
        "salesOrders",
        "sales-orders",
        "point_of_sale",
        "SALES_VIEW",
        False,
        "firm_id",
        ("order_number", "reference_number", "customer_reference"),
        subtitle_columns=("remarks",),
        status_column="status",
        category="masters",
    ),
    SearchDefinition(
        "delivery_notes",
        DeliveryNote,
        "deliveryNotes",
        "delivery-notes",
        "local_shipping",
        "SALES_VIEW",
        False,
        "firm_id",
        ("delivery_note_number", "sales_order_reference", "vehicle"),
        subtitle_columns=("driver",),
        status_column="status",
        category="masters",
    ),
    SearchDefinition(
        "purchase_invoices",
        PurchaseInvoice,
        "purchaseInvoices",
        "purchase-invoices",
        "request_quote",
        "PURCHASE_VIEW",
        False,
        "firm_id",
        ("invoice_number", "supplier_invoice_number", "reference_number"),
        subtitle_columns=("payment_terms",),
        status_column="status",
        category="masters",
    ),
    SearchDefinition(
        "sales_invoices",
        SalesInvoice,
        "salesInvoices",
        "sales-invoices",
        "receipt_long",
        "SALES_VIEW",
        False,
        "firm_id",
        ("invoice_number", "customer_invoice_number", "reference_number"),
        subtitle_columns=("payment_terms",),
        status_column="status",
        category="masters",
    ),
    SearchDefinition(
        "purchase_returns",
        PurchaseReturn,
        "purchaseReturns",
        "purchase-returns",
        "assignment_return",
        "PURCHASE_VIEW",
        False,
        "firm_id",
        ("return_number", "supplier_return_number", "reference_number"),
        subtitle_columns=("return_reason",),
        status_column="status",
        category="masters",
    ),
    SearchDefinition(
        "goods_receipts",
        GoodsReceipt,
        "goodsReceipts",
        "receipts",
        "receipt_long",
        "PURCHASE_VIEW",
        False,
        "firm_id",
        ("grn_number", "purchase_order_number", "invoice_reference"),
        subtitle_columns=("vehicle_number", "transport_details"),
        status_column="status",
        category="masters",
    ),
    SearchDefinition(
        "product_categories",
        ProductCategory,
        "masters",
        "products",
        "category",
        "PRODUCT_VIEW",
        False,
        "firm_id",
        ("name", "code", "path"),
        status_column="is_active",
        category="masters",
    ),
    SearchDefinition(
        "tax_systems",
        TaxSystem,
        "administration",
        "tax-systems",
        "account_balance",
        "TAX_VIEW",
        False,
        "firm_id",
        ("name", "code", "display_name"),
        status_column="status",
        category="tax",
    ),
    SearchDefinition(
        "tax_profiles",
        TaxProfile,
        "administration",
        "tax-profiles",
        "receipt_long",
        "TAX_VIEW",
        False,
        "firm_id",
        ("name", "code", "label"),
        status_column="status",
        category="tax",
    ),
    SearchDefinition(
        "tax_rules",
        TaxRule,
        "administration",
        "tax-rules",
        "rule",
        "TAX_RULE_VIEW",
        False,
        "firm_id",
        ("name", "code"),
        status_column="status",
        badge_columns=("priority", "version_number"),
        category="tax",
    ),
    SearchDefinition(
        "uom",
        Uom,
        "administration",
        "uoms",
        "straighten",
        "UOM_VIEW",
        False,
        None,
        ("name", "code", "symbol"),
        status_column="status",
        category="masters",
    ),
    SearchDefinition(
        "packaging",
        PackagingType,
        "administration",
        "packaging-types",
        "inventory_2",
        "PACKAGING_MANAGE",
        False,
        None,
        ("name", "code"),
        status_column="status",
        category="masters",
    ),
    SearchDefinition(
        "territories",
        SalesTerritoryNode,
        "sales",
        "territories",
        "route",
        "TERRITORY_VIEW",
        False,
        "firm_id",
        ("name", "code", "path"),
        status_column="status",
        category="organization",
    ),
    SearchDefinition(
        "routes",
        SalesTerritoryNode,
        "sales",
        "routes",
        "alt_route",
        "TERRITORY_VIEW",
        False,
        "firm_id",
        ("name", "code"),
        status_column="status",
        category="organization",
    ),
    SearchDefinition(
        "branches",
        Branch,
        "masters",
        "branches",
        "account_tree",
        "BRANCH_VIEW",
        False,
        "firm_id",
        ("name", "code"),
        status_column="status",
        category="organization",
    ),
    SearchDefinition(
        "warehouses",
        Warehouse,
        "masters",
        "warehouses",
        "warehouse",
        "WAREHOUSE_VIEW",
        False,
        "firm_id",
        ("name", "code"),
        status_column="status",
        category="organization",
    ),
    SearchDefinition(
        "storage_areas",
        WarehouseStorageNode,
        "masters",
        "storage-areas",
        "shelves",
        "STORAGE_AREA_MANAGE",
        False,
        None,
        ("name", "code", "path"),
        status_column="is_active",
        category="organization",
    ),
    SearchDefinition(
        "inventory",
        InventoryRecord,
        "inventory",
        "inventory",
        "inventory_2",
        "INVENTORY_VIEW",
        False,
        "firm_id",
        ("storage_locator",),
        subtitle_columns=("status",),
        status_column="status",
        badge_columns=("current_quantity", "available_quantity"),
        category="inventory",
    ),
    SearchDefinition(
        "opening_stock",
        OpeningStockBatch,
        "inventory",
        "opening-stock",
        "upload_file",
        "INVENTORY_VIEW",
        False,
        "firm_id",
        ("reference_number",),
        subtitle_columns=("status",),
        status_column="status",
        category="inventory",
    ),
    SearchDefinition(
        "stock_ledger",
        StockLedgerEntry,
        "inventory",
        "stock-ledger",
        "receipt",
        "INVENTORY_LEDGER_VIEW",
        False,
        "firm_id",
        ("reference_number", "reference_type"),
        subtitle_columns=("transaction_type",),
        category="inventory",
    ),
    SearchDefinition(
        "batch",
        BatchRecord,
        "inventory",
        "batches",
        "layers",
        "BATCH_VIEW",
        False,
        "firm_id",
        ("batch_number", "supplier_batch", "internal_batch"),
        status_column="status",
        category="inventory",
    ),
    SearchDefinition(
        "lot",
        LotRecord,
        "inventory",
        "lots",
        "dataset",
        "BATCH_VIEW",
        False,
        "firm_id",
        ("lot_number",),
        status_column="status",
        category="inventory",
    ),
    SearchDefinition(
        "serial",
        SerialNumber,
        "inventory",
        "serials",
        "qr_code_scanner",
        "SERIAL_VIEW",
        False,
        "firm_id",
        ("serial_number",),
        status_column="status",
        category="inventory",
    ),
    SearchDefinition(
        "expiry",
        BatchRecord,
        "inventory",
        "expiry",
        "event_busy",
        "BATCH_VIEW",
        False,
        "firm_id",
        ("batch_number",),
        subtitle_columns=("expiry_date",),
        status_column="status",
        category="inventory",
    ),
    SearchDefinition(
        "geo_masters",
        GeoCountry,
        "settings",
        "geo-masters",
        "public",
        "TERRITORY_VIEW",
        False,
        None,
        ("name", "code", "iso2", "iso3"),
        status_column="is_active",
        category="organization",
    ),
    SearchDefinition(
        "geo_masters",
        GeoState,
        "settings",
        "geo-masters",
        "map",
        "TERRITORY_VIEW",
        False,
        None,
        ("name", "code"),
        status_column="is_active",
        category="organization",
    ),
    SearchDefinition(
        "geo_masters",
        GeoDistrict,
        "settings",
        "geo-masters",
        "location_city",
        "TERRITORY_VIEW",
        False,
        None,
        ("name", "code"),
        status_column="is_active",
        category="organization",
    ),
    SearchDefinition(
        "geo_masters",
        GeoCity,
        "settings",
        "geo-masters",
        "location_on",
        "TERRITORY_VIEW",
        False,
        None,
        ("name", "code"),
        status_column="is_active",
        category="organization",
    ),
    SearchDefinition(
        "geo_masters",
        GeoLocality,
        "settings",
        "geo-masters",
        "pin_drop",
        "TERRITORY_VIEW",
        False,
        None,
        ("name",),
        status_column="is_active",
        category="organization",
    ),
    SearchDefinition(
        "settings",
        TaxSettings,
        "settings",
        "tax-settings",
        "settings",
        "TAX_MANAGE_SETTINGS",
        False,
        "firm_id",
        ("primary_label", "component_label", "profile_label"),
        category="tax",
    ),
)

_CATEGORY_ENTITY_TYPES: dict[SearchCategory, set[str]] = {
    "all": {item.entity_type for item in _DEFINITIONS},
    "masters": {
        "customers",
        "vendors",
        "products",
        "product_categories",
        "uom",
        "packaging",
        "purchase_orders",
        "sales_orders",
        "delivery_notes",
        "purchase_invoices",
        "sales_invoices",
        "purchase_returns",
        "goods_receipts",
        "business_profiles",
        "feature_flags",
    },
    "inventory": {
        "inventory",
        "opening_stock",
        "stock_ledger",
        "batch",
        "lot",
        "serial",
        "expiry",
    },
    "tax": {"tax_systems", "tax_profiles", "tax_rules", "settings"},
    "organization": {
        "users",
        "roles",
        "permissions",
        "firms",
        "branches",
        "warehouses",
        "storage_areas",
        "territories",
        "routes",
        "geo_masters",
    },
}


class SearchService:
    """Execute permission-aware global search over implemented modules."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request unit of work."""
        self._session = session

    def search(
        self,
        *,
        query: str,
        principal: Principal,
        category: SearchCategory,
        page: int,
        page_size: int,
        entity_types: set[str] | None = None,
        include_deleted: bool = False,
    ) -> SearchResultPage:
        """Search every entity the caller may see, in the firm in scope."""
        normalized_query = query.strip()
        allowed_types = _CATEGORY_ENTITY_TYPES.get(
            category, _CATEGORY_ENTITY_TYPES["all"]
        )
        if entity_types is not None:
            allowed_types = allowed_types.intersection(entity_types)
        per_entity_limit = max(page_size, 20)
        hits: list[SearchResultItem] = []
        # Opened once, and only when it is both needed and unavoidable:
        #
        #   * a platform-owned entity has to be in scope -- a search narrowed
        #     to customers costs no second connection;
        #   * and the request has to be firm-scoped. With no `X-Firm-ID`,
        #     `get_db` resolves no tenant and hands over the platform session
        #     already, so reaching for a second one would open a connection to
        #     read a table the caller can see anyway.
        with ExitStack() as stack:
            platform: Session | None = None
            for definition in _DEFINITIONS:
                if definition.entity_type not in allowed_types:
                    continue
                if not self._is_accessible(definition, principal):
                    continue
                if (
                    definition.platform_store
                    and platform is None
                    and principal.firm_id is not None
                ):
                    platform = stack.enter_context(platform_reader())
                hits.extend(
                    self._search_definition(
                        definition=definition,
                        query=normalized_query,
                        principal=principal,
                        include_deleted=include_deleted,
                        limit=per_entity_limit,
                        platform=platform,
                    )
                )
        total = len(hits)
        start = (page - 1) * page_size
        end = start + page_size
        return SearchResultPage(
            query=normalized_query,
            category=category,
            page=page,
            page_size=page_size,
            total=total,
            results=hits[start:end],
        )

    def _is_accessible(
        self, definition: SearchDefinition, principal: Principal
    ) -> bool:
        if definition.platform_admin_only and not principal.is_platform_admin:
            return False
        if definition.permission is None:
            return True
        return principal.has_permission(definition.permission)

    def _search_definition(
        self,
        *,
        definition: SearchDefinition,
        query: str,
        principal: Principal,
        include_deleted: bool,
        limit: int,
        platform: Session | None = None,
    ) -> list[SearchResultItem]:
        model = definition.model
        statement: Select[tuple[Any]] = select(model)
        if hasattr(model, "is_deleted") and not include_deleted:
            statement = statement.where(model.is_deleted.is_(False))
        if definition.firm_column is not None:
            # Firm-owned rows are searched inside one firm, never across firms.
            # Platform admins used to skip the filter entirely, so in a SHARED
            # deployment -- where one schema holds every firm's rows -- an admin
            # with no firm selected got results from all of them in one list.
            # A null firm column means the row belongs to the platform rather
            # than to a firm (roles are the case that matters), so those stay
            # visible either way.
            column = getattr(model, definition.firm_column)
            firm_id = principal.firm_id
            statement = statement.where(
                column.is_(None)
                if firm_id is None
                else or_(column == firm_id, column.is_(None))
            )
        if query:
            search_conditions = []
            for field in (*definition.title_columns, *definition.subtitle_columns):
                column = getattr(model, field, None)
                if column is None:
                    continue
                search_conditions.append(cast(column, String).ilike(f"%{query}%"))
            if search_conditions:
                statement = statement.where(or_(*search_conditions))
        if hasattr(model, "updated_at"):
            statement = statement.order_by(model.updated_at.desc())
        elif hasattr(model, "created_at"):
            statement = statement.order_by(model.created_at.desc())
        # Both timestamps are the transaction's start instant, so every row one
        # request wrote shares them and the cut at `limit` would otherwise take
        # an arbitrary subset of the tie.
        if hasattr(model, "id"):
            statement = statement.order_by(model.id.desc())
        statement = statement.limit(limit)
        # `users`, `roles`, `permissions` and `firms` exist only in the
        # platform schema. A request carrying `X-Firm-ID` runs on a tenant
        # session whose `search_path` is that firm's schema and nothing else,
        # so reading them there raised `relation "<firm schema>.users" does
        # not exist` -- and because one definition failing aborts the whole
        # search, **every** global search from inside a firm answered 503.
        # Fourth occurrence of this shape; see `platform_reader`.
        # `platform` is None when the request carries no firm, and then the
        # session in hand is the platform store already.
        reader = platform if definition.platform_store and platform else self._session
        rows = reader.scalars(statement).all()
        return [
            self._to_item(definition=definition, row=row, query=query)
            for row in rows
            if self._include_row(definition, row)
        ]

    def _include_row(self, definition: SearchDefinition, row: object) -> bool:
        if definition.entity_type == "expiry":
            return getattr(row, "expiry_date", None) is not None
        return True

    def _to_item(
        self,
        *,
        definition: SearchDefinition,
        row: BaseEntity,
        query: str,
    ) -> SearchResultItem:
        title_parts = [
            self._string_value(getattr(row, field, None))
            for field in definition.title_columns
        ]
        subtitle_parts = [
            self._string_value(getattr(row, field, None))
            for field in definition.subtitle_columns
        ]
        title = next((part for part in title_parts if part), str(row.id))
        subtitle = " | ".join([part for part in subtitle_parts if part]) or None
        badges = [
            self._string_value(getattr(row, field, None))
            for field in definition.badge_columns
        ]
        status = None
        if definition.status_column is not None:
            status = self._status_value(getattr(row, definition.status_column, None))
        matched_fields = self._matched_fields(definition, row, query)
        entity_id = row.id
        return SearchResultItem(
            id=str(entity_id),
            entity_type=definition.entity_type,
            module=definition.module,
            tab=definition.tab,
            title=title,
            subtitle=subtitle,
            status=status,
            icon=definition.icon,
            badges=[item for item in badges if item],
            navigation_path=self._navigation_path(definition, entity_id),
            matched_fields=matched_fields,
        )

    @staticmethod
    def _navigation_path(definition: SearchDefinition, entity_id: UUID) -> str:
        if definition.tab is None:
            return definition.module
        return f"{definition.module}/{definition.tab}/{entity_id}"

    @staticmethod
    def _string_value(value: object) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @staticmethod
    def _status_value(value: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return "ACTIVE" if value else "INACTIVE"
        text = str(value).strip()
        return text or None

    def _matched_fields(
        self,
        definition: SearchDefinition,
        row: object,
        query: str,
    ) -> list[str]:
        if not query:
            return []
        lowered = query.casefold()
        matched: list[str] = []
        for field in (*definition.title_columns, *definition.subtitle_columns):
            value = self._string_value(getattr(row, field, None))
            if value and lowered in value.casefold():
                matched.append(field)
        return matched
