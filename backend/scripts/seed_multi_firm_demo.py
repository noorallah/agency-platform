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
from uuid import UUID

from generate_transaction_history import generate_history, reset_history
from seed_tax_sample_data import TaxSeedContext, _seed_firm_tax_data
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.api.dependencies.settings import get_settings
from app.batch_serial import models as batch_serial_models
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
    BusinessFeature,
    BusinessModule,
    BusinessProfile,
    CategoryAttributeRule,
    FirmBusinessProfile,
    ProfileFeature,
    ProfileModule,
)
from app.commission.schemas import CommissionRuleCreate
from app.commission.services import CommissionService
from app.core.config.settings import Settings
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
from app.firms.models import Firm
from app.firms.schemas import FirmCreate
from app.firms.services.firm_service import FirmService
from app.identity.models import PlatformAdmin, Role, User, UserFirm
from app.identity.schemas.api import UserCreate, UserFirmAssignment
from app.identity.services.identity_service import IdentityService
from app.inventory.models import OpeningStockBatch
from app.inventory.schemas import OpeningStockBatchCreate, OpeningStockLineCreate
from app.inventory.services import InventoryService
from app.products.models import Product, ProductCategory
from app.products.schemas import (
    ProductAttributeInput,
    ProductCategoryCreate,
    ProductCreate,
)
from app.products.schemas.product import ProductStatus, ProductType
from app.products.services.product_service import ProductService
from app.sales.models import (
    BeatPlan,
    BeatPlanCustomerStop,
    SalesTerritoryNode,
    TerritoryCustomerAssignment,
    TerritoryRouteProfile,
    TerritoryWorkingDay,
)
from app.sales.schemas import (
    BeatPlanCreate,
    BeatPlanCustomerStopInput,
    BeatPlanType,
    BeatPlanUpdate,
    RouteProfileInput,
    RouteTypeWrite,
    TerritoryAssignCustomersRequest,
    TerritoryAssignSalesmenRequest,
    TerritoryCreate,
    TerritoryUpdate,
)
from app.sales.schemas.territory import SalesmanAssignmentInput, VisitFrequency
from app.sales.services import SalesTerritoryService
from app.tax.models import TaxProfile, TaxSystem
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

DEMO_PASSWORD = "DemoAdmin@12345"


@dataclass(frozen=True)
class FirmSeedTarget:
    """A firm to seed, and the store its rows belong in."""

    blueprint: FirmBlueprint
    firm_id: UUID
    tenant: TenantContext
    #: The firm's salespeople, resolved on the platform session because
    #: `users` lives only there. Carried rather than re-queried: the tenant
    #: pass runs on a session that cannot see the table at all.
    salesman_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True)
class FirmRef:
    """A firm reduced to what the seeder needs after it exists."""

    id: UUID
    code: str
    name: str


@dataclass(frozen=True)
class ProductSeed:
    """One product to create, before it has an id."""

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
    """A demo firm as written down, before anything is created."""

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
        business_style="Pharma distributor supplying pharmacies, hospitals, and "
        "clinics.",
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
        business_style="Food and grocery wholesaler serving kirana stores and "
        "restaurants.",
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
                base_uom_code="G",
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
        business_style="General trade and FMCG wholesaler with a dedicated schema in "
        "the main database.",
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
                base_uom_code="G",
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
        business_style="Electronics and appliances distributor with its own database "
        "and schema.",
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
    """Seed the demo firms and, unless asked not to, their trading history."""
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
        with platform.sessions(
            schema=platform.config.default_schema
        ).session() as session:
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
                # `FirmService.create` records the intent; the storage is built
                # by the explicit provisioning action. Reusing an already
                # provisioned firm hid this -- once the sample-data reset began
                # deleting firms, the new records were unprovisioned and every
                # request for them was refused. Re-running is safe.
                if blueprint.deployment_mode is not DeploymentMode.SHARED:
                    _firm, already = firm_service.provision(firm.id, actor_id)
                    if not already:
                        print(f"  provisioned {blueprint.code}")
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
            sales_team = _ensure_sales_team(
                session=session,
                identity=identity,
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
                    salesman_ids=sales_team.get(firm.id, ()),
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
                    tenant_session,
                    target.firm_id,
                    blueprint.profile_code,
                    actor_id=actor_id,
                )
                _seed_tax_data(tenant_session, firm, actor_id)
                _seed_branching(tenant_session, firm, blueprint, actor_id)
                _seed_vendors(tenant_session, firm, blueprint, actor_id)
                _seed_customers(tenant_session, firm, blueprint, actor_id)
                _seed_territories(
                    tenant_session,
                    firm,
                    blueprint,
                    actor_id,
                    salesman_ids=target.salesman_ids,
                )
                _seed_commission(
                    tenant_session,
                    firm,
                    actor_id,
                    salesman_ids=target.salesman_ids,
                )
                _seed_products(tenant_session, firm, blueprint, actor_id)
                # Clear the old trading history *before* laying down opening
                # stock, not after. `reset_history` counts opening stock as
                # history and deletes it, so seeding it first and resetting
                # second wiped the day-one shelf every single run: every store
                # had opening stock documents with no movements behind them,
                # and the trading below started from nothing.
                if not args.no_history:
                    reset_history(tenant_session, target.firm_id)
                _seed_inventory_opening_stock(tenant_session, firm, blueprint, actor_id)
                if not args.no_history:
                    tally = generate_history(
                        tenant_session,
                        firm_id=target.firm_id,
                        firm_code=blueprint.code,
                        years=args.history_years,
                        reset=False,
                    )
                    print(f"{blueprint.code} history: {tally.line()}")
                    # The notes, not only the counts. Every one of them is a
                    # document the run could not raise, and reading them is
                    # how a real dispatch defect was found -- this script
                    # printed the tally and dropped them on the floor, so a
                    # firm seeding differently from its siblings was
                    # invisible here while the standalone script showed it.
                    for note in tally.skipped[:5]:
                        print(f"  note: {note}")
                    if len(tally.skipped) > 5:
                        print(f"  note: ...and {len(tally.skipped) - 5} more")

        _print_summary(platform, settings)
    finally:
        provider.dispose()
        platform.dispose()
    return 0


