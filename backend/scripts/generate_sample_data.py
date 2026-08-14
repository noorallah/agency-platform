"""Development-only enterprise data reset and reseed utility."""

from __future__ import annotations

import argparse
import importlib
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from random import Random
from typing import Any
from uuid import UUID

from sqlalchemy import Table, delete, func, inspect, select, text
from sqlalchemy.orm import Session

import app.core.database.all_models  # noqa: F401
from app.api.dependencies.settings import get_settings
from app.branches.models import (
    Branch,
    BranchType,
    Warehouse,
    WarehouseStorageNode,
    WarehouseType,
)
from app.branches.schemas import (
    BranchCreate,
    BranchStatus,
    BranchTypeWrite,
    StorageNodeCreate,
    StorageNodeType,
    WarehouseCreate,
    WarehouseStatus,
    WarehouseTypeWrite,
)
from app.branches.services.branch_warehouse_service import BranchWarehouseService
from app.business.models import (
    AttributeDefinition,
    BusinessProfile,
    CategoryAttributeRule,
)
from app.business.schemas import FirmBusinessProfileAssign
from app.business.services.framework_service import BusinessProfileFrameworkService
from app.business.system_seed import seed_business_profiles
from app.common.audit.models.audit_log import AuditLog
from app.core.config.settings import Environment, Settings
from app.core.database.base import Base
from app.core.database.engine import DatabaseManager
from app.core.database.entity import BaseEntity
from app.core.exceptions import ValidationError
from app.customers.models import Customer
from app.customers.schemas import (
    CustomerAddressInput,
    CustomerContactInput,
    CustomerCreate,
)
from app.customers.schemas.customer import AddressType as CustomerAddressType
from app.customers.schemas.customer import CustomerStatus, CustomerType
from app.customers.services.customer_service import CustomerService
from app.delivery_note.models import (
    DeliveryNote,
    DeliveryNoteAttachment,
    DeliveryNoteLine,
    DeliveryNoteNote,
)
from app.document_framework.models import (
    DocumentHeader,
    DocumentLifecycleEvent,
    DocumentLine,
    DocumentNumberingRule,
    DocumentStateDefinition,
    DocumentTotal,
    DocumentTypeDefinition,
)
from app.firms.models import Firm, FirmStorageMapping
from app.firms.schemas import FirmCreate
from app.firms.services.firm_service import FirmService
from app.goods_receipt.models import (
    GoodsReceipt,
    GoodsReceiptAttachment,
    GoodsReceiptLine,
    GoodsReceiptNote,
)
from app.identity.models import (
    Permission,
    PlatformAdmin,
    Role,
    RolePermission,
    User,
)
from app.identity.schemas.api import UserCreate, UserFirmAssignment
from app.identity.services.identity_service import IdentityService
from app.identity.system_seed import seed_system_rbac
from app.inventory.models import (
    InventoryRecord,
    InventoryTransaction,
    OpeningStockBatch,
    OpeningStockLine,
    StockLedgerEntry,
)
from app.products.models import (
    Product,
    ProductCategory,
)
from app.products.schemas import (
    ProductAttributeInput,
    ProductCategoryCreate,
    ProductCreate,
)
from app.products.schemas.product import ProductStatus, ProductType
from app.products.services.product_service import ProductService
from app.purchase.models import (
    PurchaseAttachment,
    PurchaseDeliverySchedule,
    PurchaseNote,
    PurchaseOrder,
    PurchaseOrderHistory,
    PurchaseOrderLine,
)
from app.purchase_invoice.models import (
    PurchaseInvoice,
    PurchaseInvoiceAccountingEvent,
    PurchaseInvoiceAttachment,
    PurchaseInvoiceLine,
    PurchaseInvoiceNote,
    PurchaseInvoiceSource,
)
from app.purchase_return.models import (
    PurchaseReturn,
    PurchaseReturnAccountingEvent,
    PurchaseReturnAttachment,
    PurchaseReturnLine,
    PurchaseReturnNote,
    PurchaseReturnSource,
)
from app.sales.models import (
    GeoCity,
    GeoCountry,
    GeoDistrict,
    GeoLocality,
    GeoPostalCode,
    GeoState,
    SalesTerritoryNode,
    TerritoryRouteProfile,
)
from app.sales.schemas import (
    GeoCityWrite,
    GeoCountryWrite,
    GeoDistrictWrite,
    GeoLocalityWrite,
    GeoPostalCodeWrite,
    GeoStateWrite,
    RouteTypeWrite,
)
from app.sales.schemas.territory import (
    HierarchyLevelInput,
    HierarchyUpdateRequest,
    RouteProfileInput,
    SalesmanAssignmentInput,
    TerritoryAssignCustomersRequest,
    TerritoryAssignSalesmenRequest,
    TerritoryCreate,
    TerritoryCustomerAssignmentInput,
    TerritoryStatus,
    VisitFrequency,
)
from app.sales.services.territory_service import SalesTerritoryService
from app.sales_invoice.models import (
    SalesInvoice,
    SalesInvoiceAccountingEvent,
    SalesInvoiceAttachment,
    SalesInvoiceLine,
    SalesInvoiceNote,
    SalesInvoiceSource,
)
from app.sales_order.models import (
    SalesOrder,
    SalesOrderAttachment,
    SalesOrderLine,
    SalesOrderNote,
)
from app.tax.models import (
    TaxComponent,
    TaxProfile,
    TaxRule,
    TaxSystem,
)
from app.tax.schemas import (
    TaxComponentWrite,
    TaxCountryMappingWrite,
    TaxMigrationMappingWrite,
    TaxProfileComponentInput,
    TaxProfileWrite,
    TaxRuleActionType,
    TaxRuleActionWrite,
    TaxRuleConditionOperator,
    TaxRuleConditionWrite,
    TaxRuleSimulationRequest,
    TaxRuleWrite,
    TaxSettingsWrite,
    TaxStatus,
    TaxSystemWrite,
)
from app.tax.services.tax_framework_service import TaxFrameworkService
from app.tax.services.tax_rule_service import TaxRuleService
from app.uom.models import (
    BusinessProfileUomDefault,
    ConversionRule,
    PackagingType,
    ProductPackagingLevel,
    Uom,
    UomGroup,
    UomGroupUnit,
)
from app.uom.system_seed import seed_uom_reference_data
from app.vendors.models import (
    Vendor,
)
from app.vendors.schemas import (
    VendorAddressInput,
    VendorAttachmentInput,
    VendorBankInput,
    VendorCategoryWrite,
    VendorContactInput,
    VendorCreate,
    VendorNoteInput,
    VendorStatus,
    VendorTaxInput,
    VendorTypeWrite,
)
from app.vendors.schemas.vendor import AddressType as VendorAddressType
from app.vendors.services.vendor_service import VendorService

DEVELOPMENT_PASSWORD = "Password@123"
SYSTEM_ACTOR_ID = UUID("00000000-0000-0000-0000-000000000111")
RANDOM = Random(20260801)
REPO_ROOT = Path(__file__).resolve().parents[2]
USERS_DOC_PATH = REPO_ROOT / "DEVELOPMENT_USERS.md"
SUMMARY_DOC_PATH = REPO_ROOT / "DEVELOPMENT_DATA_SUMMARY.md"
INDIA_CODE = "IN"

FIRM_BLUEPRINTS = (
    {
        "key": "NAVKAR_DISTRIBUTION",
        "name": "Navkar Consumer Distribution Private Limited",
        "code": "NAVKAR_CPL",
        "city": "Mumbai",
        "state": "Maharashtra",
        "postal_code": "400001",
        "profile_codes": ("GENERIC",),
        "notes": "Coherent single-company enterprise ERP dataset for all completed "
        "modules.",
        "branches": (
            ("NVK_HO", "Mumbai Head Office", "Mumbai", "Maharashtra"),
            ("NVK_PUN", "Pune Sales Branch", "Pune", "Maharashtra"),
            ("NVK_BLR", "Bengaluru Operations Branch", "Bengaluru", "Karnataka"),
        ),
        "territory_states": ("Maharashtra", "Karnataka"),
        "route_type_pattern": ("SALES", "DELIVERY", "COLLECTION", "SERVICE", "SURVEY"),
        "warehouses": (
            ("MAIN", "Main Distribution Warehouse"),
            ("RET", "Returns and QC Warehouse"),
        ),
    },
)

GEO_BLUEPRINT = {
    "Telangana": {
        "code": "TS",
        "districts": {
            "Hyderabad": {
                "code": "HYD",
                "cities": {
                    "Hyderabad": {
                        "code": "HYD",
                        "postal_codes": {
                            "500001": ["Abids", "Koti"],
                            "500034": ["Banjara Hills", "Jubilee Hills"],
                        },
                    },
                    "Secunderabad": {
                        "code": "SCB",
                        "postal_codes": {
                            "500003": ["MG Road", "Bowenpally"],
                            "500009": ["Trimulgherry", "Paradise"],
                        },
                    },
                },
            },
            "Warangal": {
                "code": "WRG",
                "cities": {
                    "Warangal": {
                        "code": "WRG",
                        "postal_codes": {
                            "506002": ["Hanamkonda", "Kazipet"],
                            "506007": ["Subedari", "Nakkalagutta"],
                        },
                    }
                },
            },
        },
    },
    "Karnataka": {
        "code": "KA",
        "districts": {
            "Bengaluru Urban": {
                "code": "BLRU",
                "cities": {
                    "Bengaluru": {
                        "code": "BLR",
                        "postal_codes": {
                            "560001": ["MG Road", "Brigade Road"],
                            "560038": ["Indiranagar", "Domlur"],
                        },
                    }
                },
            },
            "Mysuru": {
                "code": "MYS",
                "cities": {
                    "Mysuru": {
                        "code": "MYS",
                        "postal_codes": {
                            "570001": ["Agrahara", "Devaraja Mohalla"],
                            "570017": ["Vijayanagar", "Gokulam"],
                        },
                    }
                },
            },
        },
    },
    "Tamil Nadu": {
        "code": "TN",
        "districts": {
            "Chennai": {
                "code": "CHN",
                "cities": {
                    "Chennai": {
                        "code": "CHN",
                        "postal_codes": {
                            "600001": ["George Town", "Parrys"],
                            "600040": ["Anna Nagar", "Mogappair"],
                        },
                    }
                },
            },
            "Coimbatore": {
                "code": "CBE",
                "cities": {
                    "Coimbatore": {
                        "code": "CBE",
                        "postal_codes": {
                            "641001": ["Town Hall", "RS Puram"],
                            "641045": ["Peelamedu", "Singanallur"],
                        },
                    }
                },
            },
        },
    },
    "Kerala": {
        "code": "KL",
        "districts": {
            "Ernakulam": {
                "code": "EKM",
                "cities": {
                    "Kochi": {
                        "code": "KOC",
                        "postal_codes": {
                            "682001": ["Fort Kochi", "Mattancherry"],
                            "682020": ["Kadavanthra", "Panampilly Nagar"],
                        },
                    }
                },
            },
            "Thiruvananthapuram": {
                "code": "TVM",
                "cities": {
                    "Thiruvananthapuram": {
                        "code": "TVM",
                        "postal_codes": {
                            "695001": ["Statue", "Palayam"],
                            "695014": ["Pattom", "Kesavadasapuram"],
                        },
                    }
                },
            },
        },
    },
    "Maharashtra": {
        "code": "MH",
        "districts": {
            "Mumbai": {
                "code": "MUM",
                "cities": {
                    "Mumbai": {
                        "code": "MUM",
                        "postal_codes": {
                            "400001": ["Fort", "Churchgate"],
                            "400053": ["Andheri West", "Oshiwara"],
                        },
                    }
                },
            },
            "Pune": {
                "code": "PUN",
                "cities": {
                    "Pune": {
                        "code": "PUN",
                        "postal_codes": {
                            "411001": ["Camp", "Deccan"],
                            "411014": ["Viman Nagar", "Kharadi"],
                        },
                    }
                },
            },
        },
    },
    "Gujarat": {
        "code": "GJ",
        "districts": {
            "Ahmedabad": {
                "code": "AMD",
                "cities": {
                    "Ahmedabad": {
                        "code": "AMD",
                        "postal_codes": {
                            "380001": ["Kalupur", "Relief Road"],
                            "380015": ["Vastrapur", "Bodakdev"],
                        },
                    }
                },
            },
            "Surat": {
                "code": "SUR",
                "cities": {
                    "Surat": {
                        "code": "SUR",
                        "postal_codes": {
                            "395003": ["Nanpura", "Ring Road"],
                            "395007": ["Adajan", "Vesu"],
                        },
                    }
                },
            },
        },
    },
}

CUSTOMER_SEGMENTS = (
    ("Retail", "Medical Shop"),
    ("Wholesale", "Wholesale Mart"),
    ("Hospital", "Hospital"),
    ("Medical Shop", "Pharmacy"),
    ("Super Market", "Super Market"),
    ("Restaurant", "Restaurant"),
    ("Distributor", "Distributor"),
    ("Corporate", "Corporate"),
)

VENDOR_SEGMENTS = (
    ("MANUFACTURER", "Manufacturer"),
    ("IMPORTER", "Importer"),
    ("DISTRIBUTOR", "Distributor"),
    ("TRANSPORT", "Transport"),
    ("SERVICE_PROVIDER", "Service Provider"),
)

MEDICINE_PRODUCTS = (
    ("Paracetamol", "Tablet", "3004"),
    ("Amoxicillin", "Capsule", "3003"),
    ("Vitamin C", "Tablet", "3004"),
    ("Cetirizine", "Tablet", "3004"),
    ("ORS", "Sachet", "3004"),
    ("Cough Syrup", "Bottle", "3004"),
)
FOOD_PRODUCTS = (
    ("Basmati Rice", "Bag", "1006"),
    ("Sunflower Oil", "Can", "1512"),
    ("Whole Wheat Flour", "Bag", "1101"),
    ("Tomato Puree", "Carton", "2002"),
    ("Frozen Peas", "Pack", "0710"),
    ("Premium Biscuit", "Box", "1905"),
)
ELECTRONIC_PRODUCTS = (
    ("LED TV", "Unit", "8528"),
    ("Bluetooth Speaker", "Unit", "8518"),
    ("Power Bank", "Unit", "8507"),
    ("Smartphone", "Unit", "8517"),
    ("USB Router", "Unit", "8517"),
    ("Air Fryer", "Unit", "8516"),
)
GENERAL_PRODUCTS = (
    ("Office Chair", "Unit", "9401"),
    ("Industrial Tape", "Roll", "3919"),
    ("Safety Helmet", "Unit", "6506"),
    ("LED Bulb", "Unit", "8539"),
    ("Hand Tool Kit", "Set", "8206"),
    ("Printer Paper", "Ream", "4802"),
)
BRANDS = (
    "Aster",
    "Nova",
    "Zenith",
    "Meridian",
    "BluePeak",
    "PrimeCare",
    "HarvestOne",
    "Orbit",
    "Vertex",
    "Brighton",
)
FIRST_NAMES = (
    "Aarav",
    "Isha",
    "Rohan",
    "Meera",
    "Kabir",
    "Ananya",
    "Dev",
    "Naina",
    "Arjun",
    "Kavya",
    "Vihaan",
    "Saanvi",
    "Aditya",
    "Ritika",
    "Neel",
    "Pooja",
)
LAST_NAMES = (
    "Sharma",
    "Reddy",
    "Kulkarni",
    "Patel",
    "Nair",
    "Iyer",
    "Mehta",
    "Joshi",
    "Shetty",
    "Gupta",
)


@dataclass
class LoginRecord:
    """One account the generated data can be signed in with."""

    username: str
    role: str
    firm: str
    branch: str
    description: str


@dataclass
class GenerationArtifacts:
    """What a run produced, for the summary printed at the end."""

    counts: Counter[str]
    logins: list[LoginRecord]
    notes: list[str]


@dataclass
class FirmContext:
    """One firm mid-generation, with the masters already made for it."""

    key: str
    firm: Firm
    profile: BusinessProfile
    branches: list[Branch]
    warehouses: list[Warehouse]
    route_types: dict[str, Any]
    route_leaf_ids: list[UUID]
    primary_routes: list[UUID]
    tax_profiles: dict[str, TaxProfile]
    product_categories: dict[str, ProductCategory]
    salesmen: list[User]
    branch_by_name: dict[str, Branch]
    warehouse_by_name: dict[str, Warehouse]


def main() -> None:
    """Generate the development sample dataset and report what it made."""
    parser = argparse.ArgumentParser(
        description="Reset and reseed the development ERP dataset."
    )
    parser.add_argument(
        "mode",
        nargs="?",
        choices=("reseed", "reset", "products"),
        default="reseed",
        help="Use 'reset' to delete generated data only, or 'products' for "
        "product-focused seed data.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the destructive-operation confirmation prompt.",
    )
    args = parser.parse_args()

    settings = get_settings()
    _assert_allowed_environment(settings)
    if not args.yes:
        _confirm_or_exit(args.mode)

    database = DatabaseManager.from_settings(settings)
    try:
        with database.sessions().session() as session:
            _configure_seed_search_path(session, settings)
            _reset_development_data(session, settings)
            seed_system_rbac(session)
            seed_business_profiles(session)
            seed_uom_reference_data(session)
            session.commit()
            if args.mode == "reset":
                USERS_DOC_PATH.write_text(
                    "# Development Users\n\n"
                    "Development data has been reset. "
                    "No seeded users are present.\n",
                    encoding="utf-8",
                )
                SUMMARY_DOC_PATH.write_text(
                    "# Development Data Summary\n\n"
                    "Development data has been reset. "
                    "No seeded business dataset is present.\n",
                    encoding="utf-8",
                )
                print("Development data reset completed.")
                return
            artifacts = _seed_enterprise_dataset(
                session,
                settings,
                products_only=args.mode == "products",
            )
            USERS_DOC_PATH.write_text(
                _render_users_doc(artifacts.logins), encoding="utf-8"
            )
            SUMMARY_DOC_PATH.write_text(
                _render_summary_doc(artifacts.counts, artifacts.notes),
                encoding="utf-8",
            )
            _print_summary(artifacts.counts)
    finally:
        database.dispose()


def _configure_seed_search_path(session: Session, settings: Settings) -> None:
    """Ensure seed queries can resolve platform + shared-firm tables."""
    if session.bind is None or session.bind.dialect.name != "postgresql":
        return
    platform_schema = settings.database_schema or "platform"
    shared_schema = settings.tenancy_shared_schema_name or "firm_shared"
    if platform_schema == shared_schema:
        session.execute(text(f'SET search_path TO "{platform_schema}", public'))
        return
    session.execute(
        text(f'SET search_path TO "{platform_schema}", "{shared_schema}", public')
    )


def _assert_allowed_environment(settings: Settings) -> None:
    if settings.environment not in {Environment.DEVELOPMENT, Environment.TESTING}:
        raise RuntimeError(
            "Development data generator is blocked outside development/testing "
            "environments."
        )


def _confirm_or_exit(mode: str) -> None:
    print("WARNING")
    if mode == "reset":
        print("This will DELETE the generated development dataset.")
    else:
        print("This will DELETE and RECREATE the generated development dataset.")
    response = input("Continue? (YES/NO): ").strip().upper()
    if response != "YES":
        raise SystemExit("Operation cancelled.")


def _reset_schemas(settings: Settings) -> tuple[str, ...]:
    """Return the schemas a reset clears, platform first.

    The seed session sees both through its search path, which is why the
    delete has to name one: a table that exists in both -- and several do --
    otherwise resolves to the platform copy while the firm_shared rows survive
    to break the next foreign key.
    """
    platform_schema = settings.database_schema or "platform"
    shared_schema = settings.tenancy_shared_schema_name or "firm_shared"
    if platform_schema == shared_schema:
        return (platform_schema,)
    return (platform_schema, shared_schema)


def _safe_delete_table(session: Session, table: Table, schema: str | None) -> None:
    """Clear one table in one schema, skipping it where it does not exist.

    The platform schema holds the platform tables and firm_shared the
    firm-owned ones, so most tables are in exactly one of the two and the other
    pass skips them. The names come from the metadata, so unlike a
    hand-maintained list they cannot be wrong -- only absent.
    """
    bind = session.get_bind()
    if bind is None:
        return
    if bind.dialect.name != "postgresql":
        if not inspect(bind).has_table(table.name):
            return
        session.execute(table.delete())
        return
    qualified = f'"{schema}"."{table.name}"' if schema else f'"{table.name}"'
    exists = session.scalar(
        text("SELECT to_regclass(:name) IS NOT NULL"), {"name": qualified}
    )
    if not exists:
        return
    session.execute(text(f"DELETE FROM {qualified}"))  # noqa: S608


def _safe_delete(session: Session, model: type[BaseEntity]) -> None:
    bind = session.get_bind()
    if bind is None:
        return
    table_name = model.__table__.name
    if bind.dialect.name == "postgresql":
        exists = session.scalar(
            text("SELECT to_regclass(:table_name) IS NOT NULL"),
            {"table_name": table_name},
        )
        if not exists:
            return
        session.execute(delete(model))
        return
    if inspect(bind).has_table(table_name):
        session.execute(delete(model))


#: Tables `--reset` must not clear, and why each one survives.
#:
#: Everything else is generated data and goes. The delete order is derived from
#: the schema rather than listed by hand: the old tuple named 108 models for a
#: 169-table schema, so a reset died on whichever foreign key the missing 61
#: violated first, and it had already gone stale four times.
PRESERVED_TABLES: frozenset[str] = frozenset(
    {
        # Alembic's own bookkeeping. Clearing it would make the database look
        # unmigrated and the next `upgrade` would replay everything.
        "alembic_version",
        # The business-profile catalogue is seeded by migrations
        # (`20260801_0011`, `20260809_0046`, `20260810_0059`,
        # `20260812_0067`) and by nothing else. Deleting it leaves a platform
        # with no features or modules and no way back short of a downgrade;
        # the per-firm assignment in `firm_business_profiles` is generated and
        # is cleared.
        "business_profiles",
        "business_features",
        "business_modules",
        "profile_features",
        "profile_modules",
        # Cleared below with rules the generic pass cannot express: platform
        # admins and their users survive, system roles and permissions
        # survive, and the audit trail is truncated rather than deleted
        # because it is append-only.
        "users",
        "platform_admins",
        "roles",
        "permissions",
        "role_permissions",
        "firms",
        "firm_storage_mappings",
        "audit_logs",
    }
)


def _generated_tables() -> list[Table]:
    """Return every table `--reset` clears, children before their parents.

    ``sorted_tables`` is ordered so a table follows everything it depends on;
    reversed, that is a delete order whose foreign keys are satisfied by
    construction. Self-referencing tables -- territory nodes, storage nodes,
    account groups -- are fine, because a single `DELETE FROM t` removes the
    parent and child rows in one statement.
    """
    return [
        table
        for table in reversed(Base.metadata.sorted_tables)
        if table.name not in PRESERVED_TABLES
    ]


def _reset_development_data(session: Session, settings: Settings) -> None:
    preserved_platform_admin_ids = set(
        session.scalars(
            select(PlatformAdmin.user_id).where(PlatformAdmin.is_deleted.is_(False))
        ).all()
    )

    # Derived from the schema, not listed here: see PRESERVED_TABLES. Each
    # schema is cleared in full before the next, children before parents.
    for schema in _reset_schemas(settings):
        for table in _generated_tables():
            _safe_delete_table(session, table, schema)

    session.execute(
        delete(RolePermission).where(
            RolePermission.role_id.in_(select(Role.id).where(Role.is_system.is_(False)))
        )
    )
    session.execute(delete(Role).where(Role.is_system.is_(False)))
    session.execute(delete(Permission).where(Permission.is_system.is_(False)))

    if preserved_platform_admin_ids:
        session.execute(
            delete(User).where(
                User.id.not_in(preserved_platform_admin_ids),
            )
        )
    else:
        session.execute(delete(User))
        session.execute(delete(PlatformAdmin))

    _safe_delete(session, FirmStorageMapping)
    session.execute(delete(Firm))
    _purge_audit_logs(session)
    session.commit()


