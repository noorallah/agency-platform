"""Seed four demo firms across shared, schema, and database tenancy modes.

Masters first -- firms, users, branches, vendors, customers, products and
opening stock -- and then two financial years of trading on top, so the
demo data has a history rather than a single day's activity. History is
generated through the real services, so what it produces is what the
application itself would have produced.

    uv run python scripts/seed_multi_firm_demo.py
    uv run python scripts/seed_multi_firm_demo.py --history-years 3
    uv run python scripts/seed_multi_firm_demo.py --no-history

Re-running replaces each firm's trading history and leaves its masters
alone, so the demo can be refreshed without rebuilding everything.
"""

from __future__ import annotations

import argparse

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.api.dependencies.settings import get_settings
from app.batch_serial import models as batch_serial_models
from app.branches.models import Branch, BranchType, Warehouse, WarehouseStorageNode, WarehouseType
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
    BusinessFeature,
    BusinessModule,
    BusinessProfile,
    CategoryAttributeRule,
    FirmBusinessProfile,
    ProfileFeature,
    ProfileModule,
)
from app.core.database.engine import DatabaseManager
from app.core.tenancy import (
    DeploymentMode,
    FirmConnectionResolver,
    FirmSchemaResolver,
    MultiTenantDatabaseProvider,
    TenantContext,
    TenantStorageLifecycleService,
)
from app.core.utils.dates import utc_now
from app.customers.models import Customer
from app.customers.schemas import (
    CustomerAddressInput,
    CustomerContactInput,
    CustomerCreate,
    CustomerReceivableTransactionCreate,
    CustomerReceivableTransactionType,
)
from app.customers.schemas.customer import AddressType as CustomerAddressType
from app.customers.schemas.customer import CustomerStatus, CustomerType
from app.customers.services.customer_service import CustomerService
from app.firms.models import Firm, FirmStorageMapping
from app.firms.schemas import FirmCreate
from app.firms.services.firm_service import FirmService
from app.identity.models import PlatformAdmin, Role, User, UserFirm
from app.identity.schemas.api import UserCreate, UserFirmAssignment
from app.identity.services.identity_service import IdentityService
from app.inventory.models import OpeningStockBatch
from app.inventory.schemas import OpeningStockBatchCreate, OpeningStockLineCreate
from app.inventory.services import InventoryService
from app.products.models import Product, ProductCategory
from app.products.schemas import ProductAttributeInput, ProductCategoryCreate, ProductCreate
from app.products.schemas.product import ProductStatus, ProductType
from app.products.services.product_service import ProductService
from app.tax.models import TaxProfile, TaxSystem
from sqlalchemy.orm import Session