def _platform_admin(session: Session) -> User:
    user = session.scalar(
        select(User).where(User.email == "platform-admin@agency.local")
    )
    if user is None:
        raise RuntimeError(
            "platform-admin@agency.local is required before seeding demo firms."
        )
    return user


def _role_by_code(session: Session, code: str) -> Role:
    role = session.scalar(
        select(Role).where(Role.code == code, Role.is_deleted.is_(False))
    )
    if role is None:
        raise RuntimeError(f"System role '{code}' is missing.")
    return role


def _ensure_firm(
    session: Session,
    firm_service: FirmService,
    blueprint: FirmBlueprint,
    actor_id: UUID,
) -> Firm:
    existing = session.scalar(
        select(Firm).where(Firm.code == blueprint.code, Firm.is_deleted.is_(False))
    )
    if existing is not None:
        # Backfilled where it is missing, never overwritten. A firm seeded
        # before this field carried a GSTIN has none, and **no invoice of
        # theirs can be registered with the tax authority at all** -- the
        # payload builder refuses it by name, which is right and is also a
        # demo that cannot show the feature working.
        if not (existing.gst_number or "").strip():
            existing.gst_number = _gstin(blueprint.code, 1)
            existing.updated_by = actor_id
            session.commit()
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
            # The firm's own GSTIN, in the same state (29) the seeded
            # customers carry. Without it no invoice could be registered with
            # the tax authority at all -- and the state has to match, because
            # every seeded sale is taxed CGST + SGST, which is an intra-state
            # supply. A firm in one state selling to a customer in another
            # with that tax on it is a document the portal refuses, and the
            # payload builder refuses it first, by name.
            gst_number=_gstin(blueprint.code, 1),
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
    session: Session,
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


def _ensure_sales_team(
    *,
    session: Session,
    identity: IdentityService,
    actor_id: UUID,
    firms: list[Firm],
) -> dict[UUID, tuple[UUID, ...]]:
    """Give each firm two salespeople, and return them by firm.

    Every store had **zero** rows in `territory_salesman_assignments` while
    every customer sat on a round, which made a whole chain unreachable rather
    than merely unseeded. `_validated_salesman` refuses any salesman who does
    not cover the customer's territory, so naming one was refused on every
    customer of every firm; `_derived_salesman` had nobody to derive; so no
    document ever carried a `salesman_id`. That is why the by-salesman reports
    and the create-time validation could both reach for `users` on the tenant
    session for months without anybody seeing a 503, and why the commission
    report can only report Unassigned.

    Two people rather than one, because the interesting cases are plural: a
    coverage screen with one salesman shows nothing about distribution, and a
    commission report with one earner cannot be read against another.
    """
    role = _role_by_code(session, "SALES_EXECUTIVE")
    team: dict[UUID, tuple[UUID, ...]] = {}
    for firm in firms:
        members: list[UUID] = []
        for index, given in enumerate(("Asha", "Bala"), start=1):
            user = _ensure_user(
                session,
                identity,
                actor_id,
                email=f"{firm.code.lower()}.sales{index}@agency.local",
                full_name=f"{given} ({firm.code} Sales)",
                firm_scope=firm.id,
            )
            identity.set_user_firms(
                user.id,
                [UserFirmAssignment(firm_id=firm.id, is_primary=True, is_active=True)],
                actor_id,
            )
            identity.set_user_roles(
                user.id,
                [role.id],
                actor_id,
                firm_scope=firm.id,
            )
            members.append(user.id)
        team[firm.id] = tuple(members)
    return team