def _purge_audit_logs(session: Session) -> None:
    dialect = session.bind.dialect.name if session.bind is not None else ""
    if dialect == "postgresql":
        session.execute(text("TRUNCATE TABLE audit_logs RESTART IDENTITY"))
    else:
        session.execute(delete(AuditLog))


def _seed_enterprise_dataset(
    session: Session, settings: Settings, *, products_only: bool = False
) -> GenerationArtifacts:
    counts: Counter[str] = Counter()
    logins: list[LoginRecord] = []
    notes: list[str] = []

    firm_service = FirmService(session)
    framework_service = BusinessProfileFrameworkService(session)
    branch_service = BranchWarehouseService(session)
    territory_service = SalesTerritoryService(session)
    vendor_service = VendorService(session)
    customer_service = CustomerService(session)
    product_service = ProductService(session)
    tax_service = TaxFrameworkService(session)
    tax_rule_service = TaxRuleService(session)
    identity = IdentityService(session, settings)

    identity_module: Any = importlib.import_module(
        "app.identity.services.identity_service"
    )
    original_validate_password_policy = identity_module.validate_password_policy
    identity_module.validate_password_policy = _allow_dev_password
    try:
        business_profiles = _resolve_profiles(session)
        geography = _seed_geography(territory_service)
        firms = _create_firms(firm_service, framework_service, business_profiles)
        counts["firms"] = len(firms)

        admin_user = _ensure_superadmin(session, identity, settings)
        logins.append(
            LoginRecord(
                username=admin_user.email,
                role="PLATFORM_ADMIN",
                firm="All Firms",
                branch="All Branches",
                description="Primary development super administrator with full "
                "platform access.",
            )
        )

        contexts: list[FirmContext] = []
        for blueprint in FIRM_BLUEPRINTS:
            firm = firms[blueprint["key"]]
            profile = business_profiles[
                _first_existing_profile_code(
                    business_profiles, blueprint["profile_codes"]
                )
            ]
            branch_types = _seed_branch_types(branch_service, firm.id)
            warehouse_types = _seed_warehouse_types(branch_service, firm.id)
            branches, warehouses = _seed_branches_and_warehouses(
                branch_service=branch_service,
                geography=geography,
                firm=firm,
                profile=profile,
                blueprint=blueprint,
                branch_types=branch_types,
                warehouse_types=warehouse_types,
                actor_id=admin_user.id,
            )
            route_types, route_leaf_ids = _seed_territories(
                territory_service=territory_service,
                geography=geography,
                firm=firm,
                profile=profile,
                blueprint=blueprint,
                actor_id=admin_user.id,
            )
            tax_profiles = _seed_tax_framework(
                tax_service=tax_service,
                tax_rule_service=tax_rule_service,
                country_id=geography["country"].id,
                firm=firm,
                profile=profile,
                actor_id=admin_user.id,
            )
            product_categories = _seed_product_categories(
                product_service=product_service,
                firm=firm,
                actor_id=admin_user.id,
            )
            contexts.append(
                FirmContext(
                    key=blueprint["key"],
                    firm=firm,
                    profile=profile,
                    branches=branches,
                    warehouses=warehouses,
                    route_types=route_types,
                    route_leaf_ids=route_leaf_ids,
                    primary_routes=route_leaf_ids,
                    tax_profiles=tax_profiles,
                    product_categories=product_categories,
                    salesmen=[],
                    branch_by_name={branch.name: branch for branch in branches},
                    warehouse_by_name={
                        warehouse.name: warehouse for warehouse in warehouses
                    },
                )
            )

        user_roles = _resolve_roles(session)
        created_users = _seed_users(
            session=session,
            identity=identity,
            admin_user=admin_user,
            contexts=contexts,
            user_roles=user_roles,
            logins=logins,
        )
        counts["users"] = len(logins)

        for context in contexts:
            _assign_branch_and_warehouse_managers(
                session=session,
                context=context,
                actor_id=admin_user.id,
                created_users=created_users,
            )

        counts["branches"] = sum(len(context.branches) for context in contexts)
        counts["warehouses"] = sum(len(context.warehouses) for context in contexts)
        counts["route_types"] = sum(len(context.route_types) for context in contexts)
        counts["routes"] = sum(len(context.route_leaf_ids) for context in contexts)
        counts["territories"] = _count_active(session, SalesTerritoryNode)
        counts["tax_profiles"] = sum(len(context.tax_profiles) for context in contexts)
        counts["tax_rules"] = _count_active(session, TaxRule)

        vendors_by_firm = _seed_vendors(
            vendor_service=vendor_service,
            geography=geography,
            contexts=contexts,
            actor_id=admin_user.id,
        )
        counts["vendors"] = sum(len(items) for items in vendors_by_firm.values())

        products_by_firm = _seed_products(
            session=session,
            product_service=product_service,
            contexts=contexts,
            vendors_by_firm=vendors_by_firm,
            actor_id=admin_user.id,
            notes=notes,
        )
        counts["products"] = sum(len(items) for items in products_by_firm.values())
        counts["categories"] = _count_active(session, ProductCategory)
        if products_only:
            counts["tax_systems"] = _count_active(session, TaxSystem)
            counts["tax_components"] = _count_active(session, TaxComponent)
            notes.append(
                "Product-only mode seeded firms, users, tax, vendors, categories, and "
                "products."
            )
            return GenerationArtifacts(counts=counts, logins=logins, notes=notes)

        customers_by_firm = _seed_customers(
            customer_service=customer_service,
            contexts=contexts,
            geography=geography,
            actor_id=admin_user.id,
        )
        counts["customers"] = sum(len(items) for items in customers_by_firm.values())

        _assign_routes(
            territory_service=territory_service,
            contexts=contexts,
            customers_by_firm=customers_by_firm,
            created_users=created_users,
            actor_id=admin_user.id,
        )
        counts["storage_nodes"] = _count_active(session, WarehouseStorageNode)

        operational_counts = _seed_uom_inventory_and_documents(
            session=session,
            contexts=contexts,
            products_by_firm=products_by_firm,
            vendors_by_firm=vendors_by_firm,
            customers_by_firm=customers_by_firm,
            created_users=created_users,
            actor_id=admin_user.id,
        )
        counts.update(operational_counts)

        execution_logs = _run_tax_simulations(
            tax_rule_service=tax_rule_service,
            geography=geography,
            contexts=contexts,
            customers_by_firm=customers_by_firm,
            vendors_by_firm=vendors_by_firm,
            products_by_firm=products_by_firm,
            actor_id=admin_user.id,
        )
        counts["tax_execution_logs"] = execution_logs
        counts["tax_systems"] = _count_active(session, TaxSystem)
        counts["tax_components"] = _count_active(session, TaxComponent)

        notes.append(
            "Preferred vendor and default warehouse are recorded in product remarks "
            "because the current product schema does not yet expose first-class "
            "relationship tables for those assignments."
        )
        return GenerationArtifacts(counts=counts, logins=logins, notes=notes)
    finally:
        identity_module.validate_password_policy = original_validate_password_policy


def _resolve_profiles(session: Session) -> dict[str, BusinessProfile]:
    profiles = {
        profile.code.upper(): profile
        for profile in session.scalars(
            select(BusinessProfile).where(
                BusinessProfile.is_deleted.is_(False),
                BusinessProfile.status == "ACTIVE",
            )
        ).all()
    }
    if "GENERIC" not in profiles:
        raise RuntimeError("Business profile metadata is missing the GENERIC profile.")
    return profiles


def _seed_geography(service: SalesTerritoryService) -> dict[str, Any]:
    country = _ensure_country(service)
    state_map: dict[str, Any] = {}
    city_map: dict[tuple[str, str], Any] = {}
    locality_map: dict[tuple[str, str], Any] = {}
    postal_map: dict[tuple[str, str], Any] = {}
    district_map: dict[tuple[str, str], Any] = {}
    for state_name, state_data in GEO_BLUEPRINT.items():
        state = _ensure_state(service, country.id, state_data["code"], state_name)
        state_map[state_name] = state
        for district_name, district_data in state_data["districts"].items():
            district = _ensure_district(
                service,
                state.id,
                district_data["code"],
                district_name,
            )
            district_map[(state_name, district_name)] = district
            for city_name, city_data in district_data["cities"].items():
                city = _ensure_city(
                    service,
                    district.id,
                    city_data["code"],
                    city_name,
                )
                city_map[(state_name, city_name)] = city
                for postal_code, localities in city_data["postal_codes"].items():
                    postal = _ensure_postal_code(service, city.id, postal_code)
                    postal_map[(state_name, postal_code)] = postal
                    for locality_name in localities:
                        locality = _ensure_locality(service, postal.id, locality_name)
                        locality_map[(city_name, locality_name)] = locality
    return {
        "country": country,
        "states": state_map,
        "districts": district_map,
        "cities": city_map,
        "postal_codes": postal_map,
        "localities": locality_map,
    }


def _ensure_country(service: SalesTerritoryService) -> GeoCountry:
    session = service._session  # noqa: SLF001
    existing = session.scalar(
        select(GeoCountry).where(
            GeoCountry.code == INDIA_CODE,
            GeoCountry.is_deleted.is_(False),
        )
    )
    if existing is not None:
        return existing
    return service.create_country(
        GeoCountryWrite(
            code=INDIA_CODE,
            name="India",
            iso2="IN",
            iso3="IND",
            phone_code="+91",
            is_active=True,
        ),
        actor_id=SYSTEM_ACTOR_ID,
    )


def _ensure_state(
    service: SalesTerritoryService, country_id: UUID, code: str, name: str
) -> GeoState:
    session = service._session  # noqa: SLF001
    existing = session.scalar(
        select(GeoState).where(
            GeoState.country_id == country_id,
            GeoState.code == code,
            GeoState.is_deleted.is_(False),
        )
    )
    if existing is not None:
        return existing
    return service.create_state(
        GeoStateWrite(
            country_id=country_id,
            code=code,
            name=name,
            is_active=True,
        ),
        actor_id=SYSTEM_ACTOR_ID,
    )


def _ensure_district(
    service: SalesTerritoryService, state_id: UUID, code: str, name: str
) -> GeoDistrict:
    session = service._session  # noqa: SLF001
    existing = session.scalar(
        select(GeoDistrict).where(
            GeoDistrict.state_id == state_id,
            GeoDistrict.code == code,
            GeoDistrict.is_deleted.is_(False),
        )
    )
    if existing is not None:
        return existing
    return service.create_district(
        GeoDistrictWrite(
            state_id=state_id,
            code=code,
            name=name,
            is_active=True,
        ),
        actor_id=SYSTEM_ACTOR_ID,
    )


def _ensure_city(
    service: SalesTerritoryService, district_id: UUID, code: str, name: str
) -> GeoCity:
    session = service._session  # noqa: SLF001
    existing = session.scalar(
        select(GeoCity).where(
            GeoCity.district_id == district_id,
            GeoCity.code == code,
            GeoCity.is_deleted.is_(False),
        )
    )
    if existing is not None:
        return existing
    return service.create_city(
        GeoCityWrite(
            district_id=district_id,
            code=code,
            name=name,
            is_active=True,
        ),
        actor_id=SYSTEM_ACTOR_ID,
    )


def _ensure_postal_code(
    service: SalesTerritoryService, city_id: UUID, postal_code: str
) -> GeoPostalCode:
    session = service._session  # noqa: SLF001
    existing = session.scalar(
        select(GeoPostalCode).where(
            GeoPostalCode.city_id == city_id,
            GeoPostalCode.postal_code == postal_code,
            GeoPostalCode.is_deleted.is_(False),
        )
    )
    if existing is not None:
        return existing
    return service.create_postal_code(
        GeoPostalCodeWrite(
            city_id=city_id,
            postal_code=postal_code,
            is_active=True,
        ),
        actor_id=SYSTEM_ACTOR_ID,
    )


def _ensure_locality(
    service: SalesTerritoryService, postal_code_id: UUID, name: str
) -> GeoLocality:
    session = service._session  # noqa: SLF001
    existing = session.scalar(
        select(GeoLocality).where(
            GeoLocality.postal_code_id == postal_code_id,
            GeoLocality.name == name,
            GeoLocality.is_deleted.is_(False),
        )
    )
    if existing is not None:
        return existing
    return service.create_locality(
        GeoLocalityWrite(
            postal_code_id=postal_code_id,
            name=name,
            is_active=True,
        ),
        actor_id=SYSTEM_ACTOR_ID,
    )


def _create_firms(
    firm_service: FirmService,
    framework_service: BusinessProfileFrameworkService,
    business_profiles: dict[str, BusinessProfile],
) -> dict[str, Firm]:
    result: dict[str, Firm] = {}
    for index, blueprint in enumerate(FIRM_BLUEPRINTS, start=1):
        firm = firm_service.create(
            FirmCreate(
                name=blueprint["name"],
                code=blueprint["code"],
                gst_number=_gstin(index, blueprint["state"]),
                pan_number=_pan(index),
                address_line1=f"{index * 12} Enterprise Park",
                city=blueprint["city"],
                postal_code=blueprint["postal_code"],
                country=INDIA_CODE,
                state=blueprint["state"],
                contact_name="Operations Desk",
                contact_email=f"ops@{_slug(blueprint['name'])}.local",
                contact_phone=_phone(index),
                currency_code="INR",
                financial_year_start=date(2025, 4, 1),
                notes=blueprint["notes"],
            ),
            actor_id=SYSTEM_ACTOR_ID,
        )
        profile = business_profiles[
            _first_existing_profile_code(business_profiles, blueprint["profile_codes"])
        ]
        framework_service.assign_profile_to_firm(
            firm.id,
            FirmBusinessProfileAssign(
                business_profile_id=profile.id,
                is_active=True,
                notes=f"Seeded for {profile.code} development flows.",
            ),
            SYSTEM_ACTOR_ID,
        )
        result[blueprint["key"]] = firm
    return result


def _seed_branch_types(
    service: BranchWarehouseService, firm_id: UUID
) -> dict[str, BranchType]:
    blueprints = (
        ("HEAD_OFFICE", "Head Office"),
        ("CITY_BRANCH", "City Branch"),
        ("DISTRIBUTION_BRANCH", "Distribution Branch"),
    )
    result: dict[str, BranchType] = {}
    for code, name in blueprints:
        result[code] = service.create_branch_type(
            BranchTypeWrite(
                code=code,
                name=name,
                description=f"Development seed {name.lower()} classification.",
                is_active=True,
            ),
            firm_id=firm_id,
            actor_id=SYSTEM_ACTOR_ID,
        )
    return result


def _seed_warehouse_types(
    service: BranchWarehouseService, firm_id: UUID
) -> dict[str, WarehouseType]:
    blueprints = (
        ("MAIN", "Main Warehouse"),
        ("COLD", "Cold Storage"),
        ("RETURNS", "Returns Warehouse"),
        ("FINISHED_GOODS", "Finished Goods Warehouse"),
    )
    result: dict[str, WarehouseType] = {}
    for code, name in blueprints:
        result[code] = service.create_warehouse_type(
            WarehouseTypeWrite(
                code=code,
                name=name,
                description=f"Development seed {name.lower()} classification.",
                is_active=True,
            ),
            firm_id=firm_id,
            actor_id=SYSTEM_ACTOR_ID,
        )
    return result


def _seed_branches_and_warehouses(
    *,
    branch_service: BranchWarehouseService,
    geography: dict[str, Any],
    firm: Firm,
    profile: BusinessProfile,
    blueprint: dict[str, Any],
    branch_types: dict[str, BranchType],
    warehouse_types: dict[str, WarehouseType],
    actor_id: UUID,
) -> tuple[list[Branch], list[Warehouse]]:
    branches: list[Branch] = []
    warehouses: list[Warehouse] = []
    for branch_index, (branch_code, branch_name, city_name, state_name) in enumerate(
        blueprint["branches"], start=1
    ):
        geo = _geo_for_city(geography, state_name, city_name)
        branch_type_code = "HEAD_OFFICE" if branch_index == 1 else "DISTRIBUTION_BRANCH"
        branch = branch_service.create_branch(
            BranchCreate(
                code=branch_code,
                name=branch_name,
                display_name=branch_name,
                description=f"{branch_name} for {firm.name}.",
                business_profile_id=profile.id,
                branch_type_id=branch_types[branch_type_code].id,
                branch_manager_id=None,
                email=f"{_slug(branch_name)}@{_slug(firm.name)}.local",
                phone=_phone(branch_index + 20),
                mobile=_phone(branch_index + 200),
                country_id=geography["country"].id,
                state_id=geo["state"].id,
                district_id=geo["district"].id,
                city_id=geo["city"].id,
                postal_code_id=geo["postal"].id,
                locality_id=geo["locality"].id,
                address_line1=(
                    f"{branch_index * 18} {geo['locality'].name} " "Industrial Estate"
                ),
                address_line2="Enterprise Block",
                timezone="Asia/Kolkata",
                currency_code="INR",
                gst_registration=True,
                pan=_pan(branch_index + 50),
                license_number=f"LIC-{branch_code}",
                working_hours={
                    "monday": "09:00-18:00",
                    "tuesday": "09:00-18:00",
                    "wednesday": "09:00-18:00",
                    "thursday": "09:00-18:00",
                    "friday": "09:00-18:00",
                    "saturday": "09:00-16:00",
                },
                is_default=branch_index == 1,
                status=BranchStatus.ACTIVE,
            ),
            firm_id=firm.id,
            actor_id=actor_id,
        )
        branches.append(branch)

        for warehouse_position, (warehouse_code, warehouse_name) in enumerate(
            blueprint["warehouses"], start=1
        ):
            warehouse_type_code = "COLD" if "cold" in warehouse_name.lower() else "MAIN"
            if "finished" in warehouse_name.lower():
                warehouse_type_code = "FINISHED_GOODS"
            if "returns" in warehouse_name.lower():
                warehouse_type_code = "RETURNS"
            warehouse = branch_service.create_warehouse(
                WarehouseCreate(
                    branch_id=branch.id,
                    code=f"{branch_code}_{warehouse_code}",
                    name=warehouse_name,
                    display_name=f"{branch_name} {warehouse_name}",
                    description=f"{warehouse_name} at {branch_name}.",
                    warehouse_type_id=warehouse_types[warehouse_type_code].id,
                    warehouse_manager_id=None,
                    business_profile_id=profile.id,
                    country_id=geography["country"].id,
                    state_id=geo["state"].id,
                    district_id=geo["district"].id,
                    city_id=geo["city"].id,
                    postal_code_id=geo["postal"].id,
                    locality_id=geo["locality"].id,
                    address_line1=f"{warehouse_position * 5} Warehouse Avenue",
                    address_line2=geo["locality"].name,
                    capacity=Decimal("15000") + Decimal(warehouse_position * 2500),
                    capacity_unit="PCS",
                    is_default=warehouse_position == 1,
                    temperature_controlled="cold" in warehouse_name.lower(),
                    cold_storage="cold" in warehouse_name.lower(),
                    hazardous_storage=False,
                    has_receiving_area=True,
                    has_dispatch_area=True,
                    has_returns_area="returns" in warehouse_name.lower(),
                    has_inspection_area=True,
                    has_packing_area=True,
                    has_loading_dock=True,
                    status=WarehouseStatus.ACTIVE,
                ),
                firm_id=firm.id,
                actor_id=actor_id,
            )
            warehouses.append(warehouse)
            _seed_storage_hierarchy(branch_service, warehouse, actor_id)
    return branches, warehouses


def _seed_storage_hierarchy(
    service: BranchWarehouseService, warehouse: Warehouse, actor_id: UUID
) -> None:
    areas = [
        ("RECV", "Receiving Area", StorageNodeType.RECEIVING_AREA),
        ("A", "Area A", StorageNodeType.STORAGE_AREA),
        ("B", "Area B", StorageNodeType.STORAGE_AREA),
    ]
    for area_order, (area_code, area_name, area_type) in enumerate(areas, start=1):
        area = service.create_storage_node(
            StorageNodeCreate(
                warehouse_id=warehouse.id,
                parent_id=None,
                node_type=area_type,
                code=area_code,
                name=area_name,
                description=f"{area_name} for {warehouse.name}.",
                sort_order=area_order,
                is_active=True,
            ),
            firm_scope=warehouse.firm_id,
            actor_id=actor_id,
        )
        if area_type == StorageNodeType.RECEIVING_AREA:
            continue
        for rack_index in range(1, 3):
            rack = service.create_storage_node(
                StorageNodeCreate(
                    warehouse_id=warehouse.id,
                    parent_id=area.id,
                    node_type=StorageNodeType.RACK,
                    code=f"{area_code}R{rack_index}",
                    name=f"Rack {rack_index}",
                    description=None,
                    sort_order=rack_index,
                    is_active=True,
                ),
                firm_scope=warehouse.firm_id,
                actor_id=actor_id,
            )
            for shelf_index in range(1, 3):
                shelf = service.create_storage_node(
                    StorageNodeCreate(
                        warehouse_id=warehouse.id,
                        parent_id=rack.id,
                        node_type=StorageNodeType.SHELF,
                        code=f"{area_code}R{rack_index}S{shelf_index}",
                        name=f"Shelf {shelf_index}",
                        description=None,
                        sort_order=shelf_index,
                        is_active=True,
                    ),
                    firm_scope=warehouse.firm_id,
                    actor_id=actor_id,
                )
                for bin_index in range(1, 4):
                    service.create_storage_node(
                        StorageNodeCreate(
                            warehouse_id=warehouse.id,
                            parent_id=shelf.id,
                            node_type=StorageNodeType.BIN,
                            code=f"{area_code}R{rack_index}S{shelf_index}B{bin_index}",
                            name=f"Bin {bin_index}",
                            description=None,
                            sort_order=bin_index,
                            is_active=True,
                        ),
                        firm_scope=warehouse.firm_id,
                        actor_id=actor_id,
                    )


