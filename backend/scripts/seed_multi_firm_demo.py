"""Seed four demo firms across shared, schema, and database tenancy modes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.api.dependencies.settings import get_settings
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
from app.business.models import BusinessProfile, FirmBusinessProfile
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
)
from app.customers.schemas.customer import AddressType as CustomerAddressType
from app.customers.schemas.customer import CustomerStatus, CustomerType
from app.customers.services.customer_service import CustomerService
from app.firms.models import Firm, FirmStorageMapping
from app.firms.schemas import FirmCreate
from app.firms.services.firm_service import FirmService
from app.identity.models import Role, User, UserFirm
from app.identity.schemas.api import UserCreate, UserFirmAssignment
from app.identity.services.identity_service import IdentityService
from app.products.models import Product, ProductCategory
from app.products.schemas import ProductCategoryCreate, ProductCreate
from app.products.schemas.product import ProductStatus, ProductType
from app.products.services.product_service import ProductService
from app.tax.models import TaxProfile, TaxSystem
from app.uom.models import Uom
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
    purchase_price: Decimal
    selling_price: Decimal
    mrp: Decimal


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
                purchase_price=Decimal("58"),
                selling_price=Decimal("72"),
                mrp=Decimal("75"),
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
                purchase_price=Decimal("24"),
                selling_price=Decimal("31"),
                mrp=Decimal("35"),
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
                purchase_price=Decimal("1120"),
                selling_price=Decimal("1245"),
                mrp=Decimal("1290"),
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
                purchase_price=Decimal("620"),
                selling_price=Decimal("675"),
                mrp=Decimal("699"),
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
                purchase_price=Decimal("260"),
                selling_price=Decimal("325"),
                mrp=Decimal("349"),
            ),
        ),
    ),
)


def main() -> int:
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
        service.create(
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


def _seed_products(session, firm: Firm, blueprint: FirmBlueprint, actor_id: UUID) -> None:
    service = ProductService(session)
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
        if session.scalar(
            select(Product.id).where(
                Product.firm_id == firm.id,
                Product.code == product.code,
                Product.is_deleted.is_(False),
            )
        ):
            continue
        base_uom = uoms[product.base_uom_code]
        sales_uom = uoms[product.sales_uom_code]
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
                tax_profile_id=tax_profile.id,
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
                remarks=f"Seeded for {blueprint.profile_code.lower()} demo flows.",
                attributes=[],
                media=[],
            ),
            firm_id=firm.id,
            actor_id=actor_id,
        )


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