def _ensure_master_user(
    *,
    session: Session,
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
    session: Session,
    identity: IdentityService,
    actor_id: UUID,
    *,
    email: str,
    full_name: str,
    firm_scope: UUID | None,
) -> User:
    existing = session.scalar(
        select(User).where(User.email == email, User.is_deleted.is_(False))
    )
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


def _tenant_context_for_firm(settings: Settings, firm: Firm) -> TenantContext:
    mapping = next(
        (row for row in firm.storage_mappings if row.is_active and not row.is_deleted),
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
    session: Session,
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
        raise RuntimeError(
            f"Business profile '{profile_code}' is missing in tenant storage."
        )
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


def _seed_tax_data(session: Session, firm: Firm, actor_id: UUID) -> None:
    existing = session.scalar(
        select(TaxSystem.id).where(
            TaxSystem.firm_id == firm.id,
            TaxSystem.is_deleted.is_(False),
        )
    )
    if existing is not None:
        return
    _seed_firm_tax_data(session, firm, TaxSeedContext(actor_id=actor_id))


def _seed_branching(
    session: Session, firm: Firm, blueprint: FirmBlueprint, actor_id: UUID
) -> None:
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
    session: Session,
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


def _seed_vendors(
    session: Session, firm: Firm, blueprint: FirmBlueprint, actor_id: UUID
) -> None:
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


def _seed_customers(
    session: Session, firm: Firm, blueprint: FirmBlueprint, actor_id: UUID
) -> None:
    service = CustomerService(session)
    for index, customer_name in enumerate(blueprint.customer_names, start=1):
        existing = session.scalar(
            select(Customer).where(
                Customer.firm_id == firm.id,
                Customer.code == f"{firm.code}C{index:02d}",
                Customer.is_deleted.is_(False),
            )
        )
        if existing is not None:
            # Backfilled where missing, never overwritten -- the third place
            # this run needed it. A customer seeded before the field carried a
            # GSTIN has none, and **no invoice to them can be registered with
            # the tax authority**, which is a demo that cannot show the
            # feature working rather than a defect in the feature.
            if not (existing.gst_number or "").strip():
                existing.gst_number = _gstin(f"{firm.code}C", index)
                existing.updated_by = actor_id
                session.commit()
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
        # No hand-posted balances here. These called
        # `CustomerService.post_receivable_transaction`, which moves a
        # customer's balance and writes no journal -- CLAUDE.md names it as the
        # older path the two books drift by every rupee of. It left MEDI01's
        # first customer owing 30,000 that the receivable control account had
        # never heard of, on every seed.
        #
        # Two financial years of generated trading give every customer a real
        # balance built from invoices and receipts that do post. If the demo
        # ever wants an unapplied advance to show, raise it through
        # `ReceiptService` so it reaches the ledger like any other money.


def _seed_business_framework(
    session: Session, blueprint: FirmBlueprint, actor_id: UUID
) -> dict[str, AttributeDefinition]:
    profile = _business_profile(session, blueprint.profile_code)
    feature_definitions = {
        "BARCODE": {"name": "Barcode", "category": "PRODUCT", "default_enabled": True},
        "QR_CODE": {"name": "QR Code", "category": "PRODUCT", "default_enabled": True},
        "ATTACHMENTS": {
            "name": "Product Attachments",
            "category": "PRODUCT",
            "default_enabled": True,
        },
        "EXPIRY_TRACKING": {
            "name": "Expiry Tracking",
            "category": "INVENTORY",
            "default_enabled": True,
        },
        "SERIAL_TRACKING": {
            "name": "Serial Tracking",
            "category": "INVENTORY",
            "default_enabled": False,
        },
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
                description=f"Seeded feature for {blueprint.profile_code.lower()} "
                f"demo flows.",
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
                description=f"Seeded module for {blueprint.profile_code.lower()} demo "
                f"flows.",
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
                ProfileFeature.feature_id
                == session.scalar(
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
    }.get(
        blueprint.profile_code,
        {"PRODUCT_MASTER", "INVENTORY_CONTROL", "CUSTOMER_RECEIVABLES"},
    )
    for code in module_definitions:
        relationship = session.scalar(
            select(ProfileModule).where(
                ProfileModule.business_profile_id == profile.id,
                ProfileModule.module_id
                == session.scalar(
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
                CategoryAttributeRule.attribute_definition_id
                == attribute_definition.id,
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


def _seed_territories(
    session: Session,
    firm: Firm,
    blueprint: FirmBlueprint,
    actor_id: UUID,
    *,
    salesman_ids: tuple[UUID, ...] = (),
) -> None:
    """Give the firm a region, two territories and a route under each.

    The territory module has been complete on the server since it was written
    -- hierarchy, route types, route profiles, customer and salesman
    assignment, beat plans -- and every one of its tables was empty in the
    demo. So Sales -> Geography opened on an empty grid and the whole feature
    looked unbuilt.

    The hierarchy defaults to Region -> Territory -> Route, so a route is the
    leaf of the tree rather than a separate record: the territory *is* the
    round, and its route profile says what kind of round and how often.
    """
    service = SalesTerritoryService(session)
    hierarchy = service.get_hierarchy(firm_scope=firm.id, actor_id=actor_id)
    levels = {level.level_code: level.id for level in hierarchy.levels}
    if not {"REGION", "TERRITORY", "ROUTE"} <= levels.keys():
        return

    # Two kinds of round, which is the distinction the module exists to carry:
    # a van going out to sell, and someone going out to collect what is owed.
    route_types: dict[str, UUID] = {
        item.code: item.id for item in service.list_route_types(firm_scope=firm.id)
    }
    for code, name in (
        ("SALES", "Sales Route"),
        ("COLLECTION", "Collection Route"),
    ):
        if code in route_types:
            continue
        created = service.create_route_type(
            RouteTypeWrite(code=code, name=name),
            firm_scope=firm.id,
            actor_id=actor_id,
        )
        route_types[code] = created.id

    def _ensure_route_profile(node_id: UUID, route: RouteProfileInput) -> None:
        """Give an existing node its route profile, and the days it should work.

        Two jobs, and the second is why this is not just a create-if-missing.
        A profile that exists keeps whatever days it has -- but a day this
        script means the round to work and the store does not have is added.
        `WHOLE01-R-N1` sat on Monday alone where every other firm's equivalent
        works Monday, Wednesday and Friday, so its Wednesday and Friday rounds
        reported "the route does not work on this day" for ever and that firm
        showed two blank weekdays.

        **Additive, never subtractive.** The service replaces the day set --
        anything absent from the request is soft-deleted -- so the union is
        sent rather than the intended list, and a day somebody added by hand
        survives a reseed. That is the same "backfill only where missing"
        rule the GSTIN, HSN and tax-profile backfills follow; narrowing a
        round is a decision, and this script does not get to reverse it.
        """
        node = session.get(SalesTerritoryNode, node_id)
        if node is None:
            return
        profile_id = session.scalar(
            select(TerritoryRouteProfile.id).where(
                TerritoryRouteProfile.territory_id == node_id,
                TerritoryRouteProfile.is_deleted.is_(False),
            )
        )
        wanted = route
        if profile_id is not None:
            stored = set(
                session.scalars(
                    select(TerritoryWorkingDay.weekday).where(
                        TerritoryWorkingDay.route_profile_id == profile_id,
                        TerritoryWorkingDay.is_deleted.is_(False),
                    )
                ).all()
            )
            missing = set(route.working_days) - stored
            if not missing:
                return
            wanted = route.model_copy(
                update={"working_days": sorted(stored | set(route.working_days))}
            )
        service.update_territory(
            node_id,
            TerritoryUpdate(
                code=node.code,
                name=node.name,
                hierarchy_level_id=node.hierarchy_level_id,
                parent_id=node.parent_id,
                route_profile=wanted,
            ),
            firm_scope=firm.id,
            actor_id=actor_id,
        )

    def _node(
        code: str,
        name: str,
        level: str,
        parent_id: UUID | None,
        route: RouteProfileInput | None = None,
    ) -> UUID | None:
        existing = session.scalar(
            select(SalesTerritoryNode.id).where(
                SalesTerritoryNode.firm_id == firm.id,
                SalesTerritoryNode.code == code,
                SalesTerritoryNode.is_deleted.is_(False),
            )
        )
        if existing is not None:
            # A node that already exists still needs its route profile, and
            # this used to return before checking: `WHOLE01-R-S1` had been
            # seeded before the profile was part of the route list and so was
            # never a route at all, which made every beat plan against it
            # refuse with "is not a route". The fourth instance of a master
            # field added later never reaching a store already seeded --
            # backfilled only where missing, never overwritten.
            if route is not None:
                _ensure_route_profile(existing, route)
            return existing
        return service.create_territory(
            TerritoryCreate(
                code=code,
                name=name,
                hierarchy_level_id=levels[level],
                parent_id=parent_id,
                route_profile=route,
            ),
            firm_scope=firm.id,
            actor_id=actor_id,
        ).id

    region_id = _node(f"{firm.code}-RGN", f"{blueprint.city} Region", "REGION", None)
    if region_id is None:
        return
    north = _node(f"{firm.code}-T-N", "North Zone", "TERRITORY", region_id)
    south = _node(f"{firm.code}-T-S", "South Zone", "TERRITORY", region_id)

    routes: list[UUID] = []
    #: The route each plan hangs off, and the days that route works. A beat
    #: plan whose weekday is not one of its route's working days reports "the
    #: route does not work on this day" for ever, so the two are kept together.
    route_days: dict[UUID, list[int]] = {}
    for parent, suffix, label, kind, frequency, days in (
        (north, "R-N1", "North Sales Beat", "SALES", VisitFrequency.WEEKLY, [1, 3, 5]),
        (
            north,
            "R-N2",
            "North Collections",
            "COLLECTION",
            VisitFrequency.FORTNIGHTLY,
            [2, 4],
        ),
        (south, "R-S1", "South Sales Beat", "SALES", VisitFrequency.WEEKLY, [2, 4]),
    ):
        if parent is None:
            continue
        made = _node(
            f"{firm.code}-{suffix}",
            label,
            "ROUTE",
            parent,
            RouteProfileInput(
                route_type_id=route_types.get(kind),
                visit_frequency=frequency,
                working_days=days,
            ),
        )
        if made is not None:
            routes.append(made)
            route_days[made] = list(days)

    # Put the firm's customers on the rounds, so "customers without a route" on
    # the Geography dashboard reports something real rather than everyone.
    customer_ids = list(
        session.scalars(
            select(Customer.id)
            .where(Customer.firm_id == firm.id, Customer.is_deleted.is_(False))
            .order_by(Customer.code.asc())
        ).all()
    )
    for index, route_id in enumerate(routes):
        assigned = customer_ids[index :: max(len(routes), 1)]
        if not assigned:
            continue
        service.set_customers(
            route_id,
            TerritoryAssignCustomersRequest(customer_ids=assigned),
            firm_scope=firm.id,
            actor_id=actor_id,
        )

    # And put somebody on each round. Without this the rounds exist, the
    # customers are on them, and no document can name a salesman at all:
    # `_validated_salesman` refuses anybody who does not cover the customer's
    # territory, and `_derived_salesman` has nobody to derive. Every store had
    # zero of these rows, so the whole order -> note -> invoice -> collection
    # -> commission chain could only ever report Unassigned.
    #
    # Marked primary because the derivation deliberately names nobody when two
    # people share a round with neither marked: an unmarked pair is a
    # configuration the code reads as "cannot say", not as "either will do".
    for index, route_id in enumerate(routes):
        if not salesman_ids:
            break
        service.set_salesmen(
            route_id,
            TerritoryAssignSalesmenRequest(
                assignments=[
                    SalesmanAssignmentInput(
                        user_id=salesman_ids[index % len(salesman_ids)],
                        is_primary=True,
                    )
                ]
            ),
            firm_scope=firm.id,
            actor_id=actor_id,
        )

    _seed_beat_plans(session, service, firm, actor_id, routes, route_days)


def _seed_beat_plans(
    session: Session,
    service: SalesTerritoryService,
    firm: Firm,
    actor_id: UUID,
    routes: list[UUID],
    route_days: dict[UUID, list[int]],
) -> None:
    """Give each round a timetable, so the call list has something to answer.

    Every store held **zero** beat plans, so `GET /call-lists` and a plan's own
    call list both answered an empty page for every firm and every date -- the
    feature looked unbuilt, which is what happened to the whole territory
    module before 2026-08-16 and to `territory_salesman_assignments` before
    2026-08-23. A screen with nothing behind it is indistinguishable from a
    screen that does not work.

    Three rules decide whether a plan calls anybody, and the seed has to
    satisfy all three or it reproduces the empty screen with extra rows:

    1. the recurrence must hit the date (`_occurs_on`),
    2. the route must be in force on it (`_route_in_force`), and
    3. **the route must work that weekday** (`_route_works_on`) -- which is why
       each plan's weekday is drawn from its own route's working days rather
       than picked.

    Between them the plans cover Monday to Friday, so whichever day somebody
    opens the screen there is a round to see; Saturday and Sunday show the
    "does not run today" answer, which is a different thing from an empty
    round and worth being able to look at.

    Stops are deliberately seeded for **one** plan only. A plan that lists none
    falls back to every customer on its territory in visit order, which is the
    ordinary case; listing them is how a route splits into day-beats. Seeding
    one of each exercises both paths.
    """
    if not routes:
        return
    existing = {
        code
        for code in session.scalars(
            select(BeatPlan.code).where(
                BeatPlan.firm_id == firm.id,
                BeatPlan.is_deleted.is_(False),
            )
        ).all()
    }
    #: What each route actually works, read from the store rather than from
    #: the list above. `WHOLE01-R-N1` was seeded by an older version of this
    #: script with Monday alone where the list now says Monday, Wednesday and
    #: Friday -- and an existing profile is deliberately never overwritten, so
    #: the two disagree for ever. A plan built from the literal would name a
    #: weekday its route does not work and report "the route does not work on
    #: this day" for the rest of time, which is the empty screen this function
    #: exists to fill, with extra rows.
    working: dict[UUID, list[int]] = {}
    for route_id in routes:
        stored = list(
            session.scalars(
                select(TerritoryWorkingDay.weekday)
                .join(
                    TerritoryRouteProfile,
                    TerritoryRouteProfile.id == TerritoryWorkingDay.route_profile_id,
                )
                .where(
                    TerritoryRouteProfile.territory_id == route_id,
                    TerritoryRouteProfile.is_deleted.is_(False),
                    TerritoryWorkingDay.is_deleted.is_(False),
                )
                .order_by(TerritoryWorkingDay.weekday.asc())
            ).all()
        )
        # A route naming no working days works every day its plan says, so an
        # empty list means the whole week is available rather than none of it.
        working[route_id] = stored or [1, 2, 3, 4, 5]

    weekday_names = {
        1: "Monday",
        2: "Tuesday",
        3: "Wednesday",
        4: "Thursday",
        5: "Friday",
        6: "Saturday",
        7: "Sunday",
    }
    made = 0
    #: One weekly round per day the route works, so between them the rounds
    #: cover as much of the week as the firm's own routes allow. Days a route
    #: does not work stay uncovered, which is the truth about that firm rather
    #: than something to paper over.
    for position, route_id in enumerate(routes, start=1):
        for weekday in working[route_id]:
            # Keyed on the route as well as the day. Two rounds working the
            # same weekday collided on a day-only code, so the second got no
            # plan at all -- WHOLE01's South round was left with nothing but
            # the monthly review while North held three.
            code = f"{firm.code}-BP-R{position}-{weekday_names[weekday][:3].upper()}"
            if code in existing:
                continue
            existing.add(code)
            service.create_beat_plan(
                BeatPlanCreate(
                    code=code,
                    name=(
                        f"{firm.code} {weekday_names[weekday]} round "
                        f"(round {position})"
                    ),
                    territory_id=route_id,
                    plan_type=BeatPlanType.WEEKLY,
                    weekday=weekday,
                ),
                firm_scope=firm.id,
                actor_id=actor_id,
            )
            made += 1

    # And one of each of the other two recurrences, so all three kinds are
    # visible. Both hang off a day their own route works, for the reason
    # above.
    extras: list[tuple[str, str, BeatPlanType, int | None]] = [
        ("COLL", "Collections, alternate {day}s", BeatPlanType.FORTNIGHTLY, None),
        ("MTH", "Second {day} review", BeatPlanType.MONTHLY, 2),
    ]
    for index, (suffix, label, plan_type, week) in enumerate(extras):
        route_id = routes[min(index + 1, len(routes) - 1)]
        weekday = working[route_id][0]
        code = f"{firm.code}-BP-{suffix}"
        if code in existing:
            continue
        existing.add(code)
        service.create_beat_plan(
            BeatPlanCreate(
                code=code,
                name=f"{firm.code} " + label.format(day=weekday_names[weekday]),
                territory_id=route_id,
                plan_type=plan_type,
                weekday=weekday,
                week_of_month=week,
                # A fortnightly plan with no anchor is refused rather than
                # guessed at, so it gets one.
                starts_on=(
                    date(2026, 4, 7) if plan_type is BeatPlanType.FORTNIGHTLY else None
                ),
            ),
            firm_scope=firm.id,
            actor_id=actor_id,
        )
        made += 1
    if made:
        session.commit()
    _seed_beat_plan_stops(session, service, firm, actor_id, routes)


def _seed_beat_plan_stops(
    session: Session,
    service: SalesTerritoryService,
    firm: Firm,
    actor_id: UUID,
    routes: list[UUID],
) -> None:
    """Give one plan an explicit order of calls.

    The rest fall back to their territory's customers, which is the ordinary
    arrangement. This one says which shops belong to the round and in what
    order, which is what the table exists for -- and seeding both means the
    fallback and the explicit path are each exercised by real data.
    """
    plan = session.scalar(
        select(BeatPlan).where(
            BeatPlan.firm_id == firm.id,
            BeatPlan.code == f"{firm.code}-BP-MON",
            BeatPlan.is_deleted.is_(False),
        )
    )
    if plan is None:
        return
    already = session.scalar(
        select(func.count())
        .select_from(BeatPlanCustomerStop)
        .where(
            BeatPlanCustomerStop.beat_plan_id == plan.id,
            BeatPlanCustomerStop.is_deleted.is_(False),
        )
    )
    if already:
        return
    customers = list(
        session.scalars(
            select(TerritoryCustomerAssignment.customer_id).where(
                # No `firm_id` here: the assignment is scoped through its
                # territory, and that territory is this firm's route.
                TerritoryCustomerAssignment.territory_id == plan.territory_id,
                TerritoryCustomerAssignment.is_deleted.is_(False),
            )
            # `visit_sequence` is nullable, and PostgreSQL sorts NULLs first
            # ascending where SQLite sorts them last -- ranked explicitly so
            # the stop order is the same wherever this runs.
            .order_by(
                case(
                    (TerritoryCustomerAssignment.visit_sequence.is_(None), 1), else_=0
                ),
                TerritoryCustomerAssignment.visit_sequence.asc(),
                TerritoryCustomerAssignment.customer_id.asc(),
            )
        ).all()
    )
    if not customers:
        return
    service.update_beat_plan(
        plan.id,
        BeatPlanUpdate(
            code=plan.code,
            name=plan.name,
            territory_id=plan.territory_id,
            plan_type=BeatPlanType(plan.plan_type),
            weekday=plan.weekday,
            week_of_month=plan.week_of_month,
            starts_on=plan.starts_on,
            ends_on=plan.ends_on,
            customer_stops=[
                BeatPlanCustomerStopInput(
                    customer_id=customer_id,
                    stop_order=order,
                    planned_duration_minutes=20,
                )
                for order, customer_id in enumerate(customers, start=1)
            ],
        ),
        firm_scope=firm.id,
        actor_id=actor_id,
    )
    session.commit()


def _seed_commission(
    session: Session,
    firm: Firm,
    actor_id: UUID,
    *,
    salesman_ids: tuple[UUID, ...] = (),
) -> None:
    """Declare what the firm pays on money it collects.

    Without a rule the commission report is honest and useless: it shows what
    each salesman collected and zero against every one of them, because a firm
    that has declared no rate has not agreed to pay one. A demo of a feature
    should show the feature working.

    A firm-wide default plus one person on a better rate, because the
    precedence -- a rule of one's own beats the default, which beats nothing --
    is the thing about this module worth seeing on screen, and it is invisible
    when everybody earns the same.
    """
    service = CommissionService(session)
    # Checked one rule at a time rather than "does the firm have any". The
    # all-or-nothing guard meant a firm that had lost one of the two never got
    # it back, and the precedence this seeds exists to show is invisible with
    # only one of them present.
    existing, _total = service.list_rules(firm_id=firm.id, page=1, page_size=100)
    if not any(rule.salesman_id is None for rule in existing):
        service.create_rule(
            CommissionRuleCreate(
                percentage=Decimal("2.5"),
                effective_from=date(2024, 4, 1),
            ),
            firm_id=firm.id,
            actor_id=actor_id,
        )
    if salesman_ids and not any(
        rule.salesman_id == salesman_ids[0] and rule.product_category_id is None
        for rule in existing
    ):
        service.create_rule(
            CommissionRuleCreate(
                salesman_id=salesman_ids[0],
                percentage=Decimal("4"),
                effective_from=date(2024, 4, 1),
            ),
            firm_id=firm.id,
            actor_id=actor_id,
        )


def _seed_products(
    session: Session, firm: Firm, blueprint: FirmBlueprint, actor_id: UUID
) -> None:
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
            #
            # The HSN code is the second exception, and for the same shape of
            # reason: a product seeded before this field carried one keeps a
            # NULL, and an invoice naming it **cannot be registered with the
            # tax authority at all**. Backfilled only where it is missing, so
            # a code somebody corrected by hand is never overwritten.
            changed = False
            if (
                existing.track_batch != product.requires_batch
                or existing.require_batch_on_receipt != product.requires_batch
                or existing.require_batch_on_issue != product.requires_batch
            ):
                existing.track_batch = product.requires_batch
                existing.require_batch_on_receipt = product.requires_batch
                existing.require_batch_on_issue = product.requires_batch
                changed = True
            if not (existing.hsn_sac or "").strip() and product.hsn_sac:
                existing.hsn_sac = product.hsn_sac
                changed = True
            # And the third of the same shape. A product seeded before the
            # firm had a tax profile keeps a NULL group code, `TaxRuleService`
            # then matches no rule for it, and **every sale of it is billed
            # with no GST at all** -- WHOLE01's toothpaste went two financial
            # years that way, 37,105 of supplies, and nothing said so until a
            # GST return reported a nil-rated row nobody had asked for.
            if not (existing.tax_profile_group_code or "").strip():
                existing.tax_profile_group_code = tax_profile.group_code
                changed = True
            if changed:
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
                description=f"Seeded demo product for "
                f"{blueprint.business_style.lower()}",
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
                # Both sides. Opening stock carries a batch now, so a traced
                # product has no untracked stock to strand: everything it holds
                # arrived in a batch and can therefore leave from one.
                require_batch_on_receipt=product.requires_batch,
                require_batch_on_issue=product.requires_batch,
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
                f"One {from_uom.code} is {factor} {to_uom.code} " f"for {product_code}."
            ),
        ),
        firm_scope=firm.id,
        actor_id=actor_id,
    )


def _seed_inventory_opening_stock(
    session: Session,
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
            f"Branch/warehouse not found for firm '{firm.code}' while seeding "
            f"inventory."
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
            f"Products missing for firm '{firm.code}' while seeding inventory: "
            f"{missing_codes}"
        )

    lines = [
        OpeningStockLineCreate(
            product_id=product_by_code[product.code].id,
            quantity=Decimal("100") + Decimal(index * 25),
            entered_quantity=Decimal("100") + Decimal(index * 25),
            # Day-one stock of a traced product arrived in a batch like any
            # other delivery, and the flag now says so on the way out as well
            # as in: without a batch here, the opening shelf could never ship.
            batch_number=(
                f"{product.code}-OPENING" if product.requires_batch else None
            ),
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


def _business_profile(session: Session, profile_code: str) -> BusinessProfile:
    profile = session.scalar(
        select(BusinessProfile).where(
            BusinessProfile.code == profile_code,
            BusinessProfile.is_deleted.is_(False),
        )
    )
    if profile is None:
        raise RuntimeError(f"Business profile '{profile_code}' was not found.")
    return profile


def _tax_profile_for_firm(
    session: Session, firm_id: UUID, profile_code: str
) -> TaxProfile:
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


def _uom_map(session: Session) -> dict[str, Uom]:
    rows = session.scalars(
        select(Uom).where(
            Uom.code.in_(
                [
                    "TABLET",
                    "STRIP",
                    "BOX",
                    "KG",
                    "BAG",
                    "L",
                    "BOTTLE",
                    "G",
                    "PACK",
                    "ML",
                    "TUBE",
                    "PIECE",
                ]
            ),
            Uom.is_deleted.is_(False),
        )
    ).all()
    result = {row.code: row for row in rows}
    required = {
        "TABLET",
        "STRIP",
        "BOX",
        "KG",
        "BAG",
        "L",
        "BOTTLE",
        "G",
        "PACK",
        "ML",
        "TUBE",
        "PIECE",
    }
    missing = required - set(result)
    if missing:
        raise RuntimeError(f"Required UOM codes are missing: {sorted(missing)}")
    return result


def _phone(seed: int) -> str:
    return f"+9199000{seed:05d}"


def _pan(seed: int) -> str:
    return f"ABCDE{seed:04d}F"


def _gstin(prefix: str, seed: int) -> str:
    normalized = "".join(
        character for character in prefix.upper() if character.isalnum()
    )
    body = f"{normalized}{seed:02d}".ljust(10, "0")[:10]
    return f"29{body}{seed % 9 + 1}Z5"


def _print_summary(platform: DatabaseManager, settings: Settings) -> None:
    with platform.sessions(schema=platform.config.default_schema).session() as session:
        firms = session.scalars(
            select(Firm).where(Firm.is_deleted.is_(False)).order_by(Firm.code.asc())
        ).all()
        users = session.scalars(
            select(User)
            .where(User.is_deleted.is_(False), User.email.like("%@agency.local"))
            .order_by(User.email.asc())
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
            mode = (
                mapping.deployment_mode
                if mapping is not None
                else DeploymentMode.SHARED.value
            )
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
                f"- {firm.code}: mode={mode} database={database_name} "
                f"schema={schema_name}"
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
            print(f"- {user.email}: firms={len(memberships)} password={DEMO_PASSWORD}")


if __name__ == "__main__":
    raise SystemExit(main())