def _seed_territories(
    *,
    territory_service: SalesTerritoryService,
    geography: dict[str, Any],
    firm: Firm,
    profile: BusinessProfile,
    blueprint: dict[str, Any],
    actor_id: UUID,
) -> tuple[dict[str, Any], list[UUID]]:
    hierarchy = territory_service.update_hierarchy(
        firm_scope=firm.id,
        actor_id=actor_id,
        payload=HierarchyUpdateRequest(
            max_levels=4,
            allow_multi_route_per_salesman=True,
            allow_multi_salesman_per_route=True,
            enforce_customer_leaf_assignment=True,
            levels=[
                HierarchyLevelInput(
                    level_order=1,
                    level_code="STATE",
                    display_name="State",
                    description="State level coverage",
                    is_mandatory=True,
                    is_enabled=True,
                ),
                HierarchyLevelInput(
                    level_order=2,
                    level_code="CITY",
                    display_name="City",
                    description="City level coverage",
                    is_mandatory=True,
                    is_enabled=True,
                ),
                HierarchyLevelInput(
                    level_order=3,
                    level_code="CIRCLE",
                    display_name="Circle",
                    description="Circle level coverage",
                    is_mandatory=True,
                    is_enabled=True,
                ),
                HierarchyLevelInput(
                    level_order=4,
                    level_code="ROUTE",
                    display_name="Route",
                    description="Leaf route coverage",
                    is_mandatory=True,
                    is_enabled=True,
                ),
            ],
        ),
    )
    level_ids = {level.level_code: level.id for level in hierarchy.levels}
    route_types: dict[str, Any] = {}
    for _index, route_type_name in enumerate(
        ("Sales", "Delivery", "Collection", "Service", "Survey"), start=1
    ):
        row = territory_service.create_route_type(
            RouteTypeWrite(
                code=route_type_name.upper(),
                name=route_type_name,
                description=f"{route_type_name} route for development coverage.",
                is_active=True,
            ),
            firm_scope=firm.id,
            actor_id=actor_id,
        )
        route_types[row.code] = row

    leaf_ids: list[UUID] = []
    state_counter = 1
    for state_name in blueprint["territory_states"]:
        geography["states"][state_name]
        state_node = territory_service.create_territory(
            TerritoryCreate(
                code=f"{firm.code[:4]}ST{state_counter}",
                name=state_name,
                hierarchy_level_id=level_ids["STATE"],
                parent_id=None,
                description=f"{state_name} state coverage for {firm.name}.",
                status=TerritoryStatus.ACTIVE,
                sort_order=state_counter,
                route_profile=None,
            ),
            firm_scope=firm.id,
            actor_id=actor_id,
        )
        cities_for_state = [
            city_name
            for key_state, city_name in geography["cities"]
            if key_state == state_name
        ][:2]
        for city_counter, city_name in enumerate(cities_for_state, start=1):
            city_node = territory_service.create_territory(
                TerritoryCreate(
                    code=f"{state_node.code}C{city_counter}",
                    name=city_name,
                    hierarchy_level_id=level_ids["CITY"],
                    parent_id=state_node.id,
                    description=f"{city_name} city coverage for {firm.name}.",
                    status=TerritoryStatus.ACTIVE,
                    sort_order=city_counter,
                    route_profile=None,
                ),
                firm_scope=firm.id,
                actor_id=actor_id,
            )
            geo = _geo_for_city(geography, state_name, city_name)
            for circle_counter, locality_name in enumerate(
                list(
                    locality.name
                    for (locality_city, _), locality in geography["localities"].items()
                    if locality_city == city_name
                )[:2],
                start=1,
            ):
                circle_node = territory_service.create_territory(
                    TerritoryCreate(
                        code=f"{city_node.code}R{circle_counter}",
                        name=f"{locality_name} Circle",
                        hierarchy_level_id=level_ids["CIRCLE"],
                        parent_id=city_node.id,
                        description=f"{locality_name} circle for {city_name}.",
                        status=TerritoryStatus.ACTIVE,
                        sort_order=circle_counter,
                        route_profile=None,
                    ),
                    firm_scope=firm.id,
                    actor_id=actor_id,
                )
                for route_counter in range(1, 3):
                    route_type_code = blueprint["route_type_pattern"][
                        (route_counter + circle_counter + city_counter)
                        % len(blueprint["route_type_pattern"])
                    ]
                    locality_candidates = [
                        item
                        for (locality_city, _), item in geography["localities"].items()
                        if locality_city == city_name
                    ]
                    locality = locality_candidates[
                        (route_counter - 1) % len(locality_candidates)
                    ]
                    route = territory_service.create_territory(
                        TerritoryCreate(
                            code=f"{circle_node.code}T{route_counter}",
                            name=f"{city_name} Route "
                            f"{route_counter + (circle_counter - 1) * 2}",
                            hierarchy_level_id=level_ids["ROUTE"],
                            parent_id=circle_node.id,
                            description=f"{route_type_code.title()} route for "
                            f"{city_name}.",
                            status=TerritoryStatus.ACTIVE,
                            sort_order=route_counter,
                            route_profile=RouteProfileInput(
                                route_type_id=route_types[route_type_code].id,
                                visit_frequency=VisitFrequency.WEEKLY,
                                effective_from=date(2025, 4, 1),
                                effective_to=None,
                                city_id=geo["city"].id,
                                postal_code_id=geo["postal"].id,
                                locality_id=locality.id,
                                working_days=[1, 3, 5],
                            ),
                        ),
                        firm_scope=firm.id,
                        actor_id=actor_id,
                    )
                    leaf_ids.append(route.id)
        state_counter += 1
    return route_types, leaf_ids