from app.uom.models import ConversionRule, Uom
from app.uom.schemas import ConversionRuleCreate
from app.uom.services import UomService
from app.vendors.models import Vendor, VendorCategory, VendorType
from app.vendors.schemas import (
    VendorAddressInput,
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
from generate_transaction_history import generate_history
from seed_tax_sample_data import TaxSeedContext, _seed_firm_tax_data

DEMO_PASSWORD = "DemoAdmin@12345"


@dataclass(frozen=True)
class FirmSeedTarget:
    blueprint: FirmBlueprint
    firm_id: UUID
    tenant: TenantContext


@dataclass(frozen=True)
class FirmRef:
    id: UUID
    code: str
    name: str


@dataclass(frozen=True)
class ProductSeed:
    code: str
    name: str
    short_name: str
    brand: str
    hsn_sac: str
    unit_label: str
    base_uom_code: str
    sales_uom_code: str
    #: How many base units make one sales unit -- a strip of ten tablets, a
    #: 25 kg bag. Seeds the conversion rule a sales line needs when it is
    #: raised in the sales unit; 1 when the two units are the same.
    sales_uom_factor: Decimal
    purchase_price: Decimal
    selling_price: Decimal
    mrp: Decimal
    #: Whether these goods cannot be taken in unidentified. Set on the products
    #: an industry actually traces -- a medicine that has to be recallable, a
    #: food with a use-by date -- and deliberately left off some of them, so
    #: the seeded data has untracked stock beside the tracked kind rather than
    #: making every row look the same.
    requires_batch: bool = False


@dataclass(frozen=True)
class FirmBlueprint:
    name: str
    code: str
    business_style: str
    profile_code: str
    city: str
    state: str
    postal_code: str
    deployment_mode: DeploymentMode
    schema_name: str | None
    database_name: str | None
    branch_code: str
    branch_name: str
    warehouse_code: str
    warehouse_name: str
    branch_phone_seed: int
    products: tuple[ProductSeed, ...]
    vendor_names: tuple[str, ...]
    customer_names: tuple[str, ...]


FIRM_BLUEPRINTS: tuple[FirmBlueprint, ...] = (
    FirmBlueprint(
        name="Medisphere Pharma Distribution Private Limited",
        code="MEDI01",
        business_style="Pharma distributor supplying pharmacies, hospitals, and clinics.",
        profile_code="PHARMACY",
        city="Hyderabad",
        state="Telangana",
        postal_code="500001",
        deployment_mode=DeploymentMode.SHARED,
        schema_name=None,
        database_name=None,
        branch_code="MEDI_HO",
        branch_name="Hyderabad Pharma Hub",
        warehouse_code="MEDI_DC",
        warehouse_name="Cold Chain Distribution Center",
        branch_phone_seed=101,
        vendor_names=(
            "Apex Labs Supply",
            "Curewell Generics",
            "Vital Biocare Depot",
        ),
        customer_names=(
            "LifeCare Pharmacy",
            "GreenCross Hospital",
            "CityMed Clinic",
        ),
        products=(
            ProductSeed(
                code="AMOX500",
                name="Amoxicillin 500mg",
                short_name="Amox 500",
                brand="Medisphere",
                hsn_sac="300410",
                unit_label="STRIP",
                base_uom_code="TABLET",
                sales_uom_code="STRIP",
                sales_uom_factor=Decimal("10"),
                purchase_price=Decimal("58"),
                selling_price=Decimal("72"),
                mrp=Decimal("75"),
                requires_batch=True,
            ),
            ProductSeed(
                code="PARA650",
                name="Paracetamol 650mg",
                short_name="Paracetamol 650",
                brand="HealthLine",
                hsn_sac="300450",
                unit_label="STRIP",
                base_uom_code="TABLET",
                sales_uom_code="STRIP",
                sales_uom_factor=Decimal("15"),
                purchase_price=Decimal("24"),
                selling_price=Decimal("31"),
                mrp=Decimal("35"),
                requires_batch=True,
            ),
            ProductSeed(
                code="VITC1000",
                name="Vitamin C 1000mg",
                short_name="Vit C 1000",
                brand="NutriAid",
                hsn_sac="300490",
                unit_label="BOX",
                base_uom_code="TABLET",
                sales_uom_code="BOX",
                sales_uom_factor=Decimal("30"),
                purchase_price=Decimal("145"),
                selling_price=Decimal("178"),
                mrp=Decimal("185"),
            ),
        ),
    ),
    FirmBlueprint(
        name="FreshRoute Food Supply Private Limited",
        code="FOOD01",
        business_style="Food and grocery wholesaler serving kirana stores and restaurants.",
        profile_code="FOOD",
        city="Bengaluru",
        state="Karnataka",
        postal_code="560001",
        deployment_mode=DeploymentMode.SHARED,
        schema_name=None,
        database_name=None,
        branch_code="FOOD_HO",
        branch_name="Bengaluru Food Distribution Hub",
        warehouse_code="FOOD_DC",
        warehouse_name="Temperature Controlled Grocery Warehouse",
        branch_phone_seed=201,
        vendor_names=(
            "Golden Grain Mills",
            "PureHarvest Foods",
            "FreshNest Agro",
        ),
        customer_names=(
            "Sri Lakshmi Kirana",
            "Spice Garden Restaurant",
            "Metro Mart Retail",
        ),
        products=(
            ProductSeed(
                code="SONA25KG",
                name="Sona Masoori Rice 25kg",
                short_name="Rice 25kg",
                brand="FreshRoute",
                hsn_sac="100630",
                unit_label="BAG",
                base_uom_code="KG",
                sales_uom_code="BAG",
                sales_uom_factor=Decimal("25"),
                purchase_price=Decimal("1120"),
                selling_price=Decimal("1245"),
                mrp=Decimal("1290"),
                requires_batch=True,
            ),
            ProductSeed(
                code="SUN5L",
                name="Sunflower Oil 5L",
                short_name="Sun Oil 5L",
                brand="PureHarvest",
                hsn_sac="151219",
                unit_label="BOTTLE",
                base_uom_code="L",
                sales_uom_code="BOTTLE",
                sales_uom_factor=Decimal("5"),
                purchase_price=Decimal("620"),
                selling_price=Decimal("675"),
                mrp=Decimal("699"),
                requires_batch=True,
            ),
            ProductSeed(
                code="BISC100",
                name="Tea Biscuits 100g",
                short_name="Biscuits 100g",
                brand="SnackJoy",
                hsn_sac="190531",
                unit_label="PACK",
                base_uom_code="GRAM",
                sales_uom_code="PACK",
                sales_uom_factor=Decimal("100"),
                purchase_price=Decimal("8"),
                selling_price=Decimal("10"),
                mrp=Decimal("10"),
            ),
        ),
    ),
    FirmBlueprint(
        name="MarketBridge Wholesale Traders Private Limited",
        code="WHOLE01",
        business_style="General trade and FMCG wholesaler with a dedicated schema in the main database.",
        profile_code="WHOLESALE",
        city="Chennai",
        state="Tamil Nadu",
        postal_code="600001",
        deployment_mode=DeploymentMode.SCHEMA,
        schema_name="wholesale_hub",
        database_name="agency_platform",
        branch_code="WHL_HO",
        branch_name="Chennai Wholesale Branch",
        warehouse_code="WHL_DC",
        warehouse_name="Bulk Goods Warehouse",
        branch_phone_seed=301,
        vendor_names=(
            "BrightHome Consumer Goods",
            "CleanWave Home Care",
            "DailyNeed Distributors",
        ),
        customer_names=(
            "Vijaya Super Stores",
            "Anand Agencies",
            "Classic Departmental Stores",
        ),
        products=(
            ProductSeed(
                code="DETER1K",
                name="Detergent Powder 1kg",
                short_name="Detergent 1kg",
                brand="CleanWave",
                hsn_sac="340220",
                unit_label="PACK",
                base_uom_code="KG",
                sales_uom_code="PACK",
                sales_uom_factor=Decimal("1"),
                purchase_price=Decimal("68"),
                selling_price=Decimal("84"),
                mrp=Decimal("89"),
            ),
            ProductSeed(
                code="SHAMP180",
                name="Shampoo Bottle 180ml",
                short_name="Shampoo 180ml",
                brand="GlowFresh",
                hsn_sac="330510",
                unit_label="BOTTLE",
                base_uom_code="ML",
                sales_uom_code="BOTTLE",
                sales_uom_factor=Decimal("180"),
                purchase_price=Decimal("92"),
                selling_price=Decimal("116"),
                mrp=Decimal("120"),
            ),
            ProductSeed(
                code="TOOTH150",
                name="Toothpaste 150g",
                short_name="Toothpaste 150g",
                brand="SmileCare",
                hsn_sac="330610",
                unit_label="TUBE",
                base_uom_code="GRAM",
                sales_uom_code="TUBE",
                sales_uom_factor=Decimal("150"),
                purchase_price=Decimal("46"),
                selling_price=Decimal("58"),
                mrp=Decimal("60"),
            ),
        ),
    ),
    FirmBlueprint(
        name="ElectroLink Appliances Distribution Private Limited",
        code="ELEC01",
        business_style="Electronics and appliances distributor with its own database and schema.",
        profile_code="ELECTRONICS",
        city="Pune",
        state="Maharashtra",
        postal_code="411001",
        deployment_mode=DeploymentMode.DATABASE,
        schema_name="electrolink_ops",
        database_name="agency_electrolink",
        branch_code="ELC_HO",
        branch_name="Pune Electronics Operations",
        warehouse_code="ELC_DC",
        warehouse_name="Appliance Fulfillment Center",
        branch_phone_seed=401,
        vendor_names=(
            "VoltEdge Appliances",
            "Nova Home Electronics",
            "Prime Power Devices",
        ),
        customer_names=(
            "City Digital World",
            "SmartHome Dealers",
            "QuickTech Retail",
        ),
        products=(
            ProductSeed(
                code="MIX500",
                name="Mixer Grinder 500W",
                short_name="Mixer 500W",
                brand="VoltEdge",
                hsn_sac="850940",
                unit_label="PIECE",
                base_uom_code="PIECE",
                sales_uom_code="PIECE",
                sales_uom_factor=Decimal("1"),
                purchase_price=Decimal("1450"),
                selling_price=Decimal("1780"),
                mrp=Decimal("1899"),
            ),
            ProductSeed(
                code="LED9W",
                name="LED Bulb 9W",
                short_name="LED Bulb 9W",
                brand="Nova",
                hsn_sac="853950",
                unit_label="PIECE",
                base_uom_code="PIECE",
                sales_uom_code="PIECE",
                sales_uom_factor=Decimal("1"),
                purchase_price=Decimal("72"),
                selling_price=Decimal("95"),
                mrp=Decimal("99"),
            ),
            ProductSeed(
                code="EXT5M",
                name="Extension Board 5 Meter",
                short_name="Extension 5M",
                brand="Prime Power",
                hsn_sac="854442",
                unit_label="PIECE",
                base_uom_code="PIECE",
                sales_uom_code="PIECE",
                sales_uom_factor=Decimal("1"),
                purchase_price=Decimal("260"),
                selling_price=Decimal("325"),
                mrp=Decimal("349"),
            ),
        ),
    ),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--history-years",
        type=int,
        default=2,
        help="Prior financial years of trading to generate, plus the current one.",
    )
    parser.add_argument(
        "--no-history",
        action="store_true",
        help="Seed masters only, the way this script behaved before.",
    )
    args = parser.parse_args()

    # Keep batch/lot/serial mappers loaded so inventory transaction FKs resolve.
    assert batch_serial_models is not None
    settings = get_settings()
    platform = DatabaseManager.from_settings(settings)
    lifecycle = TenantStorageLifecycleService(
        platform,
        settings.tenancy.connection_profiles,
    )
    provider = MultiTenantDatabaseProvider(
        platform,
        FirmConnectionResolver(platform, settings.tenancy.connection_profiles),
        FirmSchemaResolver(),
    )
    try:
        with platform.sessions(schema=platform.config.default_schema).session() as session:
            identity = IdentityService(session, settings)
            firm_service = FirmService(
                session,
                storage_lifecycle=lifecycle,
                tenancy_settings=settings.tenancy,
            )
            actor = _platform_admin(session)
            actor_id = actor.id
            firm_admin_role = _role_by_code(session, "FIRM_ADMIN")

            seeded_firms: list[Firm] = []
            for blueprint in FIRM_BLUEPRINTS:
                firm = _ensure_firm(session, firm_service, blueprint, actor_id)
                seeded_firms.append(firm)

            _ensure_firm_admins(
                session=session,
                identity=identity,
                firm_admin_role=firm_admin_role,
                actor_id=actor_id,
                firms=seeded_firms,
            )
            _ensure_master_user(
                session=session,
                identity=identity,
                firm_admin_role=firm_admin_role,
                actor_id=actor_id,
                firms=seeded_firms,
            )
            firm_targets = [
                FirmSeedTarget(
                    blueprint=next(
                        item for item in FIRM_BLUEPRINTS if item.code == firm.code
                    ),
                    firm_id=firm.id,
                    tenant=_tenant_context_for_firm(settings, firm),
                )
                for firm in seeded_firms
            ]

        for target in firm_targets:
            blueprint = target.blueprint
            firm = FirmRef(id=target.firm_id, name=blueprint.name, code=blueprint.code)
            tenant = target.tenant
            manager = provider.manager_for(tenant)
            schema_name = provider.schema_for(tenant)
            with manager.sessions(schema=schema_name).session() as tenant_session:
                _seed_business_profile_assignment(
                    tenant_session, target.firm_id, blueprint.profile_code, actor_id=actor_id
                )
                _seed_tax_data(tenant_session, firm, actor_id)
                _seed_branching(tenant_session, firm, blueprint, actor_id)
                _seed_vendors(tenant_session, firm, blueprint, actor_id)
                _seed_customers(tenant_session, firm, blueprint, actor_id)
                _seed_products(tenant_session, firm, blueprint, actor_id)
                _seed_inventory_opening_stock(tenant_session, firm, blueprint, actor_id)
                if not args.no_history:
                    tally = generate_history(
                        tenant_session,
                        firm_id=target.firm_id,
                        firm_code=blueprint.code,
                        years=args.history_years,
                        reset=True,
                    )
                    print(f"{blueprint.code} history: {tally.line()}")

        _print_summary(platform, settings)
    finally:
        provider.dispose()
        platform.dispose()
    return 0


def _platform_admin(session) -> User:
    user = session.scalar(select(User).where(User.email == "platform-admin@agency.local"))
    if user is None:
        raise RuntimeError("platform-admin@agency.local is required before seeding demo firms.")
    return user


def _role_by_code(session, code: str) -> Role:
    role = session.scalar(
        select(Role).where(Role.code == code, Role.is_deleted.is_(False))
    )
    if role is None:
        raise RuntimeError(f"System role '{code}' is missing.")
    return role


def _ensure_firm(
    session,
    firm_service: FirmService,
    blueprint: FirmBlueprint,
    actor_id: UUID,
) -> Firm:
    existing = session.scalar(
        select(Firm).where(Firm.code == blueprint.code, Firm.is_deleted.is_(False))
    )
    if existing is not None:
        return existing
    return firm_service.create(
        FirmCreate(
            name=blueprint.name,
            code=blueprint.code,
            address_line1=f"{blueprint.branch_name}, Main Road",
            city=blueprint.city,
            postal_code=blueprint.postal_code,
            country="IN",
            state=blueprint.state,
            contact_name=f"{blueprint.name} Admin Desk",
            contact_email=f"hello@{blueprint.code.lower()}.agency.local",
            contact_phone=_phone(blueprint.branch_phone_seed),
            currency_code="INR",
            financial_year_start=date(2026, 4, 1),
            deployment_mode=blueprint.deployment_mode,
            database_name=blueprint.database_name,
            schema_name=blueprint.schema_name,
            database_type="postgresql",
            notes=blueprint.business_style,
        ),
        actor_id=actor_id,
    )


def _ensure_firm_admins(
    *,
    session,
    identity: IdentityService,
    firm_admin_role: Role,
    actor_id: UUID,
    firms: list[Firm],
) -> None:
    for firm in firms:
        email = f"{firm.code.lower()}.admin@agency.local"
        user = _ensure_user(
            session,
            identity,
            actor_id,
            email=email,
            full_name=f"{firm.name} Admin",
            firm_scope=firm.id,
        )
        identity.set_user_firms(
            user.id,
            [UserFirmAssignment(firm_id=firm.id, is_primary=True, is_active=True)],
            actor_id,
        )
        identity.set_user_roles(
            user.id,
            [firm_admin_role.id],
            actor_id,
            firm_scope=firm.id,
        )


def _ensure_master_user(
    *,
    session,
    identity: IdentityService,
    firm_admin_role: Role,
    actor_id: UUID,
    firms: list[Firm],
) -> None:
    master = _ensure_user(
        session,
        identity,
        actor_id,
        email="master.ops@agency.local",
        full_name="Master Operations User",
        firm_scope=None,
    )
    identity.set_user_firms(
        master.id,
        [
            UserFirmAssignment(
                firm_id=firm.id,
                is_primary=index == 0,
                is_active=True,
            )
            for index, firm in enumerate(firms)
        ],
        actor_id,
    )
    if session.scalar(
        select(PlatformAdmin.id).where(
            PlatformAdmin.user_id == master.id,
            PlatformAdmin.is_deleted.is_(False),
        )
    ):
        # A platform admin already holds every permission, and firm-scoped role
        # administration deliberately refuses to touch one -- _get_user
        # excludes them, so a firm admin cannot manage a platform admin. The
        # first run assigns these roles before anything elevates the user; a
        # later run would hit that refusal and fail the whole seed. Skipping is
        # the honest answer: the roles would be redundant either way.
        return
    for firm in firms:
        identity.set_user_roles(
            master.id,
            [firm_admin_role.id],
            actor_id,
            firm_scope=firm.id,
        )


def _ensure_user(
    session,
    identity: IdentityService,
    actor_id: UUID,
    *,
    email: str,
    full_name: str,
    firm_scope: UUID | None,
) -> User:
    existing = session.scalar(select(User).where(User.email == email, User.is_deleted.is_(False)))
    if existing is not None:
        return existing
    return identity.create_user(
        UserCreate(
            email=email,
            full_name=full_name,
            password=DEMO_PASSWORD,
            is_active=True,
            force_password_change=False,
        ),
        actor_id=actor_id,
        firm_scope=firm_scope,
    )


def _tenant_context_for_firm(settings, firm: Firm) -> TenantContext:
    mapping = next(
        (
            row
            for row in firm.storage_mappings
            if row.is_active and not row.is_deleted
        ),
        None,
    )
    if mapping is None or mapping.deployment_mode == DeploymentMode.SHARED.value:
        return TenantContext(
            firm_id=firm.id,
            deployment_mode=DeploymentMode.SHARED,
            database_name=settings.tenancy.shared_database_name,
            schema_name=settings.tenancy.shared_schema_name,
            database_type=settings.tenancy.platform_database_type.value,
        )
    return TenantContext(
        firm_id=firm.id,
        deployment_mode=DeploymentMode(mapping.deployment_mode),
        database_name=mapping.database_name or settings.tenancy.shared_database_name,
        schema_name=mapping.schema_name or settings.tenancy.shared_schema_name,
        database_type=mapping.database_type,
    )


def _seed_business_profile_assignment(
    session,
    firm_id: UUID,
    profile_code: str,
    *,
    actor_id: UUID,
) -> None:
    profile = session.scalar(
        select(BusinessProfile).where(
            BusinessProfile.code == profile_code,
            BusinessProfile.is_deleted.is_(False),
            BusinessProfile.status == "ACTIVE",
        )
    )
    if profile is None:
        raise RuntimeError(f"Business profile '{profile_code}' is missing in tenant storage.")
    assignment = session.scalar(
        select(FirmBusinessProfile).where(
            FirmBusinessProfile.firm_id == firm_id,
            FirmBusinessProfile.is_deleted.is_(False),
        )
    )
    if assignment is None:
        session.add(
            FirmBusinessProfile(
                firm_id=firm_id,
                business_profile_id=profile.id,
                is_active=True,
                effective_from=utc_now(),
                notes=f"Seeded for {profile.name}",
                created_by=actor_id,
                updated_by=actor_id,
            )
        )
    else:
        assignment.business_profile_id = profile.id
        assignment.is_active = True
        assignment.notes = f"Seeded for {profile.name}"
        assignment.updated_by = actor_id
    session.commit()


def _seed_tax_data(session, firm: Firm, actor_id: UUID) -> None:
    existing = session.scalar(
        select(TaxSystem.id).where(
            TaxSystem.firm_id == firm.id,
            TaxSystem.is_deleted.is_(False),
        )
    )
    if existing is not None:
        return
    _seed_firm_tax_data(session, firm, TaxSeedContext(actor_id=actor_id))


def _seed_branching(session, firm: Firm, blueprint: FirmBlueprint, actor_id: UUID) -> None:
    service = BranchWarehouseService(session)
    branch_type = session.scalar(
        select(BranchType).where(
            BranchType.firm_id == firm.id,
            BranchType.code == "DISTRIBUTOR",
            BranchType.is_deleted.is_(False),
        )
    )
    if branch_type is None:
        branch_type = service.create_branch_type(
            BranchTypeWrite(
                code="DISTRIBUTOR",
                name="Distributor Branch",
                description="Seeded branch type for demo distributors.",
                is_active=True,
            ),
            firm_id=firm.id,
            actor_id=actor_id,
        )
    warehouse_type = session.scalar(
        select(WarehouseType).where(
            WarehouseType.firm_id == firm.id,
            WarehouseType.code == "DC",
            WarehouseType.is_deleted.is_(False),
        )
    )
    if warehouse_type is None:
        warehouse_type = service.create_warehouse_type(
            WarehouseTypeWrite(
                code="DC",
                name="Distribution Center",
                description="Seeded warehouse type for demo firms.",
                is_active=True,
            ),
            firm_id=firm.id,
            actor_id=actor_id,
        )
    branch = session.scalar(
        select(Branch).where(
            Branch.firm_id == firm.id,
            Branch.code == blueprint.branch_code,
            Branch.is_deleted.is_(False),
        )
    )
    if branch is None:
        branch = service.create_branch(
            BranchCreate(
                code=blueprint.branch_code,
                name=blueprint.branch_name,
                display_name=blueprint.branch_name,
                description=blueprint.business_style,
                branch_type_id=branch_type.id,
                email=f"{blueprint.code.lower()}.branch@agency.local",
                phone=_phone(blueprint.branch_phone_seed),
                mobile=_phone(blueprint.branch_phone_seed + 1),
                address_line1=f"{blueprint.city} Trade Centre",
                address_line2="Phase 1",
                timezone="Asia/Kolkata",
                currency_code="INR",
                gst_registration=True,
                pan=_pan(blueprint.branch_phone_seed),
                working_hours={"mon_sat": "09:00-19:00"},
                is_default=True,
                status=BranchStatus.ACTIVE,
            ),
            firm_id=firm.id,
            actor_id=actor_id,
        )
    warehouse = session.scalar(
        select(Warehouse).where(
            Warehouse.firm_id == firm.id,
            Warehouse.code == blueprint.warehouse_code,
            Warehouse.is_deleted.is_(False),
        )
    )
    if warehouse is None:
        warehouse = service.create_warehouse(
            WarehouseCreate(
                branch_id=branch.id,
                code=blueprint.warehouse_code,
                name=blueprint.warehouse_name,
                display_name=blueprint.warehouse_name,
                description=f"{blueprint.business_style} warehouse",
                warehouse_type_id=warehouse_type.id,
                address_line1=f"{blueprint.city} Logistics Park",
                address_line2="Warehouse Block A",
                capacity=Decimal("2500"),
                capacity_unit="KG",
                is_default=True,
                temperature_controlled=blueprint.profile_code in {"PHARMACY", "FOOD"},
                cold_storage=blueprint.profile_code in {"PHARMACY", "FOOD"},
                has_receiving_area=True,
                has_dispatch_area=True,
                has_returns_area=True,
                has_loading_dock=True,
                status=WarehouseStatus.ACTIVE,
            ),
            firm_id=firm.id,
            actor_id=actor_id,
        )
    _ensure_storage_node(
        session,
        service,
        warehouse_id=warehouse.id,
        code="RECV",
        name="Receiving Area",
        node_type=StorageNodeType.RECEIVING_AREA,
        actor_id=actor_id,
    )
    main_area = _ensure_storage_node(
        session,
        service,
        warehouse_id=warehouse.id,
        code="MAIN",
        name="Main Storage Area",
        node_type=StorageNodeType.STORAGE_AREA,
        actor_id=actor_id,
    )
    _ensure_storage_node(
        session,
        service,
        warehouse_id=warehouse.id,
        parent_id=main_area.id,
        code="BIN-A1",
        name="Bin A1",
        node_type=StorageNodeType.BIN,
        actor_id=actor_id,
    )


def _ensure_storage_node(
    session,
    service: BranchWarehouseService,
    *,
    warehouse_id: UUID,
    code: str,
    name: str,
    node_type: StorageNodeType,
    actor_id: UUID,
    parent_id: UUID | None = None,
) -> WarehouseStorageNode:
    row = session.scalar(
        select(WarehouseStorageNode).where(
            WarehouseStorageNode.warehouse_id == warehouse_id,
            WarehouseStorageNode.code == code,
            WarehouseStorageNode.is_deleted.is_(False),
        )
    )
    if row is not None:
        return row
    return service.create_storage_node(
        StorageNodeCreate(
            warehouse_id=warehouse_id,
            parent_id=parent_id,
            node_type=node_type,
            code=code,
            name=name,
            description=f"Seeded {name.lower()} node.",
            sort_order=0,
            is_active=True,
        ),
        firm_scope=None,
        actor_id=actor_id,
    )


def _seed_vendors(session, firm: Firm, blueprint: FirmBlueprint, actor_id: UUID) -> None:
    service = VendorService(session)
    category = session.scalar(
        select(VendorCategory).where(
            VendorCategory.firm_id == firm.id,
            VendorCategory.code == "SUPPLIER",
            VendorCategory.is_deleted.is_(False),
        )
    )
    if category is None:
        category = service.create_category(
            VendorCategoryWrite(
                code="SUPPLIER",
                name="Supplier",
                description="Seeded supplier category.",
                is_active=True,
            ),
            firm_id=firm.id,
            actor_id=actor_id,
        )
    vendor_type = session.scalar(
        select(VendorType).where(
            VendorType.firm_id == firm.id,
            VendorType.code == "DISTRIBUTOR",
            VendorType.is_deleted.is_(False),
        )
    )
    if vendor_type is None:
        vendor_type = service.create_type(
            VendorTypeWrite(
                code="DISTRIBUTOR",
                name="Distributor Supplier",
                description="Seeded distributor supplier type.",
                is_active=True,
            ),
            firm_id=firm.id,
            actor_id=actor_id,
        )
    profile = _business_profile(session, blueprint.profile_code)
    for index, vendor_name in enumerate(blueprint.vendor_names, start=1):
        if session.scalar(
            select(Vendor.id).where(
                Vendor.firm_id == firm.id,
                Vendor.code == f"{firm.code}V{index:02d}",
                Vendor.is_deleted.is_(False),
            )
        ):
            continue
        service.create(
            VendorCreate(
                code=f"{firm.code}V{index:02d}",
                name=vendor_name,
                legal_name=f"{vendor_name} Private Limited",
                display_name=vendor_name,
                category_id=category.id,
                type_id=vendor_type.id,
                status=VendorStatus.ACTIVE,
                business_profile_id=profile.id,
                gst_registration=True,
                gstin=_gstin(firm.code, index),
                pan=_pan(index + 500),
                license_number=f"LIC-{firm.code}-{index:02d}",
                registration_number=f"REG-{firm.code}-{index:02d}",
                email=f"contact{index}@{firm.code.lower()}-vendors.local",
                phone=_phone(index + 500),
                mobile=_phone(index + 700),
                remarks=f"Seeded supplier for {blueprint.business_style.lower()}",
                business_attributes={"style": blueprint.business_style},
                contacts=[
                    VendorContactInput(
                        name=f"{vendor_name} Contact",
                        department="Sales",
                        designation="Key Account Manager",
                        phone=_phone(index + 800),
                        mobile=_phone(index + 900),
                        email=f"ka{index}@{firm.code.lower()}-vendors.local",
                        is_primary=True,
                        status="ACTIVE",
                    )
                ],
                addresses=[
                    VendorAddressInput(
                        address_type=VendorAddressType.HEAD_OFFICE,
                        address_line1=f"{10 + index} Supplier Street",
                        address_line2=blueprint.city,
                        is_primary=True,
                    )
                ],
                banking=[
                    VendorBankInput(
                        bank_name="State Bank of India",
                        account_name=vendor_name,
                        account_number=f"91{index:010d}",
                        ifsc="SBIN0001234",
                        branch=blueprint.city,
                        upi_id=f"{firm.code.lower()}vendor{index}@sbi",
                        is_primary=True,
                    )
                ],
                tax=[
                    VendorTaxInput(
                        gstin=_gstin(firm.code, index),
                        pan=_pan(index + 500),
                        tan=f"TAN{index:07d}",
                        extra_fields={"seeded": True},
                        is_primary=True,
                    )
                ],
                notes=[
                    VendorNoteInput(
                        note="Seeded strategic supplier for demo flows.",
                        note_type="GENERAL",
                    )
                ],
            ),
            firm_id=firm.id,
            actor_id=actor_id,
        )


def _seed_customers(session, firm: Firm, blueprint: FirmBlueprint, actor_id: UUID) -> None:
    service = CustomerService(session)
    for index, customer_name in enumerate(blueprint.customer_names, start=1):
        if session.scalar(
            select(Customer.id).where(
                Customer.firm_id == firm.id,
                Customer.code == f"{firm.code}C{index:02d}",
                Customer.is_deleted.is_(False),
            )
        ):
            continue
        customer = service.create(
            CustomerCreate(
                code=f"{firm.code}C{index:02d}",
                customer_type=CustomerType.BUSINESS,
                name=customer_name,
                display_name=customer_name,
                gst_number=_gstin(f"{firm.code}C", index),
                pan_number=_pan(index + 900),
                email=f"accounts{index}@{firm.code.lower()}-customers.local",
                phone=_phone(index + 1000),
                alternate_phone=_phone(index + 1100),
                website=f"https://{firm.code.lower()}-customer{index}.example.local",
                credit_limit=Decimal("250000"),
                opening_balance=Decimal("0"),
                payment_terms_days=21,
                currency_code="INR",
                status=CustomerStatus.ACTIVE,
                notes=f"Seeded customer for {blueprint.business_style.lower()}",
                addresses=[
                    CustomerAddressInput(
                        address_type=CustomerAddressType.BILLING,
                        address_line1=f"{20 + index} Market Road",
                        address_line2="Central Business District",
                        area="Main Market",
                        city=blueprint.city,
                        district=blueprint.city,
                        state=blueprint.state,
                        country="IN",
                        postal_code=blueprint.postal_code,
                        is_default_billing=True,
                        is_default_shipping=True,
                    )
                ],
                contacts=[
                    CustomerContactInput(
                        name=f"{customer_name} Procurement",
                        designation="Purchase Manager",
                        mobile=_phone(index + 1200),
                        email=f"buyer{index}@{firm.code.lower()}-customers.local",
                        department="Procurement",
                        is_primary=True,
                    )
                ],
            ),
            firm_id=firm.id,
            actor_id=actor_id,
        )
        if index == 1:
            service.post_receivable_transaction(
                customer.id,
                CustomerReceivableTransactionCreate(
                    transaction_type=CustomerReceivableTransactionType.INVOICE,
                    transaction_date=utc_now().date(),
                    amount=Decimal("50000"),
                    reference_type="SEED_INVOICE",
                    reference_number=f"SI-DEMO-{firm.code}-001",
                    remarks="Seeded receivable invoice balance.",
                ),
                firm_scope=firm.id,
                actor_id=actor_id,
            )
            service.post_receivable_transaction(
                customer.id,
                CustomerReceivableTransactionCreate(
                    transaction_type=CustomerReceivableTransactionType.RECEIPT,
                    transaction_date=utc_now().date(),
                    amount=Decimal("20000"),
                    reference_type="SEED_RECEIPT",
                    reference_number=f"RCPT-DEMO-{firm.code}-001",
                    remarks="Seeded customer receipt allocation.",
                ),
                firm_scope=firm.id,
                actor_id=actor_id,
            )
        elif index == 2:
            service.post_receivable_transaction(
                customer.id,
                CustomerReceivableTransactionCreate(
                    transaction_type=CustomerReceivableTransactionType.ADVANCE_RECEIPT,
                    transaction_date=utc_now().date(),
                    amount=Decimal("15000"),
                    reference_type="SEED_ADVANCE",
                    reference_number=f"ADV-DEMO-{firm.code}-001",
                    remarks="Seeded unapplied customer advance.",
                ),
                firm_scope=firm.id,
                actor_id=actor_id,
            )
        elif index == 3:
            service.post_receivable_transaction(
                customer.id,
                CustomerReceivableTransactionCreate(
                    transaction_type=CustomerReceivableTransactionType.INVOICE,
                    transaction_date=utc_now().date(),
                    amount=Decimal("12000"),
                    reference_type="SEED_INVOICE",
                    reference_number=f"SI-DEMO-{firm.code}-003",
                    remarks="Seeded receivable invoice.",
                ),
                firm_scope=firm.id,
                actor_id=actor_id,
            )
            service.post_receivable_transaction(
                customer.id,
                CustomerReceivableTransactionCreate(
                    transaction_type=CustomerReceivableTransactionType.CREDIT_NOTE,
                    transaction_date=utc_now().date(),
                    amount=Decimal("3000"),
                    reference_type="SEED_CREDIT_NOTE",
                    reference_number=f"CN-DEMO-{firm.code}-003",
                    remarks="Seeded credit note adjustment.",
                ),
                firm_scope=firm.id,
                actor_id=actor_id,
            )


def _seed_business_framework(session, blueprint: FirmBlueprint, actor_id: UUID) -> dict[str, AttributeDefinition]:
    profile = _business_profile(session, blueprint.profile_code)
    feature_definitions = {
        "BARCODE": {"name": "Barcode", "category": "PRODUCT", "default_enabled": True},
        "QR_CODE": {"name": "QR Code", "category": "PRODUCT", "default_enabled": True},
        "ATTACHMENTS": {"name": "Product Attachments", "category": "PRODUCT", "default_enabled": True},
        "EXPIRY_TRACKING": {"name": "Expiry Tracking", "category": "INVENTORY", "default_enabled": True},
        "SERIAL_TRACKING": {"name": "Serial Tracking", "category": "INVENTORY", "default_enabled": False},
    }
    for code, payload in feature_definitions.items():
        feature = session.scalar(
            select(BusinessFeature).where(
                BusinessFeature.code == code,
                BusinessFeature.is_deleted.is_(False),
            )
        )
        if feature is None:
            feature = BusinessFeature(
                code=code,
                name=payload["name"],
                description=f"Seeded feature for {blueprint.profile_code.lower()} demo flows.",
                category=payload["category"],
                default_enabled=payload["default_enabled"],
                is_active=True,
                created_by=actor_id,
                updated_by=actor_id,
            )
            session.add(feature)
            session.flush()
        else:
            feature.name = payload["name"]
            feature.category = payload["category"]
            feature.default_enabled = payload["default_enabled"]
            feature.is_active = True
            feature.updated_by = actor_id

    module_definitions = {
        "PRODUCT_MASTER": {
            "name": "Product Master",
            "route": "products",
            "default_enabled": True,
        },
        "INVENTORY_CONTROL": {
            "name": "Inventory Control",
            "route": "inventory",
            "default_enabled": True,
        },
        "CUSTOMER_RECEIVABLES": {
            "name": "Customer Receivables",
            "route": "customers",
            "default_enabled": True,
        },
    }
    for code, payload in module_definitions.items():
        module = session.scalar(
            select(BusinessModule).where(
                BusinessModule.code == code,
                BusinessModule.is_deleted.is_(False),
            )
        )
        if module is None:
            module = BusinessModule(
                code=code,
                name=payload["name"],
                description=f"Seeded module for {blueprint.profile_code.lower()} demo flows.",
                ui_route=payload["route"],
                default_enabled=payload["default_enabled"],
                is_active=True,
                created_by=actor_id,
                updated_by=actor_id,
            )
            session.add(module)
            session.flush()
        else:
            module.name = payload["name"]
            module.ui_route = payload["route"]
            module.default_enabled = payload["default_enabled"]
            module.is_active = True
            module.updated_by = actor_id

    # BATCH_TRACKING goes with EXPIRY_TRACKING for the two industries that
    # trace their goods: a medicine has to be recallable and a food has a
    # use-by date, and neither is answerable without knowing which delivery a
    # unit came from. Without it seeded here no demo firm could use batches at
    # all, so nothing in the demo data exercised batch-grained stock.
    enabled_features = {
        "PHARMACY": {
            "BARCODE",
            "QR_CODE",
            "ATTACHMENTS",
            "EXPIRY_TRACKING",
            "BATCH_TRACKING",
        },
        "FOOD": {
            "BARCODE",
            "QR_CODE",
            "ATTACHMENTS",
            "EXPIRY_TRACKING",
            "BATCH_TRACKING",
        },
        "WHOLESALE": {"BARCODE", "ATTACHMENTS"},
        "ELECTRONICS": {"BARCODE", "QR_CODE", "ATTACHMENTS"},
    }.get(blueprint.profile_code, {"BARCODE", "ATTACHMENTS"})
    for code in feature_definitions:
        relationship = session.scalar(
            select(ProfileFeature).where(
                ProfileFeature.business_profile_id == profile.id,
                ProfileFeature.feature_id == session.scalar(
                    select(BusinessFeature.id).where(
                        BusinessFeature.code == code,
                        BusinessFeature.is_deleted.is_(False),
                    )
                ),
                ProfileFeature.is_deleted.is_(False),
            )
        )
        if relationship is None:
            relationship = ProfileFeature(
                business_profile_id=profile.id,
                feature_id=session.scalar(
                    select(BusinessFeature.id).where(
                        BusinessFeature.code == code,
                        BusinessFeature.is_deleted.is_(False),
                    )
                ),
                is_enabled=code in enabled_features,
                configuration={"seeded": True},
                created_by=actor_id,
                updated_by=actor_id,
            )
            session.add(relationship)
        else:
            relationship.is_enabled = code in enabled_features
            relationship.configuration = {"seeded": True}
            relationship.updated_by = actor_id

    enabled_modules = {
        "PHARMACY": {"PRODUCT_MASTER", "INVENTORY_CONTROL", "CUSTOMER_RECEIVABLES"},
        "FOOD": {"PRODUCT_MASTER", "INVENTORY_CONTROL", "CUSTOMER_RECEIVABLES"},
        "WHOLESALE": {"PRODUCT_MASTER", "INVENTORY_CONTROL", "CUSTOMER_RECEIVABLES"},
        "ELECTRONICS": {"PRODUCT_MASTER", "INVENTORY_CONTROL", "CUSTOMER_RECEIVABLES"},
    }.get(blueprint.profile_code, {"PRODUCT_MASTER", "INVENTORY_CONTROL", "CUSTOMER_RECEIVABLES"})
    for code in module_definitions:
        relationship = session.scalar(
            select(ProfileModule).where(
                ProfileModule.business_profile_id == profile.id,
                ProfileModule.module_id == session.scalar(
                    select(BusinessModule.id).where(
                        BusinessModule.code == code,
                        BusinessModule.is_deleted.is_(False),
                    )
                ),
                ProfileModule.is_deleted.is_(False),
            )
        )
        if relationship is None:
            relationship = ProfileModule(
                business_profile_id=profile.id,
                module_id=session.scalar(
                    select(BusinessModule.id).where(
                        BusinessModule.code == code,
                        BusinessModule.is_deleted.is_(False),
                    )
                ),
                is_enabled=code in enabled_modules,
                is_visible=code in enabled_modules,
                display_order=0,
                configuration={"seeded": True},
                created_by=actor_id,
                updated_by=actor_id,
            )
            session.add(relationship)
        else:
            relationship.is_enabled = code in enabled_modules
            relationship.is_visible = code in enabled_modules
            relationship.configuration = {"seeded": True}
            relationship.updated_by = actor_id

    attribute_definitions = {
        "BATCH_NUMBER": {
            "name": "Batch Number",
            "description": "Lot or batch reference for inventory tracking.",
            "data_type": "TEXT",
            "mandatory": False,
        },
        "EXPIRY_DATE": {
            "name": "Expiry Date",
            "description": "Shelf-life expiry date.",
            "data_type": "DATE",
            "mandatory": False,
        },
        "MANUFACTURER": {
            "name": "Manufacturer",
            "description": "Manufacturer or brand source.",
            "data_type": "TEXT",
            "mandatory": False,
        },
        "PACK_SIZE": {
            "name": "Pack Size",
            "description": "Display pack size or unit count.",
            "data_type": "TEXT",
            "mandatory": False,
        },
        "COUNTRY_OF_ORIGIN": {
            "name": "Country of Origin",
            "description": "Country from which the item originates.",
            "data_type": "TEXT",
            "mandatory": False,
        },
        "WARRANTY_MONTHS": {
            "name": "Warranty Months",
            "description": "Warranty period in months.",
            "data_type": "NUMBER",
            "mandatory": False,
        },
    }
    definitions: dict[str, AttributeDefinition] = {}
    for code, payload in attribute_definitions.items():
        definition = session.scalar(
            select(AttributeDefinition).where(
                AttributeDefinition.code == code,
                AttributeDefinition.is_deleted.is_(False),
            )
        )
        if definition is None:
            definition = AttributeDefinition(
                code=code,
                name=payload["name"],
                description=payload["description"],
                data_type=payload["data_type"],
                mandatory=payload["mandatory"],
                applicable_category="CORE_PRODUCTS",
                is_active=True,
                created_by=actor_id,
                updated_by=actor_id,
            )
            session.add(definition)
            session.flush()
        else:
            definition.name = payload["name"]
            definition.description = payload["description"]
            definition.data_type = payload["data_type"]
            definition.mandatory = payload["mandatory"]
            definition.applicable_category = "CORE_PRODUCTS"
            definition.is_active = True
            definition.updated_by = actor_id
        definitions[code] = definition

    rule_targets = {
        "PHARMACY": {
            "required": ["BATCH_NUMBER", "EXPIRY_DATE"],
            "optional": ["MANUFACTURER", "COUNTRY_OF_ORIGIN"],
        },
        "FOOD": {
            "required": ["PACK_SIZE", "COUNTRY_OF_ORIGIN"],
            "optional": ["EXPIRY_DATE", "MANUFACTURER"],
        },
        "WHOLESALE": {
            "required": [],
            "optional": ["PACK_SIZE", "COUNTRY_OF_ORIGIN"],
        },
        "ELECTRONICS": {
            "required": [],
            "optional": ["WARRANTY_MONTHS", "COUNTRY_OF_ORIGIN"],
        },
    }.get(blueprint.profile_code, {"required": [], "optional": ["COUNTRY_OF_ORIGIN"]})
    for code in rule_targets["required"] + rule_targets["optional"]:
        attribute_definition = definitions[code]
        rule = session.scalar(
            select(CategoryAttributeRule).where(
                CategoryAttributeRule.business_profile_id == profile.id,
                CategoryAttributeRule.category_code == "CORE_PRODUCTS",
                CategoryAttributeRule.attribute_definition_id == attribute_definition.id,
                CategoryAttributeRule.is_deleted.is_(False),
            )
        )
        if rule is None:
            rule = CategoryAttributeRule(
                business_profile_id=profile.id,
                category_code="CORE_PRODUCTS",
                attribute_definition_id=attribute_definition.id,
                is_mandatory=code in rule_targets["required"],
                validation_override={"seeded": True},
                created_by=actor_id,
                updated_by=actor_id,
            )
            session.add(rule)
        else:
            rule.is_mandatory = code in rule_targets["required"]
            rule.validation_override = {"seeded": True}
            rule.updated_by = actor_id

    session.commit()
    return definitions


def _product_attributes_for_profile(
    blueprint: FirmBlueprint,
    definitions: dict[str, AttributeDefinition],
    product: ProductSeed,
) -> list[ProductAttributeInput]:
    if blueprint.profile_code == "PHARMACY":
        return [
            ProductAttributeInput(
                attribute_definition_id=definitions["BATCH_NUMBER"].id,
                value=f"{product.code}-B1",
            ),
            ProductAttributeInput(
                attribute_definition_id=definitions["EXPIRY_DATE"].id,
                value=date(2028, 12, 31),
            ),
            ProductAttributeInput(
                attribute_definition_id=definitions["MANUFACTURER"].id,
                value=product.brand,
            ),
        ]
    if blueprint.profile_code == "FOOD":
        return [
            ProductAttributeInput(
                attribute_definition_id=definitions["PACK_SIZE"].id,
                value=product.unit_label,
            ),
            ProductAttributeInput(
                attribute_definition_id=definitions["COUNTRY_OF_ORIGIN"].id,
                value="India",
            ),
            ProductAttributeInput(
                attribute_definition_id=definitions["EXPIRY_DATE"].id,
                value=date(2027, 12, 31),
            ),
        ]
    if blueprint.profile_code == "WHOLESALE":
        return [
            ProductAttributeInput(
                attribute_definition_id=definitions["PACK_SIZE"].id,
                value=product.unit_label,
            ),
            ProductAttributeInput(
                attribute_definition_id=definitions["COUNTRY_OF_ORIGIN"].id,
                value="India",
            ),
        ]
    if blueprint.profile_code == "ELECTRONICS":
        return [
            ProductAttributeInput(
                attribute_definition_id=definitions["WARRANTY_MONTHS"].id,
                value=12,
            ),
            ProductAttributeInput(
                attribute_definition_id=definitions["COUNTRY_OF_ORIGIN"].id,
                value="India",
            ),
        ]
    return [
        ProductAttributeInput(
            attribute_definition_id=definitions["COUNTRY_OF_ORIGIN"].id,
            value="India",
        )
    ]


def _seed_products(session, firm: Firm, blueprint: FirmBlueprint, actor_id: UUID) -> None:
    service = ProductService(session)
    attribute_definitions = _seed_business_framework(session, blueprint, actor_id)
    category = session.scalar(
        select(ProductCategory).where(
            ProductCategory.firm_id == firm.id,
            ProductCategory.code == "CORE_PRODUCTS",
            ProductCategory.is_deleted.is_(False),
        )
    )
    if category is None:
        category = service.create_category(
            ProductCategoryCreate(
                code="CORE_PRODUCTS",
                name="Core Products",
                parent_id=None,
                is_active=True,
            ),
            firm_id=firm.id,
            actor_id=actor_id,
        )
    tax_profile = _tax_profile_for_firm(session, firm.id, blueprint.profile_code)
    uoms = _uom_map(session)
    for product in blueprint.products:
        existing = session.scalar(
            select(Product).where(
                Product.firm_id == firm.id,
                Product.code == product.code,
                Product.is_deleted.is_(False),
            )
        )
        if existing is not None:
            # Masters are left alone on a re-run, which is what lets the demo
            # be refreshed without rebuilding. The batch flags are the
            # exception: they are what decides whether history creates any
            # batches at all, so a store seeded before they existed would take
            # the new setting and produce nothing, silently.
            if (
                existing.track_batch != product.requires_batch
                or existing.require_batch_on_receipt != product.requires_batch
            ):
                existing.track_batch = product.requires_batch
                existing.require_batch_on_receipt = product.requires_batch
                existing.updated_by = actor_id
                session.commit()
            continue
        base_uom = uoms[product.base_uom_code]
        sales_uom = uoms[product.sales_uom_code]
        attributes = _product_attributes_for_profile(
            blueprint=blueprint,
            definitions=attribute_definitions,
            product=product,
        )
        service.create_product(
            ProductCreate(
                code=product.code,
                barcode=None,
                qr_code=None,
                name=product.name,
                short_name=product.short_name,
                description=f"Seeded demo product for {blueprint.business_style.lower()}",
                product_type=ProductType.STOCK_ITEM,
                category_id=category.id,
                sub_category_id=None,
                unit=product.unit_label,
                brand=product.brand,
                model=None,
                hsn_sac=product.hsn_sac,
                tax_profile_group_code=tax_profile.group_code,
                base_uom_id=base_uom.id,
                inventory_uom_id=base_uom.id,
                purchase_uom_id=base_uom.id,
                sales_uom_id=sales_uom.id,
                default_receiving_uom_id=base_uom.id,
                default_dispatch_uom_id=sales_uom.id,
                minimum_sales_uom_id=sales_uom.id,
                weight=None,
                volume=None,
                length=None,
                width=None,
                height=None,
                allow_fraction=False,
                allow_decimal=True,
                purchase_price=product.purchase_price,
                selling_price=product.selling_price,
                mrp=product.mrp,
                status=ProductStatus.ACTIVE,
                track_batch=product.requires_batch,
                # Only the receipt side. Opening stock cannot carry a batch --
                # `post_opening_stock_batch` has no batch to give it -- so a
                # product that also required one on issue could never ship the
                # stock it started with.
                require_batch_on_receipt=product.requires_batch,
                remarks=f"Seeded for {blueprint.profile_code.lower()} demo flows.",
                attributes=attributes,
                media=[],
            ),
            firm_id=firm.id,
            actor_id=actor_id,
        )
        _seed_sales_conversion_rule(
            session,
            firm=firm,
            product_code=product.code,
            from_uom=sales_uom,
            to_uom=base_uom,
            factor=product.sales_uom_factor,
            actor_id=actor_id,
        )


def _seed_sales_conversion_rule(
    session: Session,
    *,
    firm: FirmRef,
    product_code: str,
    from_uom: Uom,
    to_uom: Uom,
    factor: Decimal,
    actor_id: UUID,
) -> None:
    """Give a product the rule its own sales unit needs.

    Seeding 36 units is not seeding conversions. Every demo product sells in a
    unit it does not stock in -- strips of tablets, bags of kilos -- and with no
    rule the first sales line raised in the sales unit fails with "No active
    conversion rule is configured for this UOM pair". That is the correct
    refusal: guessing a factor of 1 would book ten tablets where a hundred left
    the shelf.

    The rule is scoped to the product, not the firm, because a strip is ten
    tablets of one medicine and fifteen of another. That also exercises the
    specificity ordering the conversion resolver applies.
    """
    if from_uom.id == to_uom.id:
        return
    product_id = session.scalar(
        select(Product.id).where(
            Product.firm_id == firm.id,
            Product.code == product_code,
            Product.is_deleted.is_(False),
        )
    )
    if product_id is None:
        return
    existing = session.scalar(
        select(ConversionRule.id).where(
            ConversionRule.firm_id == firm.id,
            ConversionRule.product_id == product_id,
            ConversionRule.from_uom_id == from_uom.id,
            ConversionRule.to_uom_id == to_uom.id,
            ConversionRule.is_deleted.is_(False),
        )
    )
    if existing is not None:
        return
    UomService(session).create_conversion_rule(
        ConversionRuleCreate(
            product_id=product_id,
            from_uom_id=from_uom.id,
            to_uom_id=to_uom.id,
            conversion_factor=factor,
            effective_from=date(2024, 4, 1),
            version=1,
            reason=(
                f"One {from_uom.code} is {factor} {to_uom.code} "
                f"for {product_code}."
            ),
        ),
        firm_scope=firm.id,
        actor_id=actor_id,
    )


def _seed_inventory_opening_stock(
    session,
    firm: FirmRef,
    blueprint: FirmBlueprint,
    actor_id: UUID,
) -> None:
    reference_number = f"OS-DEMO-{firm.code}"
    service = InventoryService(session)
    existing = session.scalar(
        select(OpeningStockBatch).where(
            OpeningStockBatch.firm_id == firm.id,
            OpeningStockBatch.reference_number == reference_number,
            OpeningStockBatch.is_deleted.is_(False),
        )
    )
    if existing is not None:
        if existing.status == "DRAFT":
            service.post_opening_stock_batch(
                existing.id,
                firm_scope=firm.id,
                actor_id=actor_id,
            )
        return

    branch = session.scalar(
        select(Branch).where(
            Branch.firm_id == firm.id,
            Branch.code == blueprint.branch_code,
            Branch.is_deleted.is_(False),
        )
    )
    warehouse = session.scalar(
        select(Warehouse).where(
            Warehouse.firm_id == firm.id,
            Warehouse.code == blueprint.warehouse_code,
            Warehouse.is_deleted.is_(False),
        )
    )
    if branch is None or warehouse is None:
        raise RuntimeError(
            f"Branch/warehouse not found for firm '{firm.code}' while seeding inventory."
        )

    product_codes = [item.code for item in blueprint.products]
    products = session.scalars(
        select(Product).where(
            Product.firm_id == firm.id,
            Product.code.in_(product_codes),
            Product.is_deleted.is_(False),
            Product.status == ProductStatus.ACTIVE.value,
        )
    ).all()
    product_by_code = {item.code: item for item in products}
    missing_codes = [code for code in product_codes if code not in product_by_code]
    if missing_codes:
        raise RuntimeError(
            f"Products missing for firm '{firm.code}' while seeding inventory: {missing_codes}"
        )

    lines = [
        OpeningStockLineCreate(
            product_id=product_by_code[product.code].id,
            quantity=Decimal("100") + Decimal(index * 25),
            entered_quantity=Decimal("100") + Decimal(index * 25),
            minimum_level=Decimal("20"),
            reorder_level=Decimal("30"),
            safety_stock=Decimal("10"),
            remarks="Seeded opening stock",
        )
        for index, product in enumerate(blueprint.products, start=1)
    ]
    batch = service.create_opening_stock_batch(
        OpeningStockBatchCreate(
            branch_id=branch.id,
            warehouse_id=warehouse.id,
            reference_number=reference_number,
            posting_date=date(2026, 4, 1),
            remarks=f"Seeded opening stock for {firm.code}.",
            lines=lines,
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    service.post_opening_stock_batch(batch.id, firm_scope=firm.id, actor_id=actor_id)


def _business_profile(session, profile_code: str) -> BusinessProfile:
    profile = session.scalar(
        select(BusinessProfile).where(
            BusinessProfile.code == profile_code,
            BusinessProfile.is_deleted.is_(False),
        )
    )
    if profile is None:
        raise RuntimeError(f"Business profile '{profile_code}' was not found.")
    return profile


def _tax_profile_for_firm(session, firm_id: UUID, profile_code: str) -> TaxProfile:
    tax_code = "GST_18_LOCAL"
    if profile_code == "PHARMACY":
        tax_code = "GST_12_LOCAL"
    elif profile_code == "FOOD":
        tax_code = "GST_5_LOCAL"
    row = session.scalar(
        select(TaxProfile).where(
            TaxProfile.firm_id == firm_id,
            TaxProfile.code == tax_code,
            TaxProfile.is_deleted.is_(False),
        )
    )
    if row is None:
        raise RuntimeError(f"Tax profile '{tax_code}' is missing for firm '{firm_id}'.")
    return row


def _uom_map(session) -> dict[str, Uom]:
    rows = session.scalars(
        select(Uom).where(
            Uom.code.in_(
                ["TABLET", "STRIP", "BOX", "KG", "BAG", "L", "BOTTLE", "GRAM", "PACK", "ML", "TUBE", "PIECE"]
            ),
            Uom.is_deleted.is_(False),
        )
    ).all()
    result = {row.code: row for row in rows}
    required = {"TABLET", "STRIP", "BOX", "KG", "BAG", "L", "BOTTLE", "GRAM", "PACK", "ML", "TUBE", "PIECE"}
    missing = required - set(result)
    if missing:
        raise RuntimeError(f"Required UOM codes are missing: {sorted(missing)}")
    return result


def _phone(seed: int) -> str:
    return f"+9199000{seed:05d}"


def _pan(seed: int) -> str:
    return f"ABCDE{seed:04d}F"


def _gstin(prefix: str, seed: int) -> str:
    normalized = "".join(character for character in prefix.upper() if character.isalnum())
    body = f"{normalized}{seed:02d}".ljust(10, "0")[:10]
    return f"29{body}{seed % 9 + 1}Z5"


def _print_summary(platform: DatabaseManager, settings: Any) -> None:
    with platform.sessions(schema=platform.config.default_schema).session() as session:
        firms = session.scalars(select(Firm).where(Firm.is_deleted.is_(False)).order_by(Firm.code.asc())).all()
        users = session.scalars(
            select(User).where(User.is_deleted.is_(False), User.email.like("%@agency.local")).order_by(User.email.asc())
        ).all()
        print("Seeded firms:")
        for firm in firms:
            mapping = next(
                (
                    row
                    for row in firm.storage_mappings
                    if row.is_active and not row.is_deleted
                ),
                None,
            )
            mode = mapping.deployment_mode if mapping is not None else DeploymentMode.SHARED.value
            database_name = (
                settings.tenancy.shared_database_name
                if mapping is None or mapping.database_name is None
                else mapping.database_name
            )
            schema_name = (
                settings.tenancy.shared_schema_name
                if mapping is None or mapping.schema_name is None
                else mapping.schema_name
            )
            print(
                f"- {firm.code}: mode={mode} database={database_name} schema={schema_name}"
            )
        print("Demo users:")
        for user in users:
            memberships = session.scalars(
                select(UserFirm).where(
                    UserFirm.user_id == user.id,
                    UserFirm.is_deleted.is_(False),
                )
            ).all()
            if not memberships:
                continue
            print(
                f"- {user.email}: firms={len(memberships)} password={DEMO_PASSWORD}"
            )


if __name__ == "__main__":
    raise SystemExit(main())