def _seed_tax_framework(
    *,
    tax_service: TaxFrameworkService,
    tax_rule_service: TaxRuleService,
    country_id: UUID,
    firm: Firm,
    profile: BusinessProfile,
    actor_id: UUID,
) -> dict[str, TaxProfile]:
    tax_service.update_settings(
        TaxSettingsWrite(
            primary_label="Tax",
            component_label="Component",
            profile_label="Profile",
            report_label="Tax",
            allow_mixed_historical=True,
            additional_settings={"country_mode": "independent", "seeded": True},
        ),
        firm_scope=firm.id,
        actor_id=actor_id,
    )
    gst_system = tax_service.create_system(
        TaxSystemWrite(
            country_id=country_id,
            business_profile_id=profile.id,
            code="GST",
            name="Goods and Services Tax",
            display_name="GST",
            description="Development GST configuration.",
            status=TaxStatus.ACTIVE,
            display_order=10,
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    legacy_system = tax_service.create_system(
        TaxSystemWrite(
            country_id=country_id,
            business_profile_id=profile.id,
            code="LEGACY",
            name="Legacy Tax",
            display_name="Legacy Tax",
            description="Historical tax configuration retained for migration "
            "scenarios.",
            status=TaxStatus.ACTIVE,
            display_order=20,
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    gst_components = {
        "CGST": tax_service.create_component(
            TaxComponentWrite(
                tax_system_id=gst_system.id,
                code="CGST",
                name="Central GST",
                label="CGST",
                short_label="CGST",
                display_order=1,
                calculation_order=1,
                percentage=Decimal("0"),
                included_in_price=False,
                recoverable=True,
                status=TaxStatus.ACTIVE,
            ),
            firm_id=firm.id,
            actor_id=actor_id,
        ),
        "SGST": tax_service.create_component(
            TaxComponentWrite(
                tax_system_id=gst_system.id,
                code="SGST",
                name="State GST",
                label="SGST",
                short_label="SGST",
                display_order=2,
                calculation_order=2,
                percentage=Decimal("0"),
                included_in_price=False,
                recoverable=True,
                status=TaxStatus.ACTIVE,
            ),
            firm_id=firm.id,
            actor_id=actor_id,
        ),
        "IGST": tax_service.create_component(
            TaxComponentWrite(
                tax_system_id=gst_system.id,
                code="IGST",
                name="Integrated GST",
                label="IGST",
                short_label="IGST",
                display_order=3,
                calculation_order=3,
                percentage=Decimal("0"),
                included_in_price=False,
                recoverable=True,
                status=TaxStatus.ACTIVE,
            ),
            firm_id=firm.id,
            actor_id=actor_id,
        ),
        "CESS": tax_service.create_component(
            TaxComponentWrite(
                tax_system_id=gst_system.id,
                code="CESS",
                name="Compensation Cess",
                label="CESS",
                short_label="CESS",
                display_order=4,
                calculation_order=4,
                percentage=Decimal("0"),
                included_in_price=False,
                recoverable=False,
                status=TaxStatus.ACTIVE,
            ),
            firm_id=firm.id,
            actor_id=actor_id,
        ),
    }
    legacy_components = {
        "SALES_TAX": tax_service.create_component(
            TaxComponentWrite(
                tax_system_id=legacy_system.id,
                code="SALES_TAX",
                name="Sales Tax",
                label="Sales Tax",
                short_label="ST",
                display_order=1,
                calculation_order=1,
                percentage=Decimal("0"),
                included_in_price=False,
                recoverable=False,
                status=TaxStatus.ACTIVE,
            ),
            firm_id=firm.id,
            actor_id=actor_id,
        ),
        "VAT": tax_service.create_component(
            TaxComponentWrite(
                tax_system_id=legacy_system.id,
                code="VAT",
                name="Value Added Tax",
                label="VAT",
                short_label="VAT",
                display_order=2,
                calculation_order=2,
                percentage=Decimal("0"),
                included_in_price=False,
                recoverable=False,
                status=TaxStatus.ACTIVE,
            ),
            firm_id=firm.id,
            actor_id=actor_id,
        ),
        "SERVICE_TAX": tax_service.create_component(
            TaxComponentWrite(
                tax_system_id=legacy_system.id,
                code="SERVICE_TAX",
                name="Service Tax",
                label="Service Tax",
                short_label="STX",
                display_order=3,
                calculation_order=3,
                percentage=Decimal("0"),
                included_in_price=False,
                recoverable=False,
                status=TaxStatus.ACTIVE,
            ),
            firm_id=firm.id,
            actor_id=actor_id,
        ),
        "LEGACY_TAX": tax_service.create_component(
            TaxComponentWrite(
                tax_system_id=legacy_system.id,
                code="LEGACY_TAX",
                name="Legacy Tax",
                label="Legacy Tax",
                short_label="LTX",
                display_order=4,
                calculation_order=4,
                percentage=Decimal("0"),
                included_in_price=False,
                recoverable=False,
                status=TaxStatus.ACTIVE,
            ),
            firm_id=firm.id,
            actor_id=actor_id,
        ),
    }
    tax_service.create_country_mapping(
        TaxCountryMappingWrite(
            country_id=country_id,
            business_profile_id=profile.id,
            tax_system_id=gst_system.id,
            status=TaxStatus.ACTIVE,
            is_default=True,
            effective_from=date(2017, 7, 1),
            effective_to=None,
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )

    profiles: dict[str, TaxProfile] = {}
    profile_definitions = (
        (
            "GST_5",
            "GST 5%",
            gst_system.id,
            False,
            date(2017, 7, 1),
            None,
            [
                ("CGST", Decimal("2.5")),
                ("SGST", Decimal("2.5")),
            ],
        ),
        (
            "GST_12",
            "GST 12%",
            gst_system.id,
            False,
            date(2017, 7, 1),
            None,
            [
                ("CGST", Decimal("6")),
                ("SGST", Decimal("6")),
            ],
        ),
        (
            "GST_18",
            "GST 18%",
            gst_system.id,
            False,
            date(2017, 7, 1),
            None,
            [
                ("CGST", Decimal("9")),
                ("SGST", Decimal("9")),
            ],
        ),
        (
            "GST_28",
            "GST 28%",
            gst_system.id,
            False,
            date(2017, 7, 1),
            None,
            [
                ("CGST", Decimal("14")),
                ("SGST", Decimal("14")),
            ],
        ),
        (
            "ZERO_RATED",
            "Zero Rated",
            gst_system.id,
            False,
            date(2017, 7, 1),
            None,
            [("IGST", Decimal("0"))],
        ),
        (
            "EXEMPT",
            "Exempt",
            gst_system.id,
            False,
            date(2017, 7, 1),
            None,
            [],
        ),
        (
            "HIST_SALES_12",
            "Historical Sales Tax 12%",
            legacy_system.id,
            True,
            date(2014, 4, 1),
            date(2017, 6, 30),
            [("SALES_TAX", Decimal("12"))],
        ),
        (
            "HIST_VAT_4",
            "Historical VAT 4%",
            legacy_system.id,
            True,
            date(2013, 4, 1),
            date(2017, 6, 30),
            [("VAT", Decimal("4"))],
        ),
        (
            "HIST_SERVICE_15",
            "Historical Service Tax 15%",
            legacy_system.id,
            True,
            date(2015, 6, 1),
            date(2017, 6, 30),
            [("SERVICE_TAX", Decimal("15"))],
        ),
        (
            "LEGACY_8",
            "Legacy Tax 8%",
            legacy_system.id,
            True,
            date(2013, 4, 1),
            date(2016, 3, 31),
            [("LEGACY_TAX", Decimal("8"))],
        ),
    )
    for order, definition in enumerate(profile_definitions, start=1):
        code, name, system_id, historical, effective_from, effective_to, components = (
            definition
        )
        component_map = (
            gst_components if system_id == gst_system.id else legacy_components
        )
        profiles[code] = tax_service.create_profile(
            TaxProfileWrite(
                tax_system_id=system_id,
                business_profile_id=profile.id,
                code=code,
                name=name,
                label=name,
                description=f"{name} profile for development data.",
                status=TaxStatus.ACTIVE,
                display_order=order,
                is_historical=historical,
                effective_from=effective_from,
                effective_to=effective_to,
                components=[
                    TaxProfileComponentInput(
                        tax_component_id=component_map[component_code].id,
                        label=component_code,
                        short_label=component_code,
                        calculation_order=component_index,
                        percentage=percentage,
                        included_in_price=False,
                        recoverable=not historical,
                    )
                    for component_index, (component_code, percentage) in enumerate(
                        components, start=1
                    )
                ],
            ),
            firm_id=firm.id,
            actor_id=actor_id,
        )

    for code, name, rate in (
        ("VAT_4", "Legacy VAT 4%", Decimal("4")),
        ("SALES_12", "Historical Sales Tax 12%", Decimal("12")),
        ("SERVICE_15", "Historical Service Tax 15%", Decimal("15")),
    ):
        target = {
            "VAT_4": profiles["HIST_VAT_4"],
            "SALES_12": profiles["HIST_SALES_12"],
            "SERVICE_15": profiles["HIST_SERVICE_15"],
        }[code]
        tax_service.create_migration_mapping(
            TaxMigrationMappingWrite(
                legacy_tax_code=code,
                legacy_tax_name=name,
                source_system="ERP_LEGACY",
                legacy_rate=rate,
                target_tax_profile_id=target.id,
                keep_historical=True,
                status=TaxStatus.ACTIVE,
                notes="Seeded migration reference.",
            ),
            firm_id=firm.id,
            actor_id=actor_id,
        )

    _seed_tax_rules(
        tax_rule_service, country_id, firm.id, profile.id, profiles, actor_id
    )
    return profiles


def _seed_tax_rules(
    service: TaxRuleService,
    country_id: UUID,
    firm_id: UUID,
    profile_id: UUID,
    profiles: dict[str, TaxProfile],
    actor_id: UUID,
) -> None:
    rule_definitions = (
        (
            "EXPORT_ZERO",
            "Export zero rated",
            1,
            [
                (
                    "transaction_type",
                    TaxRuleConditionOperator.EQUALS,
                    "EXPORT",
                    None,
                    None,
                )
            ],
            [TaxRuleActionWrite(sequence=1, action_type=TaxRuleActionType.ZERO_RATED)],
        ),
        (
            "EXPORT_PROFILE",
            "Export profile override",
            2,
            [
                (
                    "transaction_type",
                    TaxRuleConditionOperator.EQUALS,
                    "EXPORT",
                    None,
                    None,
                )
            ],
            [
                TaxRuleActionWrite(
                    sequence=1,
                    action_type=TaxRuleActionType.APPLY_TAX_PROFILE,
                    target_tax_profile_id=profiles["ZERO_RATED"].id,
                )
            ],
        ),
        (
            "SALES_EXEMPT",
            "Exempt profile passthrough",
            3,
            [
                (
                    "tax_profile_id",
                    TaxRuleConditionOperator.EQUALS,
                    str(profiles["EXEMPT"].id),
                    None,
                    None,
                )
            ],
            [TaxRuleActionWrite(sequence=1, action_type=TaxRuleActionType.EXEMPT_TAX)],
        ),
        (
            "SALES_ZERO",
            "Zero profile passthrough",
            4,
            [
                (
                    "tax_profile_id",
                    TaxRuleConditionOperator.EQUALS,
                    str(profiles["ZERO_RATED"].id),
                    None,
                    None,
                )
            ],
            [TaxRuleActionWrite(sequence=1, action_type=TaxRuleActionType.ZERO_RATED)],
        ),
        (
            "HIGH_VALUE_28",
            "High value sale uses luxury band",
            5,
            [
                (
                    "invoice_value",
                    TaxRuleConditionOperator.GREATER_OR_EQUAL,
                    None,
                    Decimal("50000"),
                    None,
                )
            ],
            [
                TaxRuleActionWrite(
                    sequence=1,
                    action_type=TaxRuleActionType.APPLY_TAX_PROFILE,
                    target_tax_profile_id=profiles["GST_28"].id,
                )
            ],
        ),
        (
            "MEDICAL_STANDARD",
            "Medical standard taxation",
            10,
            [
                (
                    "tax_profile_id",
                    TaxRuleConditionOperator.EQUALS,
                    str(profiles["GST_12"].id),
                    None,
                    None,
                )
            ],
            [
                TaxRuleActionWrite(
                    sequence=1,
                    action_type=TaxRuleActionType.APPLY_TAX_PROFILE,
                    target_tax_profile_id=profiles["GST_12"].id,
                )
            ],
        ),
        (
            "FOOD_STANDARD",
            "Food standard taxation",
            11,
            [
                (
                    "tax_profile_id",
                    TaxRuleConditionOperator.EQUALS,
                    str(profiles["GST_5"].id),
                    None,
                    None,
                )
            ],
            [
                TaxRuleActionWrite(
                    sequence=1,
                    action_type=TaxRuleActionType.APPLY_TAX_PROFILE,
                    target_tax_profile_id=profiles["GST_5"].id,
                )
            ],
        ),
        (
            "GENERAL_STANDARD",
            "General standard taxation",
            12,
            [
                (
                    "tax_profile_id",
                    TaxRuleConditionOperator.EQUALS,
                    str(profiles["GST_18"].id),
                    None,
                    None,
                )
            ],
            [
                TaxRuleActionWrite(
                    sequence=1,
                    action_type=TaxRuleActionType.APPLY_TAX_PROFILE,
                    target_tax_profile_id=profiles["GST_18"].id,
                )
            ],
        ),
        (
            "PURCHASE_INPUT_CREDIT",
            "Purchase input credit allowed",
            20,
            [
                (
                    "transaction_type",
                    TaxRuleConditionOperator.EQUALS,
                    "PURCHASE",
                    None,
                    None,
                )
            ],
            [
                TaxRuleActionWrite(
                    sequence=1, action_type=TaxRuleActionType.INPUT_CREDIT_ALLOWED
                )
            ],
        ),
    )
    for code, name, priority, conditions, actions in rule_definitions:
        service.create_rule(
            TaxRuleWrite(
                country_id=country_id,
                business_profile_id=profile_id,
                tax_profile_id=None,
                code=code,
                name=name,
                description=f"{name} rule for development simulation coverage.",
                priority=priority,
                status=TaxStatus.ACTIVE,
                effective_from=date(2025, 4, 1),
                effective_to=None,
                conditions=[
                    TaxRuleConditionWrite(
                        sequence=index,
                        field_key=field_key,
                        operator=operator,
                        value_text=value_text,
                        value_number=value_number,
                        value_date=value_date,
                        value_boolean=None,
                        value_json=None,
                    )
                    for index, (
                        field_key,
                        operator,
                        value_text,
                        value_number,
                        value_date,
                    ) in enumerate(conditions, start=1)
                ],
                actions=actions,
            ),
            firm_id=firm_id,
            actor_id=actor_id,
        )


def _seed_product_categories(
    *, product_service: ProductService, firm: Firm, actor_id: UUID
) -> dict[str, ProductCategory]:
    roots = (
        ("MEDICINE", "Medicine"),
        ("FOOD", "Food"),
        ("ELECTRONICS", "Electronics"),
        ("GENERAL_TRADING", "General Trading"),
    )
    subcategories = {
        "MEDICINE": (("TABLETS", "Tablets"), ("SYRUPS", "Syrups")),
        "FOOD": (("STAPLES", "Staples"), ("FROZEN", "Frozen Foods")),
        "ELECTRONICS": (("MOBILES", "Mobiles"), ("HOME_APPLIANCES", "Home Appliances")),
        "GENERAL_TRADING": (
            ("OFFICE_SUPPLIES", "Office Supplies"),
            ("HARDWARE", "Hardware"),
        ),
    }
    created: dict[str, ProductCategory] = {}
    for code, name in roots:
        root = product_service.create_category(
            ProductCategoryCreate(code=code, name=name, parent_id=None, is_active=True),
            firm_id=firm.id,
            actor_id=actor_id,
        )
        created[code] = root
        for child_code, child_name in subcategories[code]:
            product_service.create_category(
                ProductCategoryCreate(
                    code=child_code,
                    name=child_name,
                    parent_id=root.id,
                    is_active=True,
                ),
                firm_id=firm.id,
                actor_id=actor_id,
            )
    return created


def _seed_users(
    *,
    session: Session,
    identity: IdentityService,
    admin_user: User,
    contexts: list[FirmContext],
    user_roles: dict[str, Role],
    logins: list[LoginRecord],
) -> dict[str, list[User]]:
    created_users: dict[str, list[User]] = defaultdict(list)

    for context in contexts:
        firm = context.firm
        blueprint = next(item for item in FIRM_BLUEPRINTS if item["key"] == context.key)
        firm_admin = _create_user_with_role(
            identity=identity,
            actor_id=admin_user.id,
            role=user_roles["FIRM_ADMIN"],
            email=f"admin@{_slug(firm.name)}.local",
            full_name=f"{firm.name} Administrator",
            firm_id=firm.id,
            description="Firm administrator with access to the assigned firm.",
            branch="All Branches",
            firm_name=firm.name,
            logins=logins,
        )
        created_users["firm_admins"].append(firm_admin)

        firm_all_access = _create_user_with_role(
            identity=identity,
            actor_id=admin_user.id,
            role=user_roles["FIRM_ADMIN"],
            email=f"firm.owner@{_slug(firm.name)}.local",
            full_name=f"{firm.name} Firm Owner",
            firm_id=firm.id,
            description="Firm-level full access user limited to this firm scope.",
            branch="All Branches",
            firm_name=firm.name,
            logins=logins,
        )
        created_users["firm_all_access"].append(firm_all_access)

        sales_manager = _create_user_with_role(
            identity=identity,
            actor_id=admin_user.id,
            role=user_roles["SALES_MANAGER"],
            email=f"sales.manager@{_slug(firm.name)}.local",
            full_name=f"{firm.name} Sales Manager",
            firm_id=firm.id,
            description="Sales leadership user for route coverage and customer "
            "planning.",
            branch="All Branches",
            firm_name=firm.name,
            logins=logins,
        )
        created_users["sales_managers"].append(sales_manager)

        purchase_user = _create_user_with_role(
            identity=identity,
            actor_id=admin_user.id,
            role=user_roles["PURCHASE_EXECUTIVE"],
            email=f"purchase@{_slug(firm.name)}.local",
            full_name=f"{firm.name} Purchase User",
            firm_id=firm.id,
            description="Purchase user for procurement and vendor workflows.",
            branch="All Branches",
            firm_name=firm.name,
            logins=logins,
        )
        created_users["purchase_users"].append(purchase_user)

        account_user = _create_user_with_role(
            identity=identity,
            actor_id=admin_user.id,
            role=user_roles["ACCOUNTANT"],
            email=f"accounts@{_slug(firm.name)}.local",
            full_name=f"{firm.name} Accounts User",
            firm_id=firm.id,
            description="Accounts user for tax, reporting, and ledger previews.",
            branch="All Branches",
            firm_name=firm.name,
            logins=logins,
        )
        created_users["account_users"].append(account_user)

        viewer = _create_user_with_role(
            identity=identity,
            actor_id=admin_user.id,
            role=user_roles["VIEWER"],
            email=f"viewer@{_slug(firm.name)}.local",
            full_name=f"{firm.name} Read Only User",
            firm_id=firm.id,
            description="Read-only user for desktop visibility checks.",
            branch="All Branches",
            firm_name=firm.name,
            logins=logins,
        )
        created_users["viewers"].append(viewer)

        for _branch_index, branch in enumerate(context.branches, start=1):
            manager = _create_user_with_role(
                identity=identity,
                actor_id=admin_user.id,
                role=user_roles["FIRM_MANAGER"],
                email=f"{_slug(branch.name)}.manager@{_slug(firm.name)}.local",
                full_name=f"{branch.name} Manager",
                firm_id=firm.id,
                description="Branch manager for branch-level administration.",
                branch=branch.name,
                firm_name=firm.name,
                logins=logins,
            )
            created_users["branch_managers"].append(manager)
            created_users[f"branch:{branch.id}"].append(manager)

        for warehouse in context.warehouses:
            manager = _create_user_with_role(
                identity=identity,
                actor_id=admin_user.id,
                role=user_roles["INVENTORY_MANAGER"],
                email=f"{_slug(warehouse.code)}.manager@{_slug(firm.name)}.local",
                full_name=f"{warehouse.name} Manager",
                firm_id=firm.id,
                description="Warehouse manager for storage and inventory "
                "relationships.",
                branch=_branch_name_for_warehouse(
                    context.branches, warehouse.branch_id
                ),
                firm_name=firm.name,
                logins=logins,
            )
            created_users["warehouse_managers"].append(manager)
            created_users[f"warehouse:{warehouse.id}"].append(manager)

        salesman_count = 4 if len(blueprint["branches"]) == 3 else 4
        context.salesmen = []
        for salesman_index in range(1, salesman_count + 1):
            branch_name = context.branches[
                (salesman_index - 1) % len(context.branches)
            ].name
            salesman = _create_user_with_role(
                identity=identity,
                actor_id=admin_user.id,
                role=user_roles["SALES_EXECUTIVE"],
                email=f"salesman{salesman_index}@{_slug(firm.name)}.local",
                full_name=f"{firm.name} Sales Executive {salesman_index}",
                firm_id=firm.id,
                description="Field sales executive assigned to seeded routes.",
                branch=branch_name,
                firm_name=firm.name,
                logins=logins,
            )
            context.salesmen.append(salesman)
            created_users["salesmen"].append(salesman)

    if len(contexts) >= 3:
        multifirm_assignments = (
            (
                "regional.ops1@agency.local",
                "Regional Operations 1",
                "FIRM_MANAGER",
                [0, 1],
            ),
            (
                "regional.ops2@agency.local",
                "Regional Operations 2",
                "FIRM_MANAGER",
                [1, 2],
            ),
            (
                "regional.ops3@agency.local",
                "Regional Operations 3",
                "FIRM_MANAGER",
                [0, 2],
            ),
            ("auditor.multi1@agency.local", "Regional Auditor 1", "VIEWER", [0, 1, 2]),
            ("auditor.multi2@agency.local", "Regional Auditor 2", "VIEWER", [0, 1, 2]),
        )
        for email, full_name, role_code, indexes in multifirm_assignments:
            primary_context = contexts[indexes[0]]
            user = _create_user_with_role(
                identity=identity,
                actor_id=admin_user.id,
                role=user_roles[role_code],
                email=email,
                full_name=full_name,
                firm_id=primary_context.firm.id,
                description="Multi-firm access user for cross-firm validation.",
                branch="Multiple Branches",
                firm_name=", ".join(contexts[index].firm.name for index in indexes),
                logins=logins,
            )
            identity.set_user_firms(
                user.id,
                [
                    UserFirmAssignment(
                        firm_id=contexts[index].firm.id,
                        is_primary=index == indexes[0],
                        is_active=True,
                    )
                    for index in indexes
                ],
                admin_user.id,
            )
            for index in indexes:
                identity.set_user_roles(
                    user.id,
                    [user_roles[role_code].id],
                    admin_user.id,
                    firm_scope=contexts[index].firm.id,
                )
            created_users["multi_firm"].append(user)
    return created_users


def _assign_branch_and_warehouse_managers(
    *,
    session: Session,
    context: FirmContext,
    actor_id: UUID,
    created_users: dict[str, list[User]],
) -> None:
    for branch in context.branches:
        managers = created_users[f"branch:{branch.id}"]
        if managers:
            branch.branch_manager_id = managers[0].id
            branch.updated_by = actor_id
    for warehouse in context.warehouses:
        managers = created_users[f"warehouse:{warehouse.id}"]
        if managers:
            warehouse.warehouse_manager_id = managers[0].id
            warehouse.updated_by = actor_id
    session.commit()


def _seed_vendors(
    *,
    vendor_service: VendorService,
    geography: dict[str, Any],
    contexts: list[FirmContext],
    actor_id: UUID,
) -> dict[UUID, list[Vendor]]:
    result: dict[UUID, list[Vendor]] = {}
    for context_index, context in enumerate(contexts, start=1):
        categories = {
            code: vendor_service.create_category(
                VendorCategoryWrite(
                    code=code,
                    name=name,
                    description=f"{name} vendors for development data.",
                    is_active=True,
                ),
                firm_id=context.firm.id,
                actor_id=actor_id,
            )
            for code, name in VENDOR_SEGMENTS
        }
        types = {
            code: vendor_service.create_type(
                VendorTypeWrite(
                    code=code,
                    name=name,
                    description=f"{name} vendor type for development data.",
                    is_active=True,
                ),
                firm_id=context.firm.id,
                actor_id=actor_id,
            )
            for code, name in VENDOR_SEGMENTS
        }
        records: list[VendorCreate] = []
        for index in range(16):
            category_code, category_name = VENDOR_SEGMENTS[index % len(VENDOR_SEGMENTS)]
            city_name = list(
                city
                for (state_name, city), item in geography["cities"].items()
                if state_name in GEO_BLUEPRINT
            )[(context_index * 4 + index) % len(geography["cities"])]
            state_name = next(
                state for (state, city) in geography["cities"] if city == city_name
            )
            geo = _geo_for_city(geography, state_name, city_name)
            vendor_name = (
                f"{BRANDS[(index + context_index) % len(BRANDS)]} "
                f"{category_name} {city_name}"
            )
            records.append(
                VendorCreate(
                    code=f"V{context_index}{index + 1:03d}",
                    name=vendor_name,
                    legal_name=f"{vendor_name} Private Limited",
                    display_name=vendor_name,
                    category_id=categories[category_code].id,
                    type_id=types[category_code].id,
                    status=VendorStatus.ACTIVE,
                    business_profile_id=context.profile.id,
                    gst_registration=True,
                    gstin=_gstin(context_index * 100 + index + 1, state_name),
                    pan=_pan(context_index * 100 + index + 1),
                    license_number=f"LIC-V{context_index}{index + 1:03d}",
                    registration_number=f"REG-V{context_index}{index + 1:03d}",
                    website=f"https://{_slug(vendor_name)}.example.local",
                    email=f"contact@{_slug(vendor_name)}.local",
                    phone=_phone(context_index * 100 + index + 1),
                    mobile=_phone(context_index * 100 + index + 401),
                    remarks=f"Preferred for {context.profile.code.lower()} "
                    f"development scenarios.",
                    business_attributes={
                        "segment": category_code,
                        "credit_days": 30 + (index % 4) * 15,
                    },
                    contacts=[
                        VendorContactInput(
                            name=_person_name(index),
                            department="Sales",
                            designation="Key Account Manager",
                            phone=_phone(index + 501),
                            mobile=_phone(index + 601),
                            email=f"ka{index + 1}@{_slug(vendor_name)}.local",
                            is_primary=True,
                            status="ACTIVE",
                        )
                    ],
                    addresses=[
                        VendorAddressInput(
                            address_type=VendorAddressType.HEAD_OFFICE,
                            address_line1=(
                                f"{10 + index} {geo['locality'].name} " "Trade Centre"
                            ),
                            address_line2="Supplier Zone",
                            country_id=geography["country"].id,
                            state_id=geo["state"].id,
                            district_id=geo["district"].id,
                            city_id=geo["city"].id,
                            postal_code_id=geo["postal"].id,
                            locality_id=geo["locality"].id,
                            is_primary=True,
                        )
                    ],
                    banking=[
                        VendorBankInput(
                            bank_name="State Bank of India",
                            account_name=vendor_name,
                            account_number=f"91{context_index:02d}{index + 1:08d}",
                            ifsc=f"SBIN{context_index:02d}{index + 1:05d}",
                            branch=city_name,
                            upi_id=f"{_slug(vendor_name)}@sbi",
                            swift_code=None,
                            is_primary=True,
                        )
                    ],
                    tax=[
                        VendorTaxInput(
                            gstin=_gstin(context_index * 100 + index + 1, state_name),
                            pan=_pan(context_index * 100 + index + 1),
                            tan=f"TAN{context_index:02d}{index + 1:06d}",
                            fssai=(
                                f"FSSAI{context_index:02d}{index + 1:08d}"
                                if context.profile.code == "FOOD"
                                else None
                            ),
                            drug_license=(
                                f"DRUG{context_index:02d}{index + 1:08d}"
                                if context.profile.code in {"PHARMACY", "MEDICAL"}
                                else None
                            ),
                            import_export_code=(
                                f"IEC{context_index:02d}{index + 1:07d}"
                                if category_code == "IMPORTER"
                                else None
                            ),
                            extra_fields={"seeded": True},
                            is_primary=True,
                        )
                    ],
                    attachments=[
                        VendorAttachmentInput(
                            file_name="vendor-profile.pdf",
                            file_url=f"https://files.example.local/vendors/{_slug(vendor_name)}.pdf",
                            mime_type="application/pdf",
                            description="Seeded vendor profile document.",
                        )
                    ],
                    notes=[
                        VendorNoteInput(
                            note="Preferred enterprise development supplier.",
                            note_type="GENERAL",
                        )
                    ],
                )
            )
        result[context.firm.id] = vendor_service.import_vendors(
            records,
            firm_id=context.firm.id,
            actor_id=actor_id,
        )
    return result


def _seed_products(
    *,
    session: Session,
    product_service: ProductService,
    contexts: list[FirmContext],
    vendors_by_firm: dict[UUID, list[Vendor]],
    actor_id: UUID,
    notes: list[str],
) -> dict[UUID, list[Product]]:
    rules = list(
        session.scalars(
            select(CategoryAttributeRule)
            .where(CategoryAttributeRule.is_deleted.is_(False))
            .order_by(CategoryAttributeRule.category_code.asc())
        ).all()
    )
    definitions = {
        row.id: row
        for row in session.scalars(
            select(AttributeDefinition).where(
                AttributeDefinition.is_deleted.is_(False),
                AttributeDefinition.is_active.is_(True),
            )
        ).all()
    }
    required_by_profile_category: dict[
        tuple[UUID | None, str], list[AttributeDefinition]
    ] = defaultdict(list)
    for rule in rules:
        definition = definitions.get(rule.attribute_definition_id)
        if definition is None:
            continue
        required_by_profile_category[
            (rule.business_profile_id, rule.category_code.upper())
        ].append(definition)

    products_by_firm: dict[UUID, list[Product]] = {}
    for context_index, context in enumerate(contexts, start=1):
        created: list[Product] = []
        vendors = vendors_by_firm[context.firm.id]
        warehouse_cycle = list(context.warehouses)
        product_groups = [
            ("MEDICINE", MEDICINE_PRODUCTS, 30, profiles_tax_code(context, "GST_12")),
            ("FOOD", FOOD_PRODUCTS, 30, profiles_tax_code(context, "GST_5")),
            (
                "ELECTRONICS",
                ELECTRONIC_PRODUCTS,
                30,
                profiles_tax_code(context, "GST_18"),
            ),
            (
                "GENERAL_TRADING",
                GENERAL_PRODUCTS,
                30,
                profiles_tax_code(context, "GST_18"),
            ),
        ]
        if context.key == "ALPHA_PHARMA":
            product_groups = [
                (
                    "MEDICINE",
                    MEDICINE_PRODUCTS,
                    120,
                    profiles_tax_code(context, "GST_12"),
                )
            ]
        elif context.key == "FRESH_FOODS":
            product_groups = [
                ("FOOD", FOOD_PRODUCTS, 120, profiles_tax_code(context, "GST_5"))
            ]
        elif context.key == "UNIVERSAL_TRADING":
            product_groups = [
                (
                    "ELECTRONICS",
                    ELECTRONIC_PRODUCTS,
                    60,
                    profiles_tax_code(context, "GST_18"),
                ),
                (
                    "GENERAL_TRADING",
                    GENERAL_PRODUCTS,
                    60,
                    profiles_tax_code(context, "GST_18"),
                ),
            ]

        product_counter = 1
        for category_code, templates, quantity, default_tax_code in product_groups:
            category = context.product_categories[category_code]
            definitions_for_category = (
                required_by_profile_category.get(
                    (context.profile.id, category.code), []
                )
                or required_by_profile_category.get((None, category.code), [])
                or required_by_profile_category.get(
                    (context.profile.id, category.name.upper()), []
                )
                or required_by_profile_category.get((None, category.name.upper()), [])
            )
            for index in range(quantity):
                template_name, unit, hsn = templates[index % len(templates)]
                vendor = vendors[(product_counter - 1) % len(vendors)]
                warehouse = warehouse_cycle[
                    (product_counter - 1) % len(warehouse_cycle)
                ]
                product_name = (
                    f"{BRANDS[(index + context_index) % len(BRANDS)]} "
                    f"{template_name} {((index % 9) + 1) * 10}"
                )
                tax_code = _product_tax_code(product_counter)
                tax_profile = context.tax_profiles[tax_code or default_tax_code]
                attributes = [
                    ProductAttributeInput(
                        attribute_definition_id=definition.id,
                        value=_attribute_value(
                            definition, product_counter, template_name
                        ),
                    )
                    for definition in definitions_for_category
                ]
                created.append(
                    product_service.create_product(
                        ProductCreate(
                            code=f"P{context_index}{product_counter:04d}",
                            barcode=None,
                            qr_code=None,
                            name=product_name,
                            short_name=template_name[:80],
                            description=f"{product_name} seeded for "
                            f"{context.profile.code} development flows.",
                            product_type=ProductType.STOCK_ITEM,
                            category_id=category.id,
                            sub_category_id=None,
                            unit=unit.upper(),
                            brand=BRANDS[(index + context_index) % len(BRANDS)],
                            model=f"M{context_index}{product_counter:03d}",
                            hsn_sac=hsn,
                            tax_profile_group_code=tax_profile.group_code
                            or tax_profile.code,
                            purchase_price=Decimal("50")
                            + Decimal(product_counter % 15) * Decimal("12.5"),
                            selling_price=Decimal("80")
                            + Decimal(product_counter % 15) * Decimal("17.5"),
                            mrp=Decimal("100")
                            + Decimal(product_counter % 15) * Decimal("20"),
                            status=ProductStatus.ACTIVE,
                            remarks=(
                                f"Preferred vendor: {vendor.code}; "
                                f"Default warehouse: {warehouse.code}"
                            ),
                            attributes=attributes,
                            media=[],
                        ),
                        firm_id=context.firm.id,
                        actor_id=actor_id,
                    )
                )
                product_counter += 1
        products_by_firm[context.firm.id] = created
    if rules:
        notes.append(
            "Product dynamic attributes were populated from existing category "
            "attribute rules."
        )
    else:
        notes.append(
            "No category attribute rules were present, so seeded products use only "
            "core fields."
        )
    return products_by_firm


def _seed_customers(
    *,
    customer_service: CustomerService,
    contexts: list[FirmContext],
    geography: dict[str, Any],
    actor_id: UUID,
) -> dict[UUID, list[Customer]]:
    result: dict[UUID, list[Customer]] = {}
    for context_index, context in enumerate(contexts, start=1):
        records: list[CustomerCreate] = []
        for index in range(60):
            segment_code, segment_label = CUSTOMER_SEGMENTS[
                index % len(CUSTOMER_SEGMENTS)
            ]
            state_name, city_name = list(geography["cities"].keys())[
                (context_index * 11 + index) % len(geography["cities"])
            ]
            geo = _geo_for_city(geography, state_name, city_name)
            customer_name = (
                f"{BRANDS[(index + context_index) % len(BRANDS)]} "
                f"{segment_label} {geo['locality'].name}"
            )
            records.append(
                CustomerCreate(
                    code=f"C{context_index}{index + 1:03d}",
                    customer_type=CustomerType.BUSINESS,
                    name=customer_name,
                    display_name=customer_name,
                    gst_number=_gstin(context_index * 300 + index + 1, state_name),
                    pan_number=_pan(context_index * 300 + index + 1),
                    email=f"accounts@{_slug(customer_name)}.local",
                    phone=_phone(context_index * 300 + index + 1),
                    alternate_phone=_phone(context_index * 300 + index + 701),
                    website=f"https://{_slug(customer_name)}.example.local",
                    credit_limit=Decimal("100000") + Decimal(index * 1500),
                    opening_balance=Decimal(index * 500),
                    payment_terms_days=15 + (index % 4) * 15,
                    currency_code="INR",
                    status=CustomerStatus.ACTIVE,
                    notes=f"Seeded {segment_code.lower()} customer for route planning.",
                    addresses=[
                        CustomerAddressInput(
                            address_type=CustomerAddressType.BILLING,
                            address_line1=(
                                f"{100 + index} {geo['locality'].name} " "Main Road"
                            ),
                            address_line2="Commercial Zone",
                            area=geo["locality"].name,
                            city=city_name,
                            district=geo["district"].name,
                            state=state_name,
                            country=INDIA_CODE,
                            postal_code=geo["postal"].postal_code,
                            is_default_billing=True,
                            is_default_shipping=False,
                        ),
                        CustomerAddressInput(
                            address_type=CustomerAddressType.SHIPPING,
                            address_line1=(
                                f"{200 + index} {geo['locality'].name} " "Service Lane"
                            ),
                            address_line2="Delivery Dock",
                            area=geo["locality"].name,
                            city=city_name,
                            district=geo["district"].name,
                            state=state_name,
                            country=INDIA_CODE,
                            postal_code=geo["postal"].postal_code,
                            is_default_billing=False,
                            is_default_shipping=True,
                        ),
                    ],
                    contacts=[
                        CustomerContactInput(
                            name=_person_name(index),
                            designation="Owner",
                            mobile=_phone(context_index * 300 + index + 901),
                            email=f"owner{index + 1}@{_slug(customer_name)}.local",
                            department="Management",
                            is_primary=True,
                        )
                    ],
                )
            )
        result[context.firm.id] = customer_service.import_customers(
            records,
            firm_id=context.firm.id,
            actor_id=actor_id,
        )
    return result


def _assign_routes(
    *,
    territory_service: SalesTerritoryService,
    contexts: list[FirmContext],
    customers_by_firm: dict[UUID, list[Customer]],
    created_users: dict[str, list[User]],
    actor_id: UUID,
) -> None:
    for context in contexts:
        customers = customers_by_firm[context.firm.id]
        salesmen = context.salesmen
        grouped: dict[UUID, list[Customer]] = defaultdict(list)
        for index, customer in enumerate(customers):
            route_id = context.route_leaf_ids[index % len(context.route_leaf_ids)]
            grouped[route_id].append(customer)
        for route_index, route_id in enumerate(context.route_leaf_ids):
            assigned_customers = grouped.get(route_id, [])
            territory_service.set_customers(
                route_id,
                TerritoryAssignCustomersRequest(
                    customer_ids=[],
                    entries=[
                        TerritoryCustomerAssignmentInput(
                            customer_id=customer.id,
                            visit_sequence=position,
                            is_potential=False,
                        )
                        for position, customer in enumerate(assigned_customers, start=1)
                    ],
                ),
                firm_scope=context.firm.id,
                actor_id=actor_id,
            )
            salesman = salesmen[route_index % len(salesmen)]
            territory_service.set_salesmen(
                route_id,
                TerritoryAssignSalesmenRequest(
                    assignments=[
                        SalesmanAssignmentInput(
                            user_id=salesman.id,
                            include_children=False,
                            is_primary=True,
                        )
                    ]
                ),
                firm_scope=context.firm.id,
                actor_id=actor_id,
            )


def _run_tax_simulations(
    *,
    tax_rule_service: TaxRuleService,
    geography: dict[str, Any],
    contexts: list[FirmContext],
    customers_by_firm: dict[UUID, list[Customer]],
    vendors_by_firm: dict[UUID, list[Vendor]],
    products_by_firm: dict[UUID, list[Product]],
    actor_id: UUID,
) -> int:
    executed = 0
    for context in contexts:
        customer = customers_by_firm[context.firm.id][0]
        vendor = vendors_by_firm[context.firm.id][0]
        export_product = products_by_firm[context.firm.id][0]
        high_value_product = products_by_firm[context.firm.id][1]
        purchase_product = products_by_firm[context.firm.id][2]
        city = context.branches[0].city_id
        for request in (
            TaxRuleSimulationRequest(
                transaction_type="EXPORT",
                transaction_date=date(2025, 4, 5),
                country_id=geography["country"].id,
                business_profile_id=context.profile.id,
                tax_profile_id=None,
                branch_id=context.branches[0].id,
                warehouse_id=context.warehouses[0].id,
                customer_id=customer.id,
                vendor_id=vendor.id,
                currency_code="USD",
                origin=context.branches[0].name,
                destination="Overseas",
                state=None,
                district=None,
                city=None,
                product_id=export_product.id,
                product_category_id=export_product.category_id,
                product_type=export_product.product_type,
                invoice_value=Decimal("25000"),
                quantity=Decimal("10"),
                additional_context={},
            ),
            TaxRuleSimulationRequest(
                transaction_type="SALES",
                transaction_date=date(2025, 4, 10),
                country_id=geography["country"].id,
                business_profile_id=context.profile.id,
                tax_profile_id=None,
                branch_id=context.branches[0].id,
                warehouse_id=context.warehouses[0].id,
                customer_id=customer.id,
                vendor_id=None,
                currency_code="INR",
                origin=context.branches[0].name,
                destination=context.branches[0].name,
                state=None,
                district=None,
                city=str(city) if city is not None else None,
                product_id=high_value_product.id,
                product_category_id=high_value_product.category_id,
                product_type=high_value_product.product_type,
                invoice_value=Decimal("75000"),
                quantity=Decimal("25"),
                additional_context={},
            ),
            TaxRuleSimulationRequest(
                transaction_type="PURCHASE",
                transaction_date=date(2025, 4, 12),
                country_id=geography["country"].id,
                business_profile_id=context.profile.id,
                tax_profile_id=None,
                branch_id=context.branches[0].id,
                warehouse_id=context.warehouses[0].id,
                customer_id=None,
                vendor_id=vendor.id,
                currency_code="INR",
                origin="Domestic",
                destination=context.branches[0].name,
                state=None,
                district=None,
                city=None,
                product_id=purchase_product.id,
                product_category_id=purchase_product.category_id,
                product_type=purchase_product.product_type,
                invoice_value=Decimal("18000"),
                quantity=Decimal("15"),
                additional_context={},
            ),
        ):
            tax_rule_service.simulate(
                request, firm_scope=context.firm.id, actor_id=actor_id
            )
            executed += 1
    return executed


def _ensure_superadmin(
    session: Session, identity: IdentityService, settings: Settings
) -> User:
    del settings
    role = session.scalar(select(Role).where(Role.code == "PLATFORM_ADMIN"))
    if role is None:
        raise RuntimeError("System RBAC is missing the PLATFORM_ADMIN role.")
    user = session.scalar(
        select(User)
        .where(User.email == "superadmin@agency.local")
        .execution_options(populate_existing=True)
    )
    if user is None:
        user = identity.create_user(
            UserCreate(
                email="superadmin@agency.local",
                full_name="Super Administrator",
                password=DEVELOPMENT_PASSWORD,
                is_active=True,
                force_password_change=False,
                expires_at=None,
            ),
            SYSTEM_ACTOR_ID,
        )
    else:
        passwords = identity._passwords  # noqa: SLF001
        user.password_hash = passwords.hash_password(DEVELOPMENT_PASSWORD)
        user.full_name = "Super Administrator"
        user.is_active = True
        user.force_password_change = False
        user.expires_at = None
        user.updated_by = SYSTEM_ACTOR_ID
        session.commit()

    platform_admin = session.scalar(
        select(PlatformAdmin).where(PlatformAdmin.user_id == user.id)
    )
    if platform_admin is None:
        session.add(
            PlatformAdmin(
                user_id=user.id,
                created_by=SYSTEM_ACTOR_ID,
                updated_by=SYSTEM_ACTOR_ID,
            )
        )
        session.commit()
    identity.set_user_roles(user.id, [role.id], SYSTEM_ACTOR_ID)
    return user


def _resolve_roles(session: Session) -> dict[str, Role]:
    rows = session.scalars(
        select(Role).where(Role.is_deleted.is_(False), Role.is_active.is_(True))
    ).all()
    by_code = {row.code: row for row in rows}
    required = {
        "FIRM_ADMIN",
        "FIRM_MANAGER",
        "SALES_MANAGER",
        "SALES_EXECUTIVE",
        "PURCHASE_EXECUTIVE",
        "ACCOUNTANT",
        "INVENTORY_MANAGER",
        "VIEWER",
        "PLATFORM_ADMIN",
    }
    missing = sorted(code for code in required if code not in by_code)
    if missing:
        raise RuntimeError(f"Required seeded roles are missing: {', '.join(missing)}")
    return by_code


def _create_user_with_role(
    *,
    identity: IdentityService,
    actor_id: UUID,
    role: Role,
    email: str,
    full_name: str,
    firm_id: UUID,
    description: str,
    branch: str,
    firm_name: str,
    logins: list[LoginRecord],
) -> User:
    user = identity.create_user(
        UserCreate(
            email=email,
            full_name=full_name,
            password=DEVELOPMENT_PASSWORD,
            is_active=True,
            force_password_change=False,
            expires_at=None,
        ),
        actor_id,
        firm_scope=firm_id,
    )
    identity.set_user_roles(user.id, [role.id], actor_id, firm_scope=firm_id)
    logins.append(
        LoginRecord(
            username=user.email,
            role=role.code,
            firm=firm_name,
            branch=branch,
            description=description,
        )
    )
    return user


def _seed_uom_inventory_and_documents(
    *,
    session: Session,
    contexts: list[FirmContext],
    products_by_firm: dict[UUID, list[Product]],
    vendors_by_firm: dict[UUID, list[Vendor]],
    customers_by_firm: dict[UUID, list[Customer]],
    created_users: dict[str, list[User]],
    actor_id: UUID,
) -> Counter[str]:
    counts: Counter[str] = Counter()
    if not contexts:
        return counts

    context = contexts[0]
    firm_id = context.firm.id
    products = products_by_firm.get(firm_id, [])
    vendors = vendors_by_firm.get(firm_id, [])
    customers = customers_by_firm.get(firm_id, [])
    if len(products) < 4 or not vendors or len(customers) < 2:
        return counts

    branch = context.branches[0]
    warehouse = next(
        (item for item in context.warehouses if item.branch_id == branch.id),
        context.warehouses[0],
    )
    returns_warehouse = (
        context.warehouses[1] if len(context.warehouses) > 1 else warehouse
    )

    main_storage_nodes = list(
        session.scalars(
            select(WarehouseStorageNode)
            .where(
                WarehouseStorageNode.warehouse_id == warehouse.id,
                WarehouseStorageNode.node_type == "BIN",
                WarehouseStorageNode.is_deleted.is_(False),
            )
            .order_by(WarehouseStorageNode.path)
        ).all()
    )
    if not main_storage_nodes:
        return counts
    default_storage = main_storage_nodes[0]

    route_profiles = {
        row.territory_id: row
        for row in session.scalars(
            select(TerritoryRouteProfile).where(
                TerritoryRouteProfile.territory_id.in_(context.route_leaf_ids),
                TerritoryRouteProfile.is_deleted.is_(False),
            )
        ).all()
    }
    route_profile = route_profiles.get(context.route_leaf_ids[0])
    route_id = route_profile.id if route_profile is not None else None
    territory_id = context.route_leaf_ids[0]
    salesman = context.salesmen[0] if context.salesmen else None
    buyer = created_users.get("purchase_users", [None])[0]
    receiver = created_users.get("warehouse_managers", [None])[0]

    uom_by_code = {
        row.code: row
        for row in session.scalars(
            select(Uom).where(
                Uom.code.in_(("PCS", "BOX", "CTN")),
                Uom.is_deleted.is_(False),
            )
        ).all()
    }
    if "PCS" not in uom_by_code:
        uom = Uom(
            code="PCS",
            name="Pieces",
            symbol="pcs",
            dimension="COUNT",
            status="ACTIVE",
            is_decimal_allowed=True,
            created_by=actor_id,
            updated_by=actor_id,
        )
        session.add(uom)
        session.flush()
        uom_by_code["PCS"] = uom
    if "BOX" not in uom_by_code:
        uom = Uom(
            code="BOX",
            name="Box",
            symbol="box",
            dimension="COUNT",
            status="ACTIVE",
            is_decimal_allowed=False,
            created_by=actor_id,
            updated_by=actor_id,
        )
        session.add(uom)
        session.flush()
        uom_by_code["BOX"] = uom
    if "CTN" not in uom_by_code:
        uom = Uom(
            code="CTN",
            name="Carton",
            symbol="ctn",
            dimension="COUNT",
            status="ACTIVE",
            is_decimal_allowed=False,
            created_by=actor_id,
            updated_by=actor_id,
        )
        session.add(uom)
        session.flush()
        uom_by_code["CTN"] = uom

    uom_unit = uom_by_code["PCS"]
    uom_box = uom_by_code["BOX"]
    uom_carton = uom_by_code["CTN"]

    uom_group = session.scalar(
        select(UomGroup).where(
            UomGroup.code == "NVK_PACK_COUNT",
            UomGroup.is_deleted.is_(False),
        )
    )
    if uom_group is None:
        uom_group = UomGroup(
            code="NVK_PACK_COUNT",
            name="Navkar Pack Count",
            description="Default count group for sample ERP dataset.",
            status="ACTIVE",
            created_by=actor_id,
            updated_by=actor_id,
        )
        session.add(uom_group)
        session.flush()

    existing_group_uom_ids = {
        row.uom_id
        for row in session.scalars(
            select(UomGroupUnit).where(
                UomGroupUnit.uom_group_id == uom_group.id,
                UomGroupUnit.is_deleted.is_(False),
            )
        ).all()
    }
    for display_order, uom_id, is_base in (
        (1, uom_unit.id, True),
        (2, uom_box.id, False),
        (3, uom_carton.id, False),
    ):
        if uom_id in existing_group_uom_ids:
            continue
        session.add(
            UomGroupUnit(
                uom_group_id=uom_group.id,
                uom_id=uom_id,
                is_base=is_base,
                display_order=display_order,
                created_by=actor_id,
                updated_by=actor_id,
            )
        )

    packaging_by_code = {
        row.code: row
        for row in session.scalars(
            select(PackagingType).where(
                PackagingType.code.in_(("UNIT", "BOX", "CARTON")),
                PackagingType.is_deleted.is_(False),
            )
        ).all()
    }
    if "UNIT" not in packaging_by_code:
        session.add(
            PackagingType(
                code="UNIT",
                name="Unit",
                description="Single unit packaging.",
                status="ACTIVE",
                created_by=actor_id,
                updated_by=actor_id,
            )
        )
    if "BOX" not in packaging_by_code:
        session.add(
            PackagingType(
                code="BOX",
                name="Box",
                description="Inner retail box.",
                status="ACTIVE",
                created_by=actor_id,
                updated_by=actor_id,
            )
        )
    if "CARTON" not in packaging_by_code:
        session.add(
            PackagingType(
                code="CARTON",
                name="Carton",
                description="Outer shipping carton.",
                status="ACTIVE",
                created_by=actor_id,
                updated_by=actor_id,
            )
        )
    session.flush()
    packaging_by_code = {
        row.code: row
        for row in session.scalars(
            select(PackagingType).where(
                PackagingType.code.in_(("UNIT", "BOX", "CARTON")),
                PackagingType.is_deleted.is_(False),
            )
        ).all()
    }
    pkg_unit = packaging_by_code["UNIT"]
    pkg_box = packaging_by_code["BOX"]
    pkg_carton = packaging_by_code["CARTON"]

    profile_defaults = session.scalar(
        select(BusinessProfileUomDefault).where(
            BusinessProfileUomDefault.firm_id == firm_id,
            BusinessProfileUomDefault.business_profile_id == context.profile.id,
            BusinessProfileUomDefault.is_deleted.is_(False),
        )
    )
    if profile_defaults is None:
        session.add(
            BusinessProfileUomDefault(
                firm_id=firm_id,
                business_profile_id=context.profile.id,
                base_uom_id=uom_unit.id,
                inventory_uom_id=uom_unit.id,
                purchase_uom_id=uom_box.id,
                sales_uom_id=uom_unit.id,
                allow_fraction=False,
                allow_decimal=True,
                created_by=actor_id,
                updated_by=actor_id,
            )
        )

    for index, product in enumerate(products[:6], start=1):
        product.base_uom_id = uom_unit.id
        product.inventory_uom_id = uom_unit.id
        product.purchase_uom_id = uom_box.id
        product.sales_uom_id = uom_unit.id
        product.default_receiving_uom_id = uom_box.id
        product.default_dispatch_uom_id = uom_unit.id
        product.minimum_sales_uom_id = uom_unit.id
        product.allow_fraction = False
        product.allow_decimal = True
        product.track_batch = index <= 2
        product.track_expiry = index <= 2
        product.track_manufacturing_date = index <= 2
        product.updated_by = actor_id

        session.add(
            ConversionRule(
                firm_id=firm_id,
                business_profile_id=context.profile.id,
                product_id=product.id,
                from_uom_id=uom_box.id,
                to_uom_id=uom_unit.id,
                conversion_factor=Decimal("10"),
                rounding_mode="HALF_UP",
                precision_scale=4,
                effective_from=date(2026, 4, 1),
                effective_to=None,
                version=1,
                status="ACTIVE",
                reason="Default sample conversion (1 box = 10 pcs).",
                created_by=actor_id,
                updated_by=actor_id,
            )
        )
        # The unit slots live on the product itself. `product_uom_configs`
        # held a second copy of these fourteen columns and was removed in
        # `20260812_0068`; every module reads `product.purchase_uom_id`.
        product.base_uom_id = uom_unit.id
        product.inventory_uom_id = uom_unit.id
        product.purchase_uom_id = uom_box.id
        product.sales_uom_id = uom_unit.id
        product.default_receiving_uom_id = uom_box.id
        product.default_dispatch_uom_id = uom_unit.id
        product.minimum_sales_uom_id = uom_unit.id
        product.allow_fraction = False
        product.allow_decimal = True
        product.weight = Decimal("0.2500")
        product.volume = Decimal("0.0010")
        product.length = Decimal("0.1000")
        product.width = Decimal("0.0500")
        product.height = Decimal("0.0400")
        product.updated_by = actor_id
        unit_level = ProductPackagingLevel(
            firm_id=firm_id,
            product_id=product.id,
            parent_level_id=None,
            packaging_type_id=pkg_unit.id,
            uom_id=uom_unit.id,
            level_name="Unit",
            conversion_to_base_factor=Decimal("1"),
            barcode=f"890{index:010d}",
            status="ACTIVE",
            display_order=1,
            created_by=actor_id,
            updated_by=actor_id,
        )
        session.add(unit_level)
        session.flush()
        session.add(
            ProductPackagingLevel(
                firm_id=firm_id,
                product_id=product.id,
                parent_level_id=unit_level.id,
                packaging_type_id=pkg_carton.id,
                uom_id=uom_carton.id,
                level_name="Carton",
                conversion_to_base_factor=Decimal("100"),
                barcode=f"8909{index:09d}",
                status="ACTIVE",
                display_order=2,
                created_by=actor_id,
                updated_by=actor_id,
            )
        )

    opening_batch = OpeningStockBatch(
        firm_id=firm_id,
        branch_id=branch.id,
        warehouse_id=warehouse.id,
        reference_number="OS/NVK/2026/0001",
        posting_date=date(2026, 4, 1),
        source_format="MANUAL",
        status="POSTED",
        remarks="Opening stock for ERP integration testing.",
        posted_at=date(2026, 4, 1),
        created_by=actor_id,
        updated_by=actor_id,
    )
    session.add(opening_batch)
    session.flush()

    inventory_by_product: dict[UUID, InventoryRecord] = {}
    opening_quantities = [
        Decimal("500"),
        Decimal("420"),
        Decimal("380"),
        Decimal("300"),
    ]
    for line_number, (product, quantity) in enumerate(
        zip(products[:4], opening_quantities, strict=False), start=1
    ):
        locator = default_storage.path
        inventory = InventoryRecord(
            firm_id=firm_id,
            branch_id=branch.id,
            warehouse_id=warehouse.id,
            storage_node_id=default_storage.id,
            storage_locator=locator,
            product_id=product.id,
            business_profile_id=context.profile.id,
            current_quantity=Decimal("0"),
            reserved_quantity=Decimal("0"),
            available_quantity=Decimal("0"),
            blocked_quantity=Decimal("0"),
            damaged_quantity=Decimal("0"),
            quarantine_quantity=Decimal("0"),
            in_transit_quantity=Decimal("0"),
            display_quantity=Decimal("0"),
            display_uom_id=uom_unit.id,
            minimum_level=Decimal("80"),
            maximum_level=Decimal("1000"),
            reorder_level=Decimal("120"),
            safety_stock=Decimal("60"),
            last_transaction_at=date(2026, 4, 1),
            status="ACTIVE",
            created_by=actor_id,
            updated_by=actor_id,
        )
        session.add(inventory)
        session.flush()
        inventory_by_product[product.id] = inventory
        opening_line = OpeningStockLine(
            opening_stock_batch_id=opening_batch.id,
            line_number=line_number,
            product_id=product.id,
            storage_node_id=default_storage.id,
            storage_locator=locator,
            business_profile_id=context.profile.id,
            quantity=quantity,
            entered_quantity=quantity,
            entered_uom_id=uom_unit.id,
            conversion_version=1,
            minimum_level=Decimal("80"),
            maximum_level=Decimal("1000"),
            reorder_level=Decimal("120"),
            safety_stock=Decimal("60"),
            remarks="Opening balance entry",
            created_by=actor_id,
            updated_by=actor_id,
        )
        session.add(opening_line)
        transaction = _create_inventory_transaction(
            session=session,
            inventory=inventory,
            actor_id=actor_id,
            transaction_type="OPENING_STOCK",
            reference_number=opening_batch.reference_number,
            reference_type="OPENING_STOCK_BATCH",
            transaction_date=opening_batch.posting_date,
            quantity=quantity,
            current_delta=quantity,
            reserved_delta=Decimal("0"),
            blocked_delta=Decimal("0"),
            damaged_delta=Decimal("0"),
            quarantine_delta=Decimal("0"),
            in_transit_delta=Decimal("0"),
            remarks="Opening stock posted.",
            entered_quantity=quantity,
            entered_uom_id=uom_unit.id,
            conversion_version=1,
        )
        opening_line.transaction_id = transaction.id

    tax_profile = context.tax_profiles.get("GST_18") or next(
        iter(context.tax_profiles.values())
    )

    po_approved = PurchaseOrder(
        firm_id=firm_id,
        branch_id=branch.id,
        warehouse_id=warehouse.id,
        vendor_id=vendors[0].id,
        buyer_id=buyer.id if buyer is not None else None,
        tax_profile_id=tax_profile.id,
        po_number="PO/NVK/2026/0001",
        vendor_contact="Priya Kulkarni",
        vendor_address="C-14, MIDC Industrial Estate, Andheri East, Mumbai",
        department="Procurement",
        purchase_type="STANDARD_PURCHASE",
        purchase_category="Resale Goods",
        purchase_date=date(2026, 4, 5),
        expected_delivery_date=date(2026, 4, 12),
        payment_terms="30 Days",
        delivery_terms="Door Delivery",
        currency_code="INR",
        exchange_rate=Decimal("1"),
        reference_number="VQ-2026-118",
        external_reference="MAIL-APR-PO1",
        priority="HIGH",
        remarks="Primary purchase order for April replenishment.",
        status="APPROVED",
        subtotal=Decimal("14600"),
        line_discount_total=Decimal("300"),
        header_discount_amount=Decimal("100"),
        tax_total=Decimal("2628"),
        additional_charges=Decimal("250"),
        round_off=Decimal("0"),
        grand_total=Decimal("17378"),
        created_by=actor_id,
        updated_by=actor_id,
    )
    session.add(po_approved)
    session.flush()

    po1_line1 = PurchaseOrderLine(
        purchase_order_id=po_approved.id,
        firm_id=firm_id,
        line_number=1,
        product_id=products[0].id,
        description=products[0].name,
        purchase_uom_id=uom_box.id,
        inventory_uom_id=uom_unit.id,
        conversion_factor=Decimal("10"),
        conversion_version=1,
        ordered_quantity=Decimal("100"),
        free_quantity=Decimal("0"),
        base_quantity=Decimal("100"),
        unit_price=Decimal("50"),
        discount_percent=Decimal("2"),
        discount_amount=Decimal("100"),
        gross_amount=Decimal("4900"),
        tax_profile_id=tax_profile.id,
        tax_amount=Decimal("882"),
        net_amount=Decimal("5782"),
        batch_required=True,
        expiry_required=True,
        serial_required=False,
        warehouse_id=warehouse.id,
        storage_node_id=default_storage.id,
        remarks="Batch controlled.",
        status="PARTIALLY_RECEIVED",
        created_by=actor_id,
        updated_by=actor_id,
    )
    po1_line2 = PurchaseOrderLine(
        purchase_order_id=po_approved.id,
        firm_id=firm_id,
        line_number=2,
        product_id=products[1].id,
        description=products[1].name,
        purchase_uom_id=uom_box.id,
        inventory_uom_id=uom_unit.id,
        conversion_factor=Decimal("10"),
        conversion_version=1,
        ordered_quantity=Decimal("80"),
        free_quantity=Decimal("0"),
        base_quantity=Decimal("80"),
        unit_price=Decimal("120"),
        discount_percent=Decimal("2.0833"),
        discount_amount=Decimal("200"),
        gross_amount=Decimal("9400"),
        tax_profile_id=tax_profile.id,
        tax_amount=Decimal("1692"),
        net_amount=Decimal("11092"),
        batch_required=True,
        expiry_required=True,
        serial_required=False,
        warehouse_id=warehouse.id,
        storage_node_id=default_storage.id,
        remarks="Fast moving SKU.",
        status="PARTIALLY_RECEIVED",
        created_by=actor_id,
        updated_by=actor_id,
    )
    session.add_all([po1_line1, po1_line2])
    session.flush()
    session.add_all(
        [
            PurchaseDeliverySchedule(
                purchase_order_line_id=po1_line1.id,
                firm_id=firm_id,
                delivery_date=date(2026, 4, 8),
                quantity=Decimal("60"),
                status="RECEIVED",
                remarks="First tranche received.",
                created_by=actor_id,
                updated_by=actor_id,
            ),
            PurchaseDeliverySchedule(
                purchase_order_line_id=po1_line1.id,
                firm_id=firm_id,
                delivery_date=date(2026, 4, 12),
                quantity=Decimal("40"),
                status="PENDING",
                remarks="Balance pending.",
                created_by=actor_id,
                updated_by=actor_id,
            ),
            PurchaseDeliverySchedule(
                purchase_order_line_id=po1_line2.id,
                firm_id=firm_id,
                delivery_date=date(2026, 4, 8),
                quantity=Decimal("50"),
                status="RECEIVED",
                remarks="First tranche received.",
                created_by=actor_id,
                updated_by=actor_id,
            ),
            PurchaseDeliverySchedule(
                purchase_order_line_id=po1_line2.id,
                firm_id=firm_id,
                delivery_date=date(2026, 4, 12),
                quantity=Decimal("30"),
                status="PENDING",
                remarks="Balance pending.",
                created_by=actor_id,
                updated_by=actor_id,
            ),
        ]
    )
    session.add(
        PurchaseAttachment(
            purchase_order_id=po_approved.id,
            firm_id=firm_id,
            file_name="po-nvk-2026-0001.pdf",
            mime_type="application/pdf",
            file_path="/demo/docs/po/PO-NVK-2026-0001.pdf",
            attachment_kind="PURCHASE_FILE",
            created_by=actor_id,
            updated_by=actor_id,
        )
    )
    session.add(
        PurchaseNote(
            purchase_order_id=po_approved.id,
            firm_id=firm_id,
            note_type="INTERNAL",
            note="Supplier committed split delivery with batch stickers.",
            created_by=actor_id,
            updated_by=actor_id,
        )
    )
    session.add_all(
        [
            PurchaseOrderHistory(
                purchase_order_id=po_approved.id,
                firm_id=firm_id,
                action="CREATED",
                from_status=None,
                to_status="DRAFT",
                remarks="Initial creation.",
                created_by=actor_id,
                updated_by=actor_id,
            ),
            PurchaseOrderHistory(
                purchase_order_id=po_approved.id,
                firm_id=firm_id,
                action="APPROVED",
                from_status="DRAFT",
                to_status="APPROVED",
                remarks="Approved by procurement manager.",
                created_by=actor_id,
                updated_by=actor_id,
            ),
            PurchaseOrderHistory(
                purchase_order_id=po_approved.id,
                firm_id=firm_id,
                action="PARTIAL_RECEIPT",
                from_status="APPROVED",
                to_status="PARTIALLY_RECEIVED",
                remarks="GRN posted for partial quantities.",
                created_by=actor_id,
                updated_by=actor_id,
            ),
        ]
    )

    po_cancelled = PurchaseOrder(
        firm_id=firm_id,
        branch_id=branch.id,
        warehouse_id=warehouse.id,
        vendor_id=vendors[1].id,
        buyer_id=buyer.id if buyer is not None else None,
        po_number="PO/NVK/2026/0002",
        purchase_date=date(2026, 4, 6),
        expected_delivery_date=date(2026, 4, 15),
        currency_code="INR",
        exchange_rate=Decimal("1"),
        status="CANCELLED",
        subtotal=Decimal("3600"),
        line_discount_total=Decimal("0"),
        header_discount_amount=Decimal("0"),
        tax_total=Decimal("648"),
        additional_charges=Decimal("0"),
        round_off=Decimal("0"),
        grand_total=Decimal("4248"),
        cancel_reason="Vendor requested cancellation due to supply disruption.",
        created_by=actor_id,
        updated_by=actor_id,
    )
    session.add(po_cancelled)
    session.flush()
    session.add(
        PurchaseOrderLine(
            purchase_order_id=po_cancelled.id,
            firm_id=firm_id,
            line_number=1,
            product_id=products[2].id,
            ordered_quantity=Decimal("30"),
            base_quantity=Decimal("30"),
            unit_price=Decimal("120"),
            gross_amount=Decimal("3600"),
            tax_profile_id=tax_profile.id,
            tax_amount=Decimal("648"),
            net_amount=Decimal("4248"),
            status="ORDERED",
            created_by=actor_id,
            updated_by=actor_id,
        )
    )

    po_closed = PurchaseOrder(
        firm_id=firm_id,
        branch_id=branch.id,
        warehouse_id=returns_warehouse.id,
        vendor_id=vendors[2].id,
        buyer_id=buyer.id if buyer is not None else None,
        po_number="PO/NVK/2026/0003",
        purchase_date=date(2026, 4, 2),
        expected_delivery_date=date(2026, 4, 4),
        currency_code="INR",
        exchange_rate=Decimal("1"),
        status="CLOSED",
        subtotal=Decimal("1800"),
        line_discount_total=Decimal("0"),
        header_discount_amount=Decimal("0"),
        tax_total=Decimal("324"),
        additional_charges=Decimal("0"),
        round_off=Decimal("0"),
        grand_total=Decimal("2124"),
        close_reason="Order completed and archived.",
        created_by=actor_id,
        updated_by=actor_id,
    )
    session.add(po_closed)
    session.flush()
    session.add(
        PurchaseOrderLine(
            purchase_order_id=po_closed.id,
            firm_id=firm_id,
            line_number=1,
            product_id=products[3].id,
            ordered_quantity=Decimal("20"),
            base_quantity=Decimal("20"),
            unit_price=Decimal("90"),
            gross_amount=Decimal("1800"),
            tax_profile_id=tax_profile.id,
            tax_amount=Decimal("324"),
            net_amount=Decimal("2124"),
            status="RECEIVED",
            warehouse_id=returns_warehouse.id,
            created_by=actor_id,
            updated_by=actor_id,
        )
    )

    grn_completed = GoodsReceipt(
        firm_id=firm_id,
        purchase_order_id=po_approved.id,
        purchase_order_number=po_approved.po_number,
        vendor_id=vendors[0].id,
        branch_id=branch.id,
        warehouse_id=warehouse.id,
        received_by_id=receiver.id if receiver is not None else None,
        grn_number="GRN/NVK/2026/0001",
        receipt_date=date(2026, 4, 8),
        transport_details="Sai Logistics LR-778219",
        vehicle_number="MH12AB4582",
        invoice_reference="INV-SUP-7782",
        remarks="Partial receipt against PO 0001.",
        allow_over_receipt=False,
        over_receipt_percent=Decimal("0"),
        status="COMPLETED",
        total_ordered_quantity=Decimal("180"),
        total_previous_received_quantity=Decimal("0"),
        total_current_receipt_quantity=Decimal("110"),
        total_accepted_quantity=Decimal("108"),
        total_rejected_quantity=Decimal("1"),
        total_damaged_quantity=Decimal("1"),
        total_free_quantity=Decimal("0"),
        line_discount_total=Decimal("180"),
        subtotal=Decimal("8900"),
        tax_total=Decimal("1602"),
        additional_charges=Decimal("120"),
        round_off=Decimal("0"),
        grand_total=Decimal("10622"),
        completed_at=datetime(2026, 4, 8, 15, 30, tzinfo=UTC),
        created_by=actor_id,
        updated_by=actor_id,
    )
    session.add(grn_completed)
    session.flush()

    grn1_inv_tx_1 = _create_inventory_transaction(
        session=session,
        inventory=inventory_by_product[products[0].id],
        actor_id=actor_id,
        transaction_type="GOODS_RECEIPT",
        reference_number=grn_completed.grn_number,
        reference_type="GRN",
        transaction_date=grn_completed.receipt_date,
        quantity=Decimal("59"),
        current_delta=Decimal("59"),
        reserved_delta=Decimal("0"),
        blocked_delta=Decimal("0"),
        damaged_delta=Decimal("1"),
        quarantine_delta=Decimal("0"),
        in_transit_delta=Decimal("0"),
        remarks="GRN accepted quantity plus damaged segregation.",
        entered_quantity=Decimal("60"),
        entered_uom_id=uom_unit.id,
        conversion_version=1,
    )
    grn1_inv_tx_2 = _create_inventory_transaction(
        session=session,
        inventory=inventory_by_product[products[1].id],
        actor_id=actor_id,
        transaction_type="GOODS_RECEIPT",
        reference_number=grn_completed.grn_number,
        reference_type="GRN",
        transaction_date=grn_completed.receipt_date,
        quantity=Decimal("50"),
        current_delta=Decimal("50"),
        reserved_delta=Decimal("0"),
        blocked_delta=Decimal("0"),
        damaged_delta=Decimal("0"),
        quarantine_delta=Decimal("0"),
        in_transit_delta=Decimal("0"),
        remarks="GRN accepted quantity.",
        entered_quantity=Decimal("50"),
        entered_uom_id=uom_unit.id,
        conversion_version=1,
    )
    session.add_all(
        [
            GoodsReceiptLine(
                goods_receipt_id=grn_completed.id,
                firm_id=firm_id,
                line_number=1,
                purchase_order_line_id=po1_line1.id,
                purchase_order_line_number=1,
                product_id=products[0].id,
                description=products[0].name,
                ordered_quantity=Decimal("100"),
                previously_received_quantity=Decimal("0"),
                current_receipt_quantity=Decimal("60"),
                accepted_quantity=Decimal("58"),
                unit_price=Decimal("50"),
                discount_percent=Decimal("2"),
                discount_amount=Decimal("60"),
                gross_amount=Decimal("2940"),
                tax_profile_id=tax_profile.id,
                tax_amount=Decimal("529.2"),
                net_amount=Decimal("3469.2"),
                rejected_quantity=Decimal("1"),
                damaged_quantity=Decimal("1"),
                free_quantity=Decimal("0"),
                packaging_type_id=pkg_box.id,
                purchase_uom_id=uom_box.id,
                inventory_uom_id=uom_unit.id,
                conversion_factor=Decimal("10"),
                conversion_version=1,
                warehouse_id=warehouse.id,
                storage_node_id=default_storage.id,
                batch_number="BATCH-NVK-0408-A",
                expiry_date=date(2027, 3, 31),
                manufacturing_date=date(2026, 3, 15),
                inventory_transaction_id=grn1_inv_tx_1.id,
                remarks="1 unit rejected and 1 unit damaged.",
                created_by=actor_id,
                updated_by=actor_id,
            ),
            GoodsReceiptLine(
                goods_receipt_id=grn_completed.id,
                firm_id=firm_id,
                line_number=2,
                purchase_order_line_id=po1_line2.id,
                purchase_order_line_number=2,
                product_id=products[1].id,
                description=products[1].name,
                ordered_quantity=Decimal("80"),
                previously_received_quantity=Decimal("0"),
                current_receipt_quantity=Decimal("50"),
                accepted_quantity=Decimal("50"),
                unit_price=Decimal("120"),
                discount_percent=Decimal("2"),
                discount_amount=Decimal("120"),
                gross_amount=Decimal("5880"),
                tax_profile_id=tax_profile.id,
                tax_amount=Decimal("1058.4"),
                net_amount=Decimal("6938.4"),
                rejected_quantity=Decimal("0"),
                damaged_quantity=Decimal("0"),
                free_quantity=Decimal("0"),
                packaging_type_id=pkg_box.id,
                purchase_uom_id=uom_box.id,
                inventory_uom_id=uom_unit.id,
                conversion_factor=Decimal("10"),
                conversion_version=1,
                warehouse_id=warehouse.id,
                storage_node_id=default_storage.id,
                batch_number="BATCH-NVK-0408-B",
                expiry_date=date(2027, 1, 31),
                manufacturing_date=date(2026, 2, 20),
                inventory_transaction_id=grn1_inv_tx_2.id,
                remarks="Accepted in full.",
                created_by=actor_id,
                updated_by=actor_id,
            ),
        ]
    )
    session.add(
        GoodsReceiptAttachment(
            goods_receipt_id=grn_completed.id,
            firm_id=firm_id,
            file_name="grn-0001-transport-slip.jpg",
            mime_type="image/jpeg",
            file_path="/demo/docs/grn/GRN-NVK-2026-0001-slip.jpg",
            attachment_kind="GRN_FILE",
            created_by=actor_id,
            updated_by=actor_id,
        )
    )
    session.add(
        GoodsReceiptNote(
            goods_receipt_id=grn_completed.id,
            firm_id=firm_id,
            note_type="INTERNAL",
            note="QC completed. Damaged quantity segregated.",
            created_by=actor_id,
            updated_by=actor_id,
        )
    )

    grn_draft = GoodsReceipt(
        firm_id=firm_id,
        purchase_order_id=po_approved.id,
        purchase_order_number=po_approved.po_number,
        vendor_id=vendors[0].id,
        branch_id=branch.id,
        warehouse_id=warehouse.id,
        received_by_id=receiver.id if receiver is not None else None,
        grn_number="GRN/NVK/2026/0002",
        receipt_date=date(2026, 4, 12),
        remarks="Draft second receipt awaiting truck arrival.",
        status="DRAFT",
        total_ordered_quantity=Decimal("180"),
        total_previous_received_quantity=Decimal("110"),
        total_current_receipt_quantity=Decimal("0"),
        total_accepted_quantity=Decimal("0"),
        total_rejected_quantity=Decimal("0"),
        total_damaged_quantity=Decimal("0"),
        total_free_quantity=Decimal("0"),
        line_discount_total=Decimal("0"),
        subtotal=Decimal("0"),
        tax_total=Decimal("0"),
        additional_charges=Decimal("0"),
        round_off=Decimal("0"),
        grand_total=Decimal("0"),
        created_by=actor_id,
        updated_by=actor_id,
    )
    session.add(grn_draft)

    purchase_invoice_approved = PurchaseInvoice(
        firm_id=firm_id,
        vendor_id=vendors[0].id,
        branch_id=branch.id,
        business_profile_id=context.profile.id,
        invoice_number="PINV/NVK/2026/0001",
        invoice_date=date(2026, 4, 9),
        supplier_invoice_number="SUP-INV-7782",
        supplier_invoice_date=date(2026, 4, 8),
        currency_code="INR",
        exchange_rate=Decimal("1"),
        payment_terms="30 Days",
        due_date=date(2026, 5, 9),
        reference_number=grn_completed.grn_number,
        remarks="First partial supplier invoice.",
        allow_direct_purchase_order=False,
        allow_over_invoice=False,
        over_invoice_percent=Decimal("0"),
        status="APPROVED",
        total_source_quantity=Decimal("108"),
        total_already_invoiced_quantity=Decimal("0"),
        total_current_invoice_quantity=Decimal("70"),
        line_discount_total=Decimal("120"),
        subtotal=Decimal("5600"),
        tax_total=Decimal("1008"),
        additional_charges=Decimal("0"),
        round_off=Decimal("0"),
        grand_total=Decimal("6608"),
        approved_at=datetime(2026, 4, 9, 12, 15, tzinfo=UTC),
        created_by=actor_id,
        updated_by=actor_id,
    )
    session.add(purchase_invoice_approved)
    session.flush()
    session.add(
        PurchaseInvoiceSource(
            purchase_invoice_id=purchase_invoice_approved.id,
            firm_id=firm_id,
            source_document_type="GOODS_RECEIPT",
            source_document_id=grn_completed.id,
            source_document_number=grn_completed.grn_number,
            source_document_date=grn_completed.receipt_date,
            vendor_id=vendors[0].id,
            branch_id=branch.id,
            created_by=actor_id,
            updated_by=actor_id,
        )
    )
    session.add_all(
        [
            PurchaseInvoiceLine(
                purchase_invoice_id=purchase_invoice_approved.id,
                firm_id=firm_id,
                line_number=1,
                source_document_type="GOODS_RECEIPT",
                source_document_id=grn_completed.id,
                source_document_number=grn_completed.grn_number,
                source_document_line_id=grn1_inv_tx_1.id,
                source_document_line_number=1,
                product_id=products[0].id,
                description=products[0].name,
                received_quantity=Decimal("58"),
                already_invoiced_quantity=Decimal("0"),
                current_invoice_quantity=Decimal("40"),
                unit_price=Decimal("50"),
                discount_percent=Decimal("0"),
                discount_amount=Decimal("0"),
                charges_amount=Decimal("0"),
                gross_amount=Decimal("2000"),
                tax_profile_id=tax_profile.id,
                tax_amount=Decimal("360"),
                net_amount=Decimal("2360"),
                packaging_type_id=pkg_box.id,
                purchase_uom_id=uom_box.id,
                invoice_uom_id=uom_unit.id,
                conversion_factor=Decimal("10"),
                conversion_version=1,
                warehouse_id=warehouse.id,
                storage_node_id=default_storage.id,
                batch_number="BATCH-NVK-0408-A",
                created_by=actor_id,
                updated_by=actor_id,
            ),
            PurchaseInvoiceLine(
                purchase_invoice_id=purchase_invoice_approved.id,
                firm_id=firm_id,
                line_number=2,
                source_document_type="GOODS_RECEIPT",
                source_document_id=grn_completed.id,
                source_document_number=grn_completed.grn_number,
                source_document_line_id=grn1_inv_tx_2.id,
                source_document_line_number=2,
                product_id=products[1].id,
                description=products[1].name,
                received_quantity=Decimal("50"),
                already_invoiced_quantity=Decimal("0"),
                current_invoice_quantity=Decimal("30"),
                unit_price=Decimal("120"),
                gross_amount=Decimal("3600"),
                tax_profile_id=tax_profile.id,
                tax_amount=Decimal("648"),
                net_amount=Decimal("4248"),
                packaging_type_id=pkg_box.id,
                purchase_uom_id=uom_box.id,
                invoice_uom_id=uom_unit.id,
                conversion_factor=Decimal("10"),
                conversion_version=1,
                warehouse_id=warehouse.id,
                storage_node_id=default_storage.id,
                batch_number="BATCH-NVK-0408-B",
                created_by=actor_id,
                updated_by=actor_id,
            ),
        ]
    )
    session.add(
        PurchaseInvoiceAttachment(
            purchase_invoice_id=purchase_invoice_approved.id,
            firm_id=firm_id,
            file_name="supplier-invoice-7782.pdf",
            mime_type="application/pdf",
            file_path="/demo/docs/pinv/PINV-NVK-2026-0001.pdf",
            attachment_kind="PURCHASE_INVOICE_FILE",
            created_by=actor_id,
            updated_by=actor_id,
        )
    )
    session.add(
        PurchaseInvoiceNote(
            purchase_invoice_id=purchase_invoice_approved.id,
            firm_id=firm_id,
            note_type="INTERNAL",
            note="Partial invoice accepted for booked quantity.",
            created_by=actor_id,
            updated_by=actor_id,
        )
    )
    session.add(
        PurchaseInvoiceAccountingEvent(
            purchase_invoice_id=purchase_invoice_approved.id,
            firm_id=firm_id,
            event_type="ACCOUNTS_PAYABLE",
            account_name="Sundry Creditors",
            direction="CREDIT",
            amount=purchase_invoice_approved.grand_total,
            narration="Supplier payable booked.",
            created_by=actor_id,
            updated_by=actor_id,
        )
    )

    purchase_invoice_draft = PurchaseInvoice(
        firm_id=firm_id,
        vendor_id=vendors[0].id,
        branch_id=branch.id,
        business_profile_id=context.profile.id,
        invoice_number="PINV/NVK/2026/0002",
        invoice_date=date(2026, 4, 13),
        supplier_invoice_number="SUP-INV-7782-B",
        supplier_invoice_date=date(2026, 4, 12),
        status="DRAFT",
        total_source_quantity=Decimal("108"),
        total_already_invoiced_quantity=Decimal("70"),
        total_current_invoice_quantity=Decimal("38"),
        line_discount_total=Decimal("0"),
        subtotal=Decimal("3300"),
        tax_total=Decimal("594"),
        additional_charges=Decimal("0"),
        round_off=Decimal("0"),
        grand_total=Decimal("3894"),
        created_by=actor_id,
        updated_by=actor_id,
    )
    purchase_invoice_cancelled = PurchaseInvoice(
        firm_id=firm_id,
        vendor_id=vendors[1].id,
        branch_id=branch.id,
        business_profile_id=context.profile.id,
        invoice_number="PINV/NVK/2026/0003",
        invoice_date=date(2026, 4, 10),
        supplier_invoice_number="SUP-CAN-2001",
        supplier_invoice_date=date(2026, 4, 10),
        status="CANCELLED",
        total_source_quantity=Decimal("30"),
        total_already_invoiced_quantity=Decimal("0"),
        total_current_invoice_quantity=Decimal("0"),
        line_discount_total=Decimal("0"),
        subtotal=Decimal("0"),
        tax_total=Decimal("0"),
        additional_charges=Decimal("0"),
        round_off=Decimal("0"),
        grand_total=Decimal("0"),
        cancel_reason="Duplicate supplier submission voided.",
        created_by=actor_id,
        updated_by=actor_id,
    )
    session.add_all([purchase_invoice_draft, purchase_invoice_cancelled])
    session.flush()
    session.add(
        PurchaseInvoiceSource(
            purchase_invoice_id=purchase_invoice_draft.id,
            firm_id=firm_id,
            source_document_type="GOODS_RECEIPT",
            source_document_id=grn_completed.id,
            source_document_number=grn_completed.grn_number,
            source_document_date=grn_completed.receipt_date,
            vendor_id=vendors[0].id,
            branch_id=branch.id,
            created_by=actor_id,
            updated_by=actor_id,
        )
    )
    session.add_all(
        [
            PurchaseInvoiceLine(
                purchase_invoice_id=purchase_invoice_draft.id,
                firm_id=firm_id,
                line_number=1,
                source_document_type="GOODS_RECEIPT",
                source_document_id=grn_completed.id,
                source_document_number=grn_completed.grn_number,
                source_document_line_id=grn1_inv_tx_1.id,
                source_document_line_number=1,
                product_id=products[0].id,
                description=products[0].name,
                received_quantity=Decimal("58"),
                already_invoiced_quantity=Decimal("40"),
                current_invoice_quantity=Decimal("18"),
                unit_price=Decimal("50"),
                gross_amount=Decimal("900"),
                tax_profile_id=tax_profile.id,
                tax_amount=Decimal("162"),
                net_amount=Decimal("1062"),
                packaging_type_id=pkg_box.id,
                purchase_uom_id=uom_box.id,
                invoice_uom_id=uom_unit.id,
                conversion_factor=Decimal("10"),
                conversion_version=1,
                warehouse_id=warehouse.id,
                storage_node_id=default_storage.id,
                created_by=actor_id,
                updated_by=actor_id,
            ),
            PurchaseInvoiceLine(
                purchase_invoice_id=purchase_invoice_draft.id,
                firm_id=firm_id,
                line_number=2,
                source_document_type="GOODS_RECEIPT",
                source_document_id=grn_completed.id,
                source_document_number=grn_completed.grn_number,
                source_document_line_id=grn1_inv_tx_2.id,
                source_document_line_number=2,
                product_id=products[1].id,
                description=products[1].name,
                received_quantity=Decimal("50"),
                already_invoiced_quantity=Decimal("30"),
                current_invoice_quantity=Decimal("20"),
                unit_price=Decimal("120"),
                gross_amount=Decimal("2400"),
                tax_profile_id=tax_profile.id,
                tax_amount=Decimal("432"),
                net_amount=Decimal("2832"),
                packaging_type_id=pkg_box.id,
                purchase_uom_id=uom_box.id,
                invoice_uom_id=uom_unit.id,
                conversion_factor=Decimal("10"),
                conversion_version=1,
                warehouse_id=warehouse.id,
                storage_node_id=default_storage.id,
                created_by=actor_id,
                updated_by=actor_id,
            ),
        ]
    )

    purchase_return = PurchaseReturn(
        firm_id=firm_id,
        vendor_id=vendors[0].id,
        branch_id=branch.id,
        warehouse_id=returns_warehouse.id,
        business_profile_id=context.profile.id,
        return_number="PRTN/NVK/2026/0001",
        return_date=date(2026, 4, 11),
        supplier_return_number="SUP-RTN-204",
        supplier_return_date=date(2026, 4, 11),
        reference_grn_number=grn_completed.grn_number,
        return_reason="DAMAGED",
        currency_code="INR",
        exchange_rate=Decimal("1"),
        status="COMPLETED",
        total_source_quantity=Decimal("58"),
        total_already_returned_quantity=Decimal("0"),
        total_current_return_quantity=Decimal("5"),
        line_discount_total=Decimal("0"),
        subtotal=Decimal("250"),
        tax_total=Decimal("45"),
        additional_charges=Decimal("0"),
        round_off=Decimal("0"),
        grand_total=Decimal("295"),
        approved_at=datetime(2026, 4, 11, 11, 0, tzinfo=UTC),
        created_by=actor_id,
        updated_by=actor_id,
    )
    session.add(purchase_return)
    session.flush()
    session.add(
        PurchaseReturnSource(
            purchase_return_id=purchase_return.id,
            firm_id=firm_id,
            source_document_type="GOODS_RECEIPT",
            source_document_id=grn_completed.id,
            source_document_number=grn_completed.grn_number,
            source_document_date=grn_completed.receipt_date,
            vendor_id=vendors[0].id,
            branch_id=branch.id,
            created_by=actor_id,
            updated_by=actor_id,
        )
    )
    session.add(
        PurchaseReturnLine(
            purchase_return_id=purchase_return.id,
            firm_id=firm_id,
            line_number=1,
            source_document_type="GOODS_RECEIPT",
            source_document_id=grn_completed.id,
            source_document_number=grn_completed.grn_number,
            source_document_line_id=grn1_inv_tx_1.id,
            source_document_line_number=1,
            product_id=products[0].id,
            description=products[0].name,
            received_quantity=Decimal("58"),
            already_returned_quantity=Decimal("0"),
            current_return_quantity=Decimal("5"),
            rejected_quantity=Decimal("0"),
            reason_code="DAMAGED",
            item_condition="DAMAGED",
            replacement_required=True,
            refund_required=False,
            is_damaged=True,
            unit_price=Decimal("50"),
            gross_amount=Decimal("250"),
            tax_profile_id=tax_profile.id,
            tax_amount=Decimal("45"),
            net_amount=Decimal("295"),
            packaging_type_id=pkg_box.id,
            purchase_uom_id=uom_box.id,
            return_uom_id=uom_unit.id,
            conversion_factor=Decimal("10"),
            conversion_version=1,
            warehouse_id=returns_warehouse.id,
            storage_node_id=default_storage.id,
            batch_number="BATCH-NVK-0408-A",
            remarks="Returned damaged material for replacement.",
            accounting_event_reference="PRTN-ACC-0001",
            created_by=actor_id,
            updated_by=actor_id,
        )
    )
    session.add(
        PurchaseReturnAttachment(
            purchase_return_id=purchase_return.id,
            firm_id=firm_id,
            file_name="return-gatepass-0001.pdf",
            mime_type="application/pdf",
            file_path="/demo/docs/prtn/PRTN-NVK-2026-0001-gatepass.pdf",
            attachment_kind="PURCHASE_RETURN_FILE",
            created_by=actor_id,
            updated_by=actor_id,
        )
    )
    session.add(
        PurchaseReturnNote(
            purchase_return_id=purchase_return.id,
            firm_id=firm_id,
            note_type="INTERNAL",
            note="Vendor informed to dispatch replacement in next lot.",
            created_by=actor_id,
            updated_by=actor_id,
        )
    )
    session.add(
        PurchaseReturnAccountingEvent(
            purchase_return_id=purchase_return.id,
            firm_id=firm_id,
            event_type="PURCHASE_RETURN",
            account_name="Purchase Return",
            direction="CREDIT",
            amount=purchase_return.grand_total,
            narration="Purchase return posted.",
            created_by=actor_id,
            updated_by=actor_id,
        )
    )
    _create_inventory_transaction(
        session=session,
        inventory=inventory_by_product[products[0].id],
        actor_id=actor_id,
        transaction_type="RETURN",
        reference_number=purchase_return.return_number,
        reference_type="PURCHASE_RETURN",
        transaction_date=purchase_return.return_date,
        quantity=Decimal("5"),
        current_delta=Decimal("-5"),
        reserved_delta=Decimal("0"),
        blocked_delta=Decimal("0"),
        damaged_delta=Decimal("-1"),
        quarantine_delta=Decimal("0"),
        in_transit_delta=Decimal("0"),
        remarks="Returned damaged quantity to vendor.",
        entered_quantity=Decimal("5"),
        entered_uom_id=uom_unit.id,
        conversion_version=1,
    )

    sales_order_approved = SalesOrder(
        firm_id=firm_id,
        customer_id=customers[0].id,
        salesman_id=salesman.id if salesman is not None else None,
        territory_id=territory_id,
        route_id=route_id,
        branch_id=branch.id,
        warehouse_id=warehouse.id,
        business_profile_id=context.profile.id,
        order_number="SO/NVK/2026/0001",
        order_date=date(2026, 4, 10),
        delivery_date=date(2026, 4, 12),
        customer_reference="PO-CUST-1189",
        reference_number="WEB-ORDER-428",
        currency_code="INR",
        exchange_rate=Decimal("1"),
        remarks="Priority pharmacy replenishment.",
        credit_limit_snapshot=Decimal("150000"),
        outstanding_balance_snapshot=Decimal("28000"),
        status="APPROVED",
        line_discount_total=Decimal("250"),
        subtotal=Decimal("14900"),
        tax_total=Decimal("2682"),
        additional_charges=Decimal("120"),
        round_off=Decimal("0"),
        grand_total=Decimal("17702"),
        approved_at=datetime(2026, 4, 10, 10, 45, tzinfo=UTC),
        created_by=actor_id,
        updated_by=actor_id,
    )
    session.add(sales_order_approved)
    session.flush()
    so_line1 = SalesOrderLine(
        sales_order_id=sales_order_approved.id,
        firm_id=firm_id,
        line_number=1,
        product_id=products[0].id,
        description=products[0].name,
        quantity=Decimal("70"),
        free_quantity=Decimal("0"),
        base_quantity=Decimal("70"),
        reservable_quantity=Decimal("70"),
        reserved_quantity=Decimal("70"),
        available_stock=inventory_by_product[products[0].id].available_quantity,
        reserved_stock=inventory_by_product[products[0].id].reserved_quantity,
        sales_uom_id=uom_unit.id,
        inventory_uom_id=uom_unit.id,
        packaging_type_id=pkg_unit.id,
        conversion_factor=Decimal("1"),
        conversion_version=1,
        unit_price=Decimal("95"),
        discount_percent=Decimal("1"),
        discount_amount=Decimal("66.5"),
        gross_amount=Decimal("6583.5"),
        tax_profile_id=tax_profile.id,
        tax_amount=Decimal("1185.03"),
        net_amount=Decimal("7768.53"),
        warehouse_id=warehouse.id,
        storage_node_id=default_storage.id,
        remarks="Reserved from main bin.",
        created_by=actor_id,
        updated_by=actor_id,
    )
    so_line2 = SalesOrderLine(
        sales_order_id=sales_order_approved.id,
        firm_id=firm_id,
        line_number=2,
        product_id=products[1].id,
        description=products[1].name,
        quantity=Decimal("60"),
        free_quantity=Decimal("0"),
        base_quantity=Decimal("60"),
        reservable_quantity=Decimal("60"),
        reserved_quantity=Decimal("60"),
        available_stock=inventory_by_product[products[1].id].available_quantity,
        reserved_stock=inventory_by_product[products[1].id].reserved_quantity,
        sales_uom_id=uom_unit.id,
        inventory_uom_id=uom_unit.id,
        packaging_type_id=pkg_unit.id,
        conversion_factor=Decimal("1"),
        conversion_version=1,
        unit_price=Decimal("125"),
        discount_percent=Decimal("2.4467"),
        discount_amount=Decimal("183.5"),
        gross_amount=Decimal("7316.5"),
        tax_profile_id=tax_profile.id,
        tax_amount=Decimal("1316.97"),
        net_amount=Decimal("8633.47"),
        warehouse_id=warehouse.id,
        storage_node_id=default_storage.id,
        remarks="Reserved from main bin.",
        created_by=actor_id,
        updated_by=actor_id,
    )
    session.add_all([so_line1, so_line2])
    session.add(
        SalesOrderAttachment(
            sales_order_id=sales_order_approved.id,
            firm_id=firm_id,
            file_name="customer-po-1189.pdf",
            mime_type="application/pdf",
            file_path="/demo/docs/so/SO-NVK-2026-0001-customer-po.pdf",
            attachment_kind="SALES_ORDER_FILE",
            created_by=actor_id,
            updated_by=actor_id,
        )
    )
    session.add(
        SalesOrderNote(
            sales_order_id=sales_order_approved.id,
            firm_id=firm_id,
            note_type="INTERNAL",
            note="Reserved stock immediately after approval.",
            created_by=actor_id,
            updated_by=actor_id,
        )
    )

    _create_inventory_transaction(
        session=session,
        inventory=inventory_by_product[products[0].id],
        actor_id=actor_id,
        transaction_type="RESERVATION",
        reference_number=sales_order_approved.order_number,
        reference_type="SALES_ORDER",
        transaction_date=sales_order_approved.order_date,
        quantity=Decimal("70"),
        current_delta=Decimal("0"),
        reserved_delta=Decimal("70"),
        blocked_delta=Decimal("0"),
        damaged_delta=Decimal("0"),
        quarantine_delta=Decimal("0"),
        in_transit_delta=Decimal("0"),
        remarks="Stock reservation for SO line 1.",
        entered_quantity=Decimal("70"),
        entered_uom_id=uom_unit.id,
        conversion_version=1,
    )
    _create_inventory_transaction(
        session=session,
        inventory=inventory_by_product[products[1].id],
        actor_id=actor_id,
        transaction_type="RESERVATION",
        reference_number=sales_order_approved.order_number,
        reference_type="SALES_ORDER",
        transaction_date=sales_order_approved.order_date,
        quantity=Decimal("60"),
        current_delta=Decimal("0"),
        reserved_delta=Decimal("60"),
        blocked_delta=Decimal("0"),
        damaged_delta=Decimal("0"),
        quarantine_delta=Decimal("0"),
        in_transit_delta=Decimal("0"),
        remarks="Stock reservation for SO line 2.",
        entered_quantity=Decimal("60"),
        entered_uom_id=uom_unit.id,
        conversion_version=1,
    )

    sales_order_cancelled = SalesOrder(
        firm_id=firm_id,
        customer_id=customers[1].id,
        branch_id=branch.id,
        warehouse_id=warehouse.id,
        order_number="SO/NVK/2026/0002",
        order_date=date(2026, 4, 11),
        status="CANCELLED",
        line_discount_total=Decimal("0"),
        subtotal=Decimal("2500"),
        tax_total=Decimal("450"),
        additional_charges=Decimal("0"),
        round_off=Decimal("0"),
        grand_total=Decimal("2950"),
        cancel_reason="Customer requested deferment.",
        created_by=actor_id,
        updated_by=actor_id,
    )
    sales_order_closed = SalesOrder(
        firm_id=firm_id,
        customer_id=customers[2].id,
        branch_id=branch.id,
        warehouse_id=warehouse.id,
        order_number="SO/NVK/2026/0003",
        order_date=date(2026, 4, 7),
        status="CLOSED",
        line_discount_total=Decimal("0"),
        subtotal=Decimal("1600"),
        tax_total=Decimal("288"),
        additional_charges=Decimal("0"),
        round_off=Decimal("0"),
        grand_total=Decimal("1888"),
        close_reason="Delivered and financially closed.",
        created_by=actor_id,
        updated_by=actor_id,
    )
    session.add_all([sales_order_cancelled, sales_order_closed])

    delivery_note_completed = DeliveryNote(
        firm_id=firm_id,
        sales_order_id=sales_order_approved.id,
        customer_id=customers[0].id,
        branch_id=branch.id,
        warehouse_id=warehouse.id,
        business_profile_id=context.profile.id,
        salesman_id=salesman.id if salesman is not None else None,
        route_id=route_id,
        territory_id=territory_id,
        delivery_note_number="DN/NVK/2026/0001",
        delivery_date=date(2026, 4, 12),
        sales_order_reference=sales_order_approved.order_number,
        vehicle="MH12TX9922",
        driver="Ravi More",
        remarks="Partial first delivery.",
        status="COMPLETED",
        total_ordered_quantity=Decimal("130"),
        total_previously_delivered_quantity=Decimal("0"),
        total_current_delivery_quantity=Decimal("70"),
        total_free_quantity=Decimal("0"),
        line_discount_total=Decimal("150"),
        subtotal=Decimal("8120"),
        tax_total=Decimal("1461.6"),
        additional_charges=Decimal("60"),
        round_off=Decimal("0"),
        grand_total=Decimal("9641.6"),
        approved_at=datetime(2026, 4, 12, 10, 0, tzinfo=UTC),
        dispatched_at=datetime(2026, 4, 12, 11, 0, tzinfo=UTC),
        completed_at=datetime(2026, 4, 12, 16, 30, tzinfo=UTC),
        created_by=actor_id,
        updated_by=actor_id,
    )
    session.add(delivery_note_completed)
    session.flush()
    dn_tx_1 = _create_inventory_transaction(
        session=session,
        inventory=inventory_by_product[products[0].id],
        actor_id=actor_id,
        transaction_type="GOODS_ISSUE",
        reference_number=delivery_note_completed.delivery_note_number,
        reference_type="DELIVERY_NOTE",
        transaction_date=delivery_note_completed.delivery_date,
        quantity=Decimal("40"),
        current_delta=Decimal("-40"),
        reserved_delta=Decimal("-40"),
        blocked_delta=Decimal("0"),
        damaged_delta=Decimal("0"),
        quarantine_delta=Decimal("0"),
        in_transit_delta=Decimal("0"),
        remarks="Delivery issue against SO line 1.",
        entered_quantity=Decimal("40"),
        entered_uom_id=uom_unit.id,
        conversion_version=1,
    )
    dn_tx_2 = _create_inventory_transaction(
        session=session,
        inventory=inventory_by_product[products[1].id],
        actor_id=actor_id,
        transaction_type="GOODS_ISSUE",
        reference_number=delivery_note_completed.delivery_note_number,
        reference_type="DELIVERY_NOTE",
        transaction_date=delivery_note_completed.delivery_date,
        quantity=Decimal("30"),
        current_delta=Decimal("-30"),
        reserved_delta=Decimal("-30"),
        blocked_delta=Decimal("0"),
        damaged_delta=Decimal("0"),
        quarantine_delta=Decimal("0"),
        in_transit_delta=Decimal("0"),
        remarks="Delivery issue against SO line 2.",
        entered_quantity=Decimal("30"),
        entered_uom_id=uom_unit.id,
        conversion_version=1,
    )
    session.add_all(
        [
            DeliveryNoteLine(
                delivery_note_id=delivery_note_completed.id,
                firm_id=firm_id,
                sales_order_line_id=so_line1.id,
                line_number=1,
                product_id=products[0].id,
                description=products[0].name,
                ordered_quantity=Decimal("70"),
                reserved_quantity=Decimal("70"),
                previously_delivered_quantity=Decimal("0"),
                current_delivery_quantity=Decimal("40"),
                free_quantity=Decimal("0"),
                delivered_quantity=Decimal("40"),
                remaining_quantity=Decimal("30"),
                damaged_quantity=Decimal("0"),
                short_shipment_quantity=Decimal("0"),
                sales_uom_id=uom_unit.id,
                inventory_uom_id=uom_unit.id,
                packaging_type_id=pkg_unit.id,
                conversion_factor=Decimal("1"),
                conversion_version=1,
                unit_price=Decimal("95"),
                discount_percent=Decimal("1"),
                discount_amount=Decimal("38"),
                gross_amount=Decimal("3762"),
                tax_profile_id=tax_profile.id,
                tax_amount=Decimal("677.16"),
                net_amount=Decimal("4439.16"),
                warehouse_id=warehouse.id,
                storage_node_id=default_storage.id,
                released_reservation_transaction_id=dn_tx_1.id,
                inventory_transaction_id=dn_tx_1.id,
                remarks="Delivered in good condition.",
                created_by=actor_id,
                updated_by=actor_id,
            ),
            DeliveryNoteLine(
                delivery_note_id=delivery_note_completed.id,
                firm_id=firm_id,
                sales_order_line_id=so_line2.id,
                line_number=2,
                product_id=products[1].id,
                description=products[1].name,
                ordered_quantity=Decimal("60"),
                reserved_quantity=Decimal("60"),
                previously_delivered_quantity=Decimal("0"),
                current_delivery_quantity=Decimal("30"),
                free_quantity=Decimal("0"),
                delivered_quantity=Decimal("30"),
                remaining_quantity=Decimal("30"),
                damaged_quantity=Decimal("0"),
                short_shipment_quantity=Decimal("0"),
                sales_uom_id=uom_unit.id,
                inventory_uom_id=uom_unit.id,
                packaging_type_id=pkg_unit.id,
                conversion_factor=Decimal("1"),
                conversion_version=1,
                unit_price=Decimal("125"),
                discount_percent=Decimal("2"),
                discount_amount=Decimal("75"),
                gross_amount=Decimal("3675"),
                tax_profile_id=tax_profile.id,
                tax_amount=Decimal("661.5"),
                net_amount=Decimal("4336.5"),
                warehouse_id=warehouse.id,
                storage_node_id=default_storage.id,
                released_reservation_transaction_id=dn_tx_2.id,
                inventory_transaction_id=dn_tx_2.id,
                remarks="Delivered in good condition.",
                created_by=actor_id,
                updated_by=actor_id,
            ),
        ]
    )
    session.add(
        DeliveryNoteAttachment(
            delivery_note_id=delivery_note_completed.id,
            firm_id=firm_id,
            file_name="dn-proof-0001.jpg",
            mime_type="image/jpeg",
            file_path="/demo/docs/dn/DN-NVK-2026-0001-proof.jpg",
            attachment_kind="DELIVERY_NOTE_FILE",
            created_by=actor_id,
            updated_by=actor_id,
        )
    )
    session.add(
        DeliveryNoteNote(
            delivery_note_id=delivery_note_completed.id,
            firm_id=firm_id,
            note_type="INTERNAL",
            note="POD received and uploaded.",
            created_by=actor_id,
            updated_by=actor_id,
        )
    )

    delivery_note_draft = DeliveryNote(
        firm_id=firm_id,
        sales_order_id=sales_order_approved.id,
        customer_id=customers[0].id,
        branch_id=branch.id,
        warehouse_id=warehouse.id,
        delivery_note_number="DN/NVK/2026/0002",
        delivery_date=date(2026, 4, 14),
        sales_order_reference=sales_order_approved.order_number,
        status="DRAFT",
        total_ordered_quantity=Decimal("130"),
        total_previously_delivered_quantity=Decimal("70"),
        total_current_delivery_quantity=Decimal("0"),
        total_free_quantity=Decimal("0"),
        line_discount_total=Decimal("0"),
        subtotal=Decimal("0"),
        tax_total=Decimal("0"),
        additional_charges=Decimal("0"),
        round_off=Decimal("0"),
        grand_total=Decimal("0"),
        remarks="Draft for second dispatch.",
        created_by=actor_id,
        updated_by=actor_id,
    )
    delivery_note_cancelled = DeliveryNote(
        firm_id=firm_id,
        sales_order_id=sales_order_cancelled.id,
        customer_id=customers[1].id,
        branch_id=branch.id,
        warehouse_id=warehouse.id,
        delivery_note_number="DN/NVK/2026/0003",
        delivery_date=date(2026, 4, 13),
        sales_order_reference=sales_order_cancelled.order_number,
        status="CANCELLED",
        total_ordered_quantity=Decimal("20"),
        total_previously_delivered_quantity=Decimal("0"),
        total_current_delivery_quantity=Decimal("0"),
        total_free_quantity=Decimal("0"),
        line_discount_total=Decimal("0"),
        subtotal=Decimal("0"),
        tax_total=Decimal("0"),
        additional_charges=Decimal("0"),
        round_off=Decimal("0"),
        grand_total=Decimal("0"),
        cancel_reason="Customer cancelled order before dispatch.",
        created_by=actor_id,
        updated_by=actor_id,
    )
    session.add_all([delivery_note_draft, delivery_note_cancelled])

    sales_invoice_approved = SalesInvoice(
        firm_id=firm_id,
        customer_id=customers[0].id,
        salesman_id=salesman.id if salesman is not None else None,
        territory_id=territory_id,
        route_id=route_id,
        branch_id=branch.id,
        business_profile_id=context.profile.id,
        invoice_number="SINV/NVK/2026/0001",
        invoice_date=date(2026, 4, 12),
        customer_invoice_number="CINV-9011",
        currency_code="INR",
        exchange_rate=Decimal("1"),
        payment_terms="15 Days",
        due_date=date(2026, 4, 27),
        reference_number=delivery_note_completed.delivery_note_number,
        remarks="First partial billing against delivery.",
        status="APPROVED",
        total_source_quantity=Decimal("70"),
        total_already_invoiced_quantity=Decimal("0"),
        total_current_invoice_quantity=Decimal("45"),
        line_discount_total=Decimal("80"),
        subtotal=Decimal("5300"),
        tax_total=Decimal("954"),
        additional_charges=Decimal("40"),
        round_off=Decimal("0"),
        grand_total=Decimal("6294"),
        approved_at=datetime(2026, 4, 12, 17, 30, tzinfo=UTC),
        created_by=actor_id,
        updated_by=actor_id,
    )
    session.add(sales_invoice_approved)
    session.flush()
    session.add(
        SalesInvoiceSource(
            sales_invoice_id=sales_invoice_approved.id,
            firm_id=firm_id,
            source_document_type="DELIVERY_NOTE",
            source_document_id=delivery_note_completed.id,
            source_document_number=delivery_note_completed.delivery_note_number,
            source_document_date=delivery_note_completed.delivery_date,
            customer_id=customers[0].id,
            branch_id=branch.id,
            created_by=actor_id,
            updated_by=actor_id,
        )
    )
    session.add_all(
        [
            SalesInvoiceLine(
                sales_invoice_id=sales_invoice_approved.id,
                firm_id=firm_id,
                line_number=1,
                source_document_type="DELIVERY_NOTE",
                source_document_id=delivery_note_completed.id,
                source_document_number=delivery_note_completed.delivery_note_number,
                source_document_line_id=so_line1.id,
                source_document_line_number=1,
                product_id=products[0].id,
                description=products[0].name,
                delivered_quantity=Decimal("40"),
                already_invoiced_quantity=Decimal("0"),
                current_invoice_quantity=Decimal("25"),
                unit_price=Decimal("95"),
                gross_amount=Decimal("2375"),
                tax_profile_id=tax_profile.id,
                tax_amount=Decimal("427.5"),
                net_amount=Decimal("2802.5"),
                packaging_type_id=pkg_unit.id,
                order_uom_id=uom_unit.id,
                invoice_uom_id=uom_unit.id,
                conversion_factor=Decimal("1"),
                conversion_version=1,
                warehouse_id=warehouse.id,
                storage_node_id=default_storage.id,
                created_by=actor_id,
                updated_by=actor_id,
            ),
            SalesInvoiceLine(
                sales_invoice_id=sales_invoice_approved.id,
                firm_id=firm_id,
                line_number=2,
                source_document_type="DELIVERY_NOTE",
                source_document_id=delivery_note_completed.id,
                source_document_number=delivery_note_completed.delivery_note_number,
                source_document_line_id=so_line2.id,
                source_document_line_number=2,
                product_id=products[1].id,
                description=products[1].name,
                delivered_quantity=Decimal("30"),
                already_invoiced_quantity=Decimal("0"),
                current_invoice_quantity=Decimal("20"),
                unit_price=Decimal("125"),
                discount_amount=Decimal("80"),
                gross_amount=Decimal("2420"),
                tax_profile_id=tax_profile.id,
                tax_amount=Decimal("435.6"),
                net_amount=Decimal("2855.6"),
                packaging_type_id=pkg_unit.id,
                order_uom_id=uom_unit.id,
                invoice_uom_id=uom_unit.id,
                conversion_factor=Decimal("1"),
                conversion_version=1,
                warehouse_id=warehouse.id,
                storage_node_id=default_storage.id,
                created_by=actor_id,
                updated_by=actor_id,
            ),
        ]
    )
    session.add(
        SalesInvoiceAttachment(
            sales_invoice_id=sales_invoice_approved.id,
            firm_id=firm_id,
            file_name="invoice-nvk-0001.pdf",
            mime_type="application/pdf",
            file_path="/demo/docs/sinv/SINV-NVK-2026-0001.pdf",
            attachment_kind="SALES_INVOICE_FILE",
            created_by=actor_id,
            updated_by=actor_id,
        )
    )
    session.add(
        SalesInvoiceNote(
            sales_invoice_id=sales_invoice_approved.id,
            firm_id=firm_id,
            note_type="INTERNAL",
            note="Partial invoice approved by billing.",
            created_by=actor_id,
            updated_by=actor_id,
        )
    )
    session.add(
        SalesInvoiceAccountingEvent(
            sales_invoice_id=sales_invoice_approved.id,
            firm_id=firm_id,
            event_type="ACCOUNTS_RECEIVABLE",
            account_name="Sundry Debtors",
            direction="DEBIT",
            amount=sales_invoice_approved.grand_total,
            narration="Customer receivable booked.",
            created_by=actor_id,
            updated_by=actor_id,
        )
    )

    sales_invoice_closed = SalesInvoice(
        firm_id=firm_id,
        customer_id=customers[0].id,
        branch_id=branch.id,
        business_profile_id=context.profile.id,
        invoice_number="SINV/NVK/2026/0002",
        invoice_date=date(2026, 4, 15),
        customer_invoice_number="CINV-9011-B",
        status="CLOSED",
        total_source_quantity=Decimal("70"),
        total_already_invoiced_quantity=Decimal("45"),
        total_current_invoice_quantity=Decimal("25"),
        line_discount_total=Decimal("0"),
        subtotal=Decimal("2675"),
        tax_total=Decimal("481.5"),
        additional_charges=Decimal("0"),
        round_off=Decimal("0"),
        grand_total=Decimal("3156.5"),
        close_reason="Paid and closed in full.",
        closed_at=datetime(2026, 4, 20, 9, 0, tzinfo=UTC),
        created_by=actor_id,
        updated_by=actor_id,
    )
    sales_invoice_cancelled = SalesInvoice(
        firm_id=firm_id,
        customer_id=customers[1].id,
        branch_id=branch.id,
        business_profile_id=context.profile.id,
        invoice_number="SINV/NVK/2026/0003",
        invoice_date=date(2026, 4, 13),
        status="CANCELLED",
        total_source_quantity=Decimal("20"),
        total_already_invoiced_quantity=Decimal("0"),
        total_current_invoice_quantity=Decimal("0"),
        line_discount_total=Decimal("0"),
        subtotal=Decimal("0"),
        tax_total=Decimal("0"),
        additional_charges=Decimal("0"),
        round_off=Decimal("0"),
        grand_total=Decimal("0"),
        cancel_reason="Cancelled before posting.",
        created_by=actor_id,
        updated_by=actor_id,
    )
    session.add_all([sales_invoice_closed, sales_invoice_cancelled])
    session.flush()
    session.add(
        SalesInvoiceSource(
            sales_invoice_id=sales_invoice_closed.id,
            firm_id=firm_id,
            source_document_type="DELIVERY_NOTE",
            source_document_id=delivery_note_completed.id,
            source_document_number=delivery_note_completed.delivery_note_number,
            source_document_date=delivery_note_completed.delivery_date,
            customer_id=customers[0].id,
            branch_id=branch.id,
            created_by=actor_id,
            updated_by=actor_id,
        )
    )
    session.add_all(
        [
            SalesInvoiceLine(
                sales_invoice_id=sales_invoice_closed.id,
                firm_id=firm_id,
                line_number=1,
                source_document_type="DELIVERY_NOTE",
                source_document_id=delivery_note_completed.id,
                source_document_number=delivery_note_completed.delivery_note_number,
                source_document_line_id=so_line1.id,
                source_document_line_number=1,
                product_id=products[0].id,
                description=products[0].name,
                delivered_quantity=Decimal("40"),
                already_invoiced_quantity=Decimal("25"),
                current_invoice_quantity=Decimal("15"),
                unit_price=Decimal("95"),
                gross_amount=Decimal("1425"),
                tax_profile_id=tax_profile.id,
                tax_amount=Decimal("256.5"),
                net_amount=Decimal("1681.5"),
                packaging_type_id=pkg_unit.id,
                order_uom_id=uom_unit.id,
                invoice_uom_id=uom_unit.id,
                conversion_factor=Decimal("1"),
                conversion_version=1,
                warehouse_id=warehouse.id,
                storage_node_id=default_storage.id,
                created_by=actor_id,
                updated_by=actor_id,
            ),
            SalesInvoiceLine(
                sales_invoice_id=sales_invoice_closed.id,
                firm_id=firm_id,
                line_number=2,
                source_document_type="DELIVERY_NOTE",
                source_document_id=delivery_note_completed.id,
                source_document_number=delivery_note_completed.delivery_note_number,
                source_document_line_id=so_line2.id,
                source_document_line_number=2,
                product_id=products[1].id,
                description=products[1].name,
                delivered_quantity=Decimal("30"),
                already_invoiced_quantity=Decimal("20"),
                current_invoice_quantity=Decimal("10"),
                unit_price=Decimal("125"),
                gross_amount=Decimal("1250"),
                tax_profile_id=tax_profile.id,
                tax_amount=Decimal("225"),
                net_amount=Decimal("1475"),
                packaging_type_id=pkg_unit.id,
                order_uom_id=uom_unit.id,
                invoice_uom_id=uom_unit.id,
                conversion_factor=Decimal("1"),
                conversion_version=1,
                warehouse_id=warehouse.id,
                storage_node_id=default_storage.id,
                created_by=actor_id,
                updated_by=actor_id,
            ),
        ]
    )

    _seed_document_framework(
        session=session,
        context=context,
        actor_id=actor_id,
        docs=(
            (
                "PURCHASE_ORDER",
                po_approved.id,
                po_approved.po_number,
                po_approved.purchase_date,
                po_approved.status,
                po_approved.grand_total,
            ),
            (
                "GOODS_RECEIPT",
                grn_completed.id,
                grn_completed.grn_number,
                grn_completed.receipt_date,
                grn_completed.status,
                grn_completed.grand_total,
            ),
            (
                "PURCHASE_INVOICE",
                purchase_invoice_approved.id,
                purchase_invoice_approved.invoice_number,
                purchase_invoice_approved.invoice_date,
                purchase_invoice_approved.status,
                purchase_invoice_approved.grand_total,
            ),
            (
                "PURCHASE_RETURN",
                purchase_return.id,
                purchase_return.return_number,
                purchase_return.return_date,
                purchase_return.status,
                purchase_return.grand_total,
            ),
            (
                "SALES_ORDER",
                sales_order_approved.id,
                sales_order_approved.order_number,
                sales_order_approved.order_date,
                sales_order_approved.status,
                sales_order_approved.grand_total,
            ),
            (
                "DELIVERY_NOTE",
                delivery_note_completed.id,
                delivery_note_completed.delivery_note_number,
                delivery_note_completed.delivery_date,
                delivery_note_completed.status,
                delivery_note_completed.grand_total,
            ),
            (
                "SALES_INVOICE",
                sales_invoice_approved.id,
                sales_invoice_approved.invoice_number,
                sales_invoice_approved.invoice_date,
                sales_invoice_approved.status,
                sales_invoice_approved.grand_total,
            ),
        ),
        sample_product=products[0],
        sample_uom=uom_unit,
        sample_tax_profile=tax_profile,
        branch_id=branch.id,
        warehouse_id=warehouse.id,
    )

    session.add_all(
        [
            AuditLog(
                action="CREATE",
                entity_type="purchase_orders",
                entity_id=po_approved.id,
                actor_id=actor_id,
                firm_id=firm_id,
                before_data=None,
                after_data={
                    "po_number": po_approved.po_number,
                    "status": po_approved.status,
                },
                ip_address="127.0.0.1",
                application_version="1.0.63",
            ),
            AuditLog(
                action="COMPLETE",
                entity_type="goods_receipts",
                entity_id=grn_completed.id,
                actor_id=actor_id,
                firm_id=firm_id,
                before_data={"status": "DRAFT"},
                after_data={"status": grn_completed.status},
                ip_address="127.0.0.1",
                application_version="1.0.63",
            ),
            AuditLog(
                action="APPROVE",
                entity_type="sales_invoices",
                entity_id=sales_invoice_approved.id,
                actor_id=actor_id,
                firm_id=firm_id,
                before_data={"status": "DRAFT"},
                after_data={"status": sales_invoice_approved.status},
                ip_address="127.0.0.1",
                application_version="1.0.63",
            ),
        ]
    )

    counts["uoms"] = _count_active(session, Uom)
    counts["packaging_types"] = _count_active(session, PackagingType)
    counts["uom_conversion_rules"] = _count_active(session, ConversionRule)
    counts["product_packaging_levels"] = _count_active(session, ProductPackagingLevel)
    counts["opening_stock_batches"] = _count_active(session, OpeningStockBatch)
    counts["inventories"] = _count_active(session, InventoryRecord)
    counts["inventory_transactions"] = _count_active(session, InventoryTransaction)
    counts["stock_ledger_entries"] = _count_active(session, StockLedgerEntry)
    counts["purchase_orders"] = _count_active(session, PurchaseOrder)
    counts["goods_receipts"] = _count_active(session, GoodsReceipt)
    counts["purchase_invoices"] = _count_active(session, PurchaseInvoice)
    counts["purchase_returns"] = _count_active(session, PurchaseReturn)
    counts["sales_orders"] = _count_active(session, SalesOrder)
    counts["delivery_notes"] = _count_active(session, DeliveryNote)
    counts["sales_invoices"] = _count_active(session, SalesInvoice)
    counts["document_lifecycle_events"] = _count_active(session, DocumentLifecycleEvent)
    return counts


def _create_inventory_transaction(
    *,
    session: Session,
    inventory: InventoryRecord,
    actor_id: UUID,
    transaction_type: str,
    reference_number: str,
    reference_type: str,
    transaction_date: date,
    quantity: Decimal,
    current_delta: Decimal,
    reserved_delta: Decimal,
    blocked_delta: Decimal,
    damaged_delta: Decimal,
    quarantine_delta: Decimal,
    in_transit_delta: Decimal,
    remarks: str | None,
    entered_quantity: Decimal | None = None,
    entered_uom_id: UUID | None = None,
    conversion_version: int | None = None,
) -> InventoryTransaction:
    prev_current = inventory.current_quantity
    prev_reserved = inventory.reserved_quantity
    prev_blocked = inventory.blocked_quantity
    prev_damaged = inventory.damaged_quantity
    prev_quarantine = inventory.quarantine_quantity
    prev_in_transit = inventory.in_transit_quantity
    prev_available = inventory.available_quantity

    new_current = prev_current + current_delta
    new_reserved = prev_reserved + reserved_delta
    new_blocked = prev_blocked + blocked_delta
    new_damaged = prev_damaged + damaged_delta
    new_quarantine = prev_quarantine + quarantine_delta
    new_in_transit = prev_in_transit + in_transit_delta
    new_available = (
        new_current - new_reserved - new_blocked - new_damaged - new_quarantine
    )

    inventory.current_quantity = new_current
    inventory.reserved_quantity = new_reserved
    inventory.blocked_quantity = new_blocked
    inventory.damaged_quantity = new_damaged
    inventory.quarantine_quantity = new_quarantine
    inventory.in_transit_quantity = new_in_transit
    inventory.available_quantity = new_available
    inventory.display_quantity = new_current
    inventory.last_transaction_at = transaction_date
    inventory.updated_by = actor_id

    transaction = InventoryTransaction(
        inventory_id=inventory.id,
        firm_id=inventory.firm_id,
        branch_id=inventory.branch_id,
        warehouse_id=inventory.warehouse_id,
        storage_node_id=inventory.storage_node_id,
        product_id=inventory.product_id,
        business_profile_id=inventory.business_profile_id,
        transaction_type=transaction_type,
        reference_number=reference_number,
        reference_type=reference_type,
        transaction_date=transaction_date,
        quantity=quantity,
        current_quantity_delta=current_delta,
        reserved_quantity_delta=reserved_delta,
        blocked_quantity_delta=blocked_delta,
        damaged_quantity_delta=damaged_delta,
        quarantine_quantity_delta=quarantine_delta,
        in_transit_quantity_delta=in_transit_delta,
        previous_current_quantity=prev_current,
        new_current_quantity=new_current,
        previous_reserved_quantity=prev_reserved,
        new_reserved_quantity=new_reserved,
        previous_available_quantity=prev_available,
        new_available_quantity=new_available,
        previous_blocked_quantity=prev_blocked,
        new_blocked_quantity=new_blocked,
        previous_damaged_quantity=prev_damaged,
        new_damaged_quantity=new_damaged,
        previous_quarantine_quantity=prev_quarantine,
        new_quarantine_quantity=new_quarantine,
        previous_in_transit_quantity=prev_in_transit,
        new_in_transit_quantity=new_in_transit,
        remarks=remarks,
        entered_quantity=entered_quantity,
        entered_uom_id=entered_uom_id,
        conversion_version=conversion_version,
        created_by=actor_id,
        updated_by=actor_id,
    )
    session.add(transaction)
    session.flush()
    session.add(
        StockLedgerEntry(
            transaction_id=transaction.id,
            inventory_id=inventory.id,
            firm_id=inventory.firm_id,
            branch_id=inventory.branch_id,
            warehouse_id=inventory.warehouse_id,
            storage_node_id=inventory.storage_node_id,
            product_id=inventory.product_id,
            business_profile_id=inventory.business_profile_id,
            transaction_type=transaction.transaction_type,
            reference_number=reference_number,
            reference_type=reference_type,
            transaction_date=transaction_date,
            quantity=quantity,
            current_quantity_delta=current_delta,
            reserved_quantity_delta=reserved_delta,
            blocked_quantity_delta=blocked_delta,
            damaged_quantity_delta=damaged_delta,
            quarantine_quantity_delta=quarantine_delta,
            in_transit_quantity_delta=in_transit_delta,
            previous_current_quantity=prev_current,
            new_current_quantity=new_current,
            previous_reserved_quantity=prev_reserved,
            new_reserved_quantity=new_reserved,
            previous_available_quantity=prev_available,
            new_available_quantity=new_available,
            previous_blocked_quantity=prev_blocked,
            new_blocked_quantity=new_blocked,
            previous_damaged_quantity=prev_damaged,
            new_damaged_quantity=new_damaged,
            previous_quarantine_quantity=prev_quarantine,
            new_quarantine_quantity=new_quarantine,
            previous_in_transit_quantity=prev_in_transit,
            new_in_transit_quantity=new_in_transit,
            remarks=remarks,
            original_quantity=entered_quantity,
            original_uom_id=entered_uom_id,
            base_quantity=quantity,
            created_by=actor_id,
            updated_by=actor_id,
        )
    )
    return transaction


def _seed_document_framework(
    *,
    session: Session,
    context: FirmContext,
    actor_id: UUID,
    docs: tuple[tuple[str, UUID, str, date, str, Decimal], ...],
    sample_product: Product,
    sample_uom: Uom,
    sample_tax_profile: TaxProfile,
    branch_id: UUID,
    warehouse_id: UUID,
) -> None:
    type_rows: dict[str, DocumentTypeDefinition] = {}
    for code, name in (
        ("PURCHASE_ORDER", "Purchase Order"),
        ("GOODS_RECEIPT", "Goods Receipt Note"),
        ("PURCHASE_INVOICE", "Purchase Invoice"),
        ("PURCHASE_RETURN", "Purchase Return"),
        ("SALES_ORDER", "Sales Order"),
        ("DELIVERY_NOTE", "Delivery Note"),
        ("SALES_INVOICE", "Sales Invoice"),
    ):
        row = DocumentTypeDefinition(
            firm_id=context.firm.id,
            code=code,
            name=name,
            description=f"{name} document framework definition.",
            category="TRANSACTION",
            is_active=True,
            configuration={"seeded": True},
            created_by=actor_id,
            updated_by=actor_id,
        )
        session.add(row)
        session.flush()
        type_rows[code] = row
        for order, state in enumerate(
            ("DRAFT", "APPROVED", "COMPLETED", "CANCELLED", "CLOSED"), start=1
        ):
            session.add(
                DocumentStateDefinition(
                    firm_id=context.firm.id,
                    document_type_id=row.id,
                    code=state,
                    name=state.title(),
                    sort_order=order,
                    is_default=state == "DRAFT",
                    is_terminal=state in {"CANCELLED", "CLOSED", "COMPLETED"},
                    allows_edit=state == "DRAFT",
                    allows_print=True,
                    allows_email=True,
                    allows_export_pdf=True,
                    transition_rules=None,
                    is_active=True,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
        session.add(
            DocumentNumberingRule(
                firm_id=context.firm.id,
                document_type_id=row.id,
                code=f"{code}_STD",
                name=f"{name} Standard Rule",
                prefix=code.split("_")[0],
                suffix=None,
                separator="/",
                include_financial_year=True,
                include_branch_code=True,
                include_company_code=False,
                auto_reset=True,
                manual_allowed=True,
                sequence_padding=4,
                next_sequence=10,
                is_default=True,
                is_active=True,
                configuration={"seeded": True},
                created_by=actor_id,
                updated_by=actor_id,
            )
        )

    for code, source_id, number, doc_date, status, amount in docs:
        doc_type = type_rows[code]
        header = DocumentHeader(
            firm_id=context.firm.id,
            document_type_id=doc_type.id,
            source_document_id=source_id,
            document_number=number,
            document_date=doc_date,
            reference=f"{code}-REF",
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            firm_name=context.firm.name,
            business_profile_name=context.profile.name,
            currency_code="INR",
            exchange_rate=Decimal("1"),
            status=status,
            remarks="Seeded document framework mirror entry.",
            approved_by=actor_id,
            created_by=actor_id,
            updated_by=actor_id,
        )
        session.add(header)
        session.flush()
        session.add(
            DocumentLine(
                firm_id=context.firm.id,
                document_header_id=header.id,
                line_number=1,
                product_id=sample_product.id,
                description=sample_product.name,
                uom_id=sample_uom.id,
                packaging="Unit",
                quantity="1",
                free_quantity="0",
                unit_price=str(amount),
                discount="0",
                tax_profile=sample_tax_profile.code,
                amount=str(amount),
                net_amount=str(amount),
                remarks="Seeded line mirror.",
                created_by=actor_id,
                updated_by=actor_id,
            )
        )
        session.add(
            DocumentTotal(
                firm_id=context.firm.id,
                document_header_id=header.id,
                subtotal=str(amount),
                discount="0",
                tax="0",
                charges="0",
                round_off="0",
                grand_total=str(amount),
                remarks="Seeded total mirror.",
                created_by=actor_id,
                updated_by=actor_id,
            )
        )
        session.add_all(
            [
                DocumentLifecycleEvent(
                    firm_id=context.firm.id,
                    document_type_id=doc_type.id,
                    source_document_id=source_id,
                    source_module_code=code,
                    document_number=number,
                    action="CREATE",
                    from_state=None,
                    to_state="DRAFT",
                    remarks="Document created.",
                    details_json={"seeded": True},
                    snapshot_json={"status": "DRAFT"},
                    actor_id=actor_id,
                    occurred_at=datetime.combine(
                        doc_date, datetime.min.time(), tzinfo=UTC
                    ),
                    created_by=actor_id,
                    updated_by=actor_id,
                ),
                DocumentLifecycleEvent(
                    firm_id=context.firm.id,
                    document_type_id=doc_type.id,
                    source_document_id=source_id,
                    source_module_code=code,
                    document_number=number,
                    action="STATE_CHANGE",
                    from_state="DRAFT",
                    to_state=status,
                    remarks=f"Seeded transition to {status}.",
                    details_json={"seeded": True},
                    snapshot_json={"status": status},
                    actor_id=actor_id,
                    approved_by=actor_id,
                    occurred_at=datetime.combine(
                        doc_date, datetime.min.time(), tzinfo=UTC
                    )
                    + timedelta(hours=1),
                    created_by=actor_id,
                    updated_by=actor_id,
                ),
            ]
        )


def _render_users_doc(logins: list[LoginRecord]) -> str:
    lines = [
        "# Development Users",
        "",
        f"All seeded development users use password `{DEVELOPMENT_PASSWORD}`.",
        "",
        "| Username | Role | Firm | Branch | Password | Description |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for record in sorted(
        logins, key=lambda item: (item.role, item.firm, item.username)
    ):
        lines.append(
            f"| {record.username} | {record.role} | {record.firm} | {record.branch} | "
            f"{DEVELOPMENT_PASSWORD} | {record.description} |"
        )
    lines.append("")
    return "\n".join(lines)


def _render_summary_doc(counts: Counter[str], notes: list[str]) -> str:
    display_order = (
        "firms",
        "branches",
        "warehouses",
        "storage_nodes",
        "uoms",
        "packaging_types",
        "uom_conversion_rules",
        "product_uom_configs",
        "product_packaging_levels",
        "territories",
        "routes",
        "route_types",
        "customers",
        "vendors",
        "categories",
        "products",
        "opening_stock_batches",
        "inventories",
        "inventory_transactions",
        "stock_ledger_entries",
        "purchase_orders",
        "goods_receipts",
        "purchase_invoices",
        "purchase_returns",
        "sales_orders",
        "delivery_notes",
        "sales_invoices",
        "document_lifecycle_events",
        "users",
        "tax_systems",
        "tax_components",
        "tax_profiles",
        "tax_rules",
        "tax_execution_logs",
    )
    lines = [
        "# Development Data Summary",
        "",
        "| Entity | Count |",
        "| --- | ---: |",
    ]
    for key in display_order:
        if key in counts:
            lines.append(f"| {key.replace('_', ' ').title()} | {counts[key]} |")
    if notes:
        lines.extend(["", "## Notes", ""])
        for note in notes:
            lines.append(f"- {note}")
    lines.append("")
    return "\n".join(lines)


def _print_summary(counts: Counter[str]) -> None:
    print("Development data generation completed.")
    for key in (
        "firms",
        "branches",
        "warehouses",
        "storage_nodes",
        "uoms",
        "packaging_types",
        "territories",
        "routes",
        "customers",
        "vendors",
        "products",
        "opening_stock_batches",
        "inventories",
        "inventory_transactions",
        "purchase_orders",
        "goods_receipts",
        "purchase_invoices",
        "purchase_returns",
        "sales_orders",
        "delivery_notes",
        "sales_invoices",
        "document_lifecycle_events",
        "users",
        "tax_profiles",
        "tax_rules",
        "tax_execution_logs",
    ):
        if key in counts:
            print(f"{key}: {counts[key]}")


def _count_active(session: Session, model: type[BaseEntity]) -> int:
    if hasattr(model, "is_deleted"):
        statement = (
            select(func.count()).select_from(model).where(model.is_deleted.is_(False))
        )
    else:
        statement = select(func.count()).select_from(model)
    return int(session.scalar(statement) or 0)


def _geo_for_city(
    geography: dict[str, Any], state_name: str, city_name: str
) -> dict[str, Any]:
    city = geography["cities"][(state_name, city_name)]
    district = next(
        district
        for (lookup_state, _), district in geography["districts"].items()
        if lookup_state == state_name and district.id == city.district_id
    )
    postal = next(
        postal
        for (lookup_state, _), postal in geography["postal_codes"].items()
        if lookup_state == state_name and postal.city_id == city.id
    )
    locality = next(
        locality
        for (lookup_city, _), locality in geography["localities"].items()
        if lookup_city == city_name and locality.postal_code_id == postal.id
    )
    return {
        "state": geography["states"][state_name],
        "district": district,
        "city": city,
        "postal": postal,
        "locality": locality,
    }


def _first_existing_profile_code(
    business_profiles: dict[str, BusinessProfile], candidates: tuple[str, ...]
) -> str:
    for code in candidates:
        if code in business_profiles:
            return code
    return "GENERIC"


def _allow_dev_password(password: str) -> None:
    if password != DEVELOPMENT_PASSWORD:
        raise ValidationError(
            "Only the development seed password is allowed in this utility."
        )


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", ".", value.strip().lower()).strip(".")


def _phone(index: int) -> str:
    return f"+9197{index:08d}"[:13]


def _pan(index: int) -> str:
    return f"APL{index:06d}Q"[:10]


def _gstin(index: int, state_name: str) -> str:
    state_codes = {
        "Telangana": "36",
        "Karnataka": "29",
        "Tamil Nadu": "33",
        "Kerala": "32",
        "Maharashtra": "27",
        "Gujarat": "24",
    }
    state_code = state_codes.get(state_name, "29")
    return f"{state_code}{_pan(index)}1Z{index % 9}".upper()[:15]


def _person_name(index: int) -> str:
    return (
        f"{FIRST_NAMES[index % len(FIRST_NAMES)]} {LAST_NAMES[index % len(LAST_NAMES)]}"
    )


def _branch_name_for_warehouse(branches: list[Branch], branch_id: UUID) -> str:
    for branch in branches:
        if branch.id == branch_id:
            return branch.name
    return "Unknown Branch"


def profiles_tax_code(context: FirmContext, fallback: str) -> str:
    """Return the tax group code a firm's profile implies."""
    return (
        fallback
        if fallback in context.tax_profiles
        else next(iter(context.tax_profiles))
    )


def _product_tax_code(index: int) -> str | None:
    if index % 15 == 0:
        return "HIST_VAT_4"
    if index % 12 == 0:
        return "EXEMPT"
    if index % 10 == 0:
        return "ZERO_RATED"
    if index % 9 == 0:
        return "GST_28"
    if index % 4 == 0:
        return "GST_18"
    if index % 3 == 0:
        return "GST_12"
    return None


def _attribute_value(
    definition: AttributeDefinition, index: int, template_name: str
) -> str | int | float | bool | date:
    key = f"{definition.code} {definition.name}".upper()
    data_type = definition.data_type.upper()
    if data_type == "DATE":
        if "EXPIRY" in key:
            return date(2026, 1, 1) + timedelta(days=index % 365)
        if "MANUFACTUR" in key:
            return date(2025, 1, 1) + timedelta(days=index % 180)
        return date(2025, 4, 1) + timedelta(days=index % 90)
    if data_type in {"NUMBER", "INTEGER"}:
        if "SHELF" in key:
            return 180 + (index % 365)
        if "WARRANTY" in key:
            return 12 + (index % 24)
        return 1 + (index % 100)
    if data_type in {"DECIMAL", "FLOAT"}:
        if "WEIGHT" in key:
            return float(0.5 + (index % 20) * 0.25)
        return float(1 + (index % 10))
    if data_type == "BOOLEAN":
        return True
    if "BATCH" in key:
        return f"BT-{index:05d}"
    if "EXPIRY" in key:
        return str(date(2026, 1, 1) + timedelta(days=index % 365))
    if "MANUFACTURER" in key:
        return BRANDS[index % len(BRANDS)]
    if "WARRANTY" in key:
        return f"{12 + index % 24} months"
    if "IMEI" in key:
        return f"35678901{index:06d}"[:15]
    if "SERIAL" in key:
        return f"SN-{index:08d}"
    if "FSSAI" in key:
        return f"FSSAI{index:08d}"
    if "DRUG" in key:
        return f"DRUG{index:08d}"
    if "ENGINE" in key:
        return f"ENG-{index:07d}"
    if "CHASSIS" in key:
        return f"CHS-{index:07d}"
    if "COLOR" in key:
        return ("Red", "Blue", "Black", "Silver", "White")[index % 5]
    if "SIZE" in key:
        return ("S", "M", "L", "XL")[index % 4]
    return f"{template_name} {definition.name}"


if __name__ == "__main__":
    main()
