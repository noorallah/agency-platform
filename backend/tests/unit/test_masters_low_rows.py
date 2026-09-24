"""The Masters Low row D-MST-11, every item pinned.

Codes were never released by a delete, the barcode key was stricter under
SQLite than in production, nine master writes left no trail and four edits
un-deleted a retired row, a category could be put under its own child, a
custom display name was lost to every edit, the small masters took no
`If-Match`, a second vendor duplicate was refused, the product list loaded the
whole firm, the CSV export shifted columns on a comma, the vendors' JSON blob
was written and never read, and the settings said stock transfers were not
built.
"""

import csv
import io
from datetime import date
from uuid import UUID

import pytest
from sqlalchemy import Index, create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.branches.api.router import BranchWarehouseSettingsResponse
from app.branches.schemas import BranchCreate, BranchUpdate, WarehouseCreate
from app.branches.schemas.branch_warehouse import (
    BranchTypeWrite,
    StorageNodeCreate,
    StorageNodeUpdate,
)
from app.branches.services import BranchWarehouseService
from app.common.audit.models import AuditLog
from app.core.database.base import Base
from app.core.exceptions import (
    ConflictError,
    ResourceNotFoundError,
    ValidationError,
)
from app.customers.schemas import CustomerCreate
from app.customers.services import CustomerService
from app.firms.models import Firm
from app.products.models import Product
from app.products.schemas import (
    ProductCategoryCreate,
    ProductCategoryUpdate,
    ProductListFilters,
)
from app.products.services import ProductService
from app.vendors.models import Vendor
from app.vendors.schemas import VendorCategoryWrite, VendorCreate, VendorUpdate
from app.vendors.services import VendorService

_ACTOR = UUID("00000000-0000-0000-0000-0000000000b1")


def _session() -> Session:
    """Build an isolated in-memory schema holding one firm."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _firm(session: Session, code: str = "MST") -> Firm:
    """Create the owning firm."""
    row = Firm(
        name=f"{code} Firm",
        code=code,
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(row)
    session.commit()
    return row


def _actions(session: Session) -> set[str]:
    """Return every audit action written so far."""
    return set(session.scalars(select(AuditLog.action)).all())


def _vendor(code: str = "VEN-1", **extra: object) -> VendorCreate:
    """Build a minimal vendor."""
    return VendorCreate.model_validate(
        {"code": code, "name": "Acme Supplies", "status": "ACTIVE", **extra}
    )


# --- codes are released by a delete ------------------------------------------


def test_every_master_code_key_is_partial_and_partial_under_sqlite() -> None:
    """Each live-rows key says so to both dialects, the barcode's included."""
    tables = (
        "customer_groups",
        "customers",
        "vendor_categories",
        "vendor_types",
        "vendors",
        "product_categories",
        "products",
        "branch_types",
        "branches",
        "warehouse_types",
        "warehouses",
        "warehouse_storage_nodes",
    )
    for name in tables:
        table = Base.metadata.tables[name]
        keys = [
            index
            for index in table.indexes
            if isinstance(index, Index) and index.unique
        ]
        assert keys, name
        for index in keys:
            where = index.dialect_options["postgresql"]["where"]
            assert where is not None, index.name
            assert index.dialect_options["sqlite"]["where"] is not None, index.name
        plain = [c for c in table.constraints if c.__class__.__name__ == "Unique"]
        assert not [c for c in plain if "code" in c.columns], name


def test_a_deleted_vendor_releases_its_code_and_a_restore_into_it_is_refused() -> None:
    """Re-using a retired code works; restoring the old row then says why not."""
    session = _session()
    firm = _firm(session)
    service = VendorService(session)
    old = service.create(_vendor(), firm_id=firm.id, actor_id=_ACTOR)
    service.delete(old.id, firm_scope=firm.id, actor_id=_ACTOR)

    service.create(_vendor(), firm_id=firm.id, actor_id=_ACTOR)

    with pytest.raises(ConflictError, match="cannot be restored"):
        service.restore(old.id, firm_scope=firm.id, actor_id=_ACTOR)


def test_a_deleted_customer_releases_its_code() -> None:
    """The customer's code, GST and PAN are free once it is deleted."""
    session = _session()
    firm = _firm(session)
    service = CustomerService(session)
    payload = CustomerCreate.model_validate(
        {
            "code": "CUST-1",
            "customer_type": "BUSINESS",
            "name": "Acme Customer",
            "gst_number": "29ABCDE1234F1Z5",
            "currency_code": "INR",
            "status": "ACTIVE",
        }
    )
    old = service.create(payload, firm_id=firm.id, actor_id=_ACTOR)
    service.delete(old.id, firm_scope=firm.id, actor_id=_ACTOR)

    again = service.create(payload, firm_id=firm.id, actor_id=_ACTOR)

    assert again.id != old.id
    with pytest.raises(ConflictError, match="cannot be restored"):
        service.restore(old.id, firm_scope=firm.id, actor_id=_ACTOR)


# --- the small masters: trail, no un-delete, named refusals, If-Match ----------


def test_vendor_categories_are_audited_and_an_edit_never_undeletes() -> None:
    """Create, edit and delete each leave a row; a retired one is not found."""
    session = _session()
    firm = _firm(session)
    service = VendorService(session)
    body = VendorCategoryWrite(code="RAW", name="Raw material")
    row = service.create_category(body, firm_id=firm.id, actor_id=_ACTOR)
    service.update_category(
        row.id,
        VendorCategoryWrite(code="RAW", name="Raw materials"),
        firm_id=firm.id,
        actor_id=_ACTOR,
        expected_version=row.version,
    )
    with pytest.raises(ConflictError, match="changed since you loaded it"):
        service.update_category(
            row.id, body, firm_id=firm.id, actor_id=_ACTOR, expected_version=1
        )
    with pytest.raises(ConflictError, match="with this name already exists"):
        service.create_category(
            VendorCategoryWrite(code="RAW2", name="Raw materials"),
            firm_id=firm.id,
            actor_id=_ACTOR,
        )
    service.delete_category(row.id, firm_id=firm.id, actor_id=_ACTOR)

    with pytest.raises(ResourceNotFoundError):
        service.update_category(row.id, body, firm_id=firm.id, actor_id=_ACTOR)
    assert {
        "vendor_category.created",
        "vendor_category.updated",
        "vendor_category.deleted",
    } <= _actions(session)
    # The retired code is free again.
    service.create_category(body, firm_id=firm.id, actor_id=_ACTOR)


def test_branch_types_and_storage_node_edits_are_audited() -> None:
    """The type writes and a node edit each leave a trail."""
    session = _session()
    firm = _firm(session)
    service = BranchWarehouseService(session)
    kind = service.create_branch_type(
        BranchTypeWrite(code="RETAIL", name="Retail"),
        firm_id=firm.id,
        actor_id=_ACTOR,
    )
    service.update_branch_type(
        kind.id,
        BranchTypeWrite(code="RETAIL", name="Retail outlet"),
        firm_id=firm.id,
        actor_id=_ACTOR,
    )
    service.delete_branch_type(kind.id, firm_id=firm.id, actor_id=_ACTOR)
    with pytest.raises(ResourceNotFoundError):
        service.update_branch_type(
            kind.id,
            BranchTypeWrite(code="RETAIL", name="Retail"),
            firm_id=firm.id,
            actor_id=_ACTOR,
        )

    branch = service.create_branch(
        BranchCreate.model_validate(
            {"code": "BR-1", "name": "Head Office", "currency_code": "INR"}
        ),
        firm_id=firm.id,
        actor_id=_ACTOR,
    )
    warehouse = service.create_warehouse(
        WarehouseCreate.model_validate(
            {"branch_id": branch.id, "code": "WH-1", "name": "Main"}
        ),
        firm_id=firm.id,
        actor_id=_ACTOR,
    )
    node = service.create_storage_node(
        StorageNodeCreate(
            warehouse_id=warehouse.id, node_type="RACK", code="R1", name="Rack 1"
        ),
        firm_scope=firm.id,
        actor_id=_ACTOR,
    )
    with pytest.raises(ConflictError, match="code already exists"):
        service.create_storage_node(
            StorageNodeCreate(
                warehouse_id=warehouse.id, node_type="RACK", code="R1", name="Other"
            ),
            firm_scope=firm.id,
            actor_id=_ACTOR,
        )
    service.update_storage_node(
        node.id,
        StorageNodeUpdate(
            warehouse_id=warehouse.id, node_type="RACK", code="R1", name="Rack one"
        ),
        firm_scope=firm.id,
        actor_id=_ACTOR,
    )

    assert {
        "branch_type.created",
        "branch_type.updated",
        "branch_type.deleted",
        "warehouse.storage_node.updated",
    } <= _actions(session)


# --- display names, duplicates, the blob ----------------------------------------


def test_an_edit_keeps_a_custom_display_name_it_did_not_send() -> None:
    """Vendors and branches keep a trading name; a derived one follows."""
    session = _session()
    firm = _firm(session)
    vendors = VendorService(session)
    vendor = vendors.create(
        _vendor(display_name="Acme Trading"), firm_id=firm.id, actor_id=_ACTOR
    )
    edited = vendors.update(
        vendor.id,
        VendorUpdate.model_validate(
            {"code": "VEN-1", "name": "Acme Supplies Ltd", "status": "ACTIVE"}
        ),
        firm_scope=firm.id,
        actor_id=_ACTOR,
    )
    assert edited.display_name == "Acme Trading"

    branches = BranchWarehouseService(session)
    branch = branches.create_branch(
        BranchCreate.model_validate(
            {"code": "BR-1", "name": "Head Office", "currency_code": "INR"}
        ),
        firm_id=firm.id,
        actor_id=_ACTOR,
    )
    renamed = branches.update_branch(
        branch.id,
        BranchUpdate.model_validate({"code": "BR-1", "name": "Main Office"}),
        firm_scope=firm.id,
        actor_id=_ACTOR,
    )
    assert renamed.display_name == "Main Office"


def test_a_vendor_can_be_duplicated_twice_and_each_copy_is_audited() -> None:
    """The copy's code counts up the way a product's does."""
    session = _session()
    firm = _firm(session)
    service = VendorService(session)
    source = service.create(_vendor(), firm_id=firm.id, actor_id=_ACTOR)

    first = service.duplicate(source.id, firm_scope=firm.id, actor_id=_ACTOR)
    second = service.duplicate(source.id, firm_scope=firm.id, actor_id=_ACTOR)

    assert (first.code, second.code) == ("VEN-1-COPY", "VEN-1-COPY-1")
    assert (
        len(
            session.scalars(
                select(AuditLog).where(AuditLog.action == "vendor.duplicated")
            ).all()
        )
        == 2
    )


def test_the_vendor_json_blob_is_no_longer_written() -> None:
    """Accepted for an older client, and never stored."""
    session = _session()
    firm = _firm(session)
    vendor = VendorService(session).create(
        _vendor(business_attributes={"segment": "RAW"}),
        firm_id=firm.id,
        actor_id=_ACTOR,
    )
    assert session.get(Vendor, vendor.id).business_attributes == {}


# --- product categories -----------------------------------------------------------


def test_a_category_cannot_move_under_its_own_child_and_a_move_repaths() -> None:
    """The loop is refused; a legitimate move rewrites the whole subtree."""
    session = _session()
    firm = _firm(session)
    service = ProductService(session)
    root = service.create_category(
        ProductCategoryCreate(code="PC", name="Personal care"),
        firm_id=firm.id,
        actor_id=_ACTOR,
    )
    child = service.create_category(
        ProductCategoryCreate(code="PCC", name="Creams", parent_id=root.id),
        firm_id=firm.id,
        actor_id=_ACTOR,
    )
    grandchild = service.create_category(
        ProductCategoryCreate(code="PCCF", name="Face", parent_id=child.id),
        firm_id=firm.id,
        actor_id=_ACTOR,
    )
    other = service.create_category(
        ProductCategoryCreate(code="HC", name="Home care"),
        firm_id=firm.id,
        actor_id=_ACTOR,
    )

    with pytest.raises(ValidationError, match="own sub-categories"):
        service.update_category(
            root.id,
            ProductCategoryUpdate(code="PC", name="Personal care", parent_id=child.id),
            firm_scope=firm.id,
            actor_id=_ACTOR,
        )
    service.update_category(
        child.id,
        ProductCategoryUpdate(code="PCC", name="Creams", parent_id=other.id),
        firm_scope=firm.id,
        actor_id=_ACTOR,
    )

    session.refresh(grandchild)
    assert grandchild.path == "HC/PCC/PCCF"
    assert grandchild.level == 2
    assert {"product.category.created", "product.category.updated"} <= _actions(session)


def test_a_category_with_children_or_sub_category_use_is_not_deleted() -> None:
    """A live child, or a product naming it as a sub-category, holds it."""
    session = _session()
    firm = _firm(session)
    service = ProductService(session)
    root = service.create_category(
        ProductCategoryCreate(code="GR", name="Grocery"),
        firm_id=firm.id,
        actor_id=_ACTOR,
    )
    child = service.create_category(
        ProductCategoryCreate(code="GRR", name="Rice", parent_id=root.id),
        firm_id=firm.id,
        actor_id=_ACTOR,
    )
    session.add(
        Product(
            firm_id=firm.id,
            code="RICE",
            name="Rice",
            product_type="STOCK_ITEM",
            status="ACTIVE",
            # Named only as a sub-category, which the guard used to miss.
            sub_category_id=child.id,
        )
    )
    session.commit()

    with pytest.raises(ValidationError, match="sub-categories"):
        service.delete_category(root.id, firm_scope=firm.id, actor_id=_ACTOR)
    with pytest.raises(ValidationError, match="used by products"):
        service.delete_category(child.id, firm_scope=firm.id, actor_id=_ACTOR)


# --- the product list and export ----------------------------------------------------


def _products(session: Session, firm_id: UUID, names: list[str]) -> None:
    """Insert products straight into the table."""
    for index, name in enumerate(names):
        session.add(
            Product(
                firm_id=firm_id,
                code=f"P{index:03d}",
                name=name,
                product_type="STOCK_ITEM",
                status="ACTIVE",
            )
        )
    session.commit()


def test_the_product_list_searches_and_pages_in_the_database() -> None:
    """A search's total and page come from SQL, not a Python slice."""
    session = _session()
    firm = _firm(session)
    _products(session, firm.id, [f"Rice {n}" for n in range(5)] + ["Oil", "Salt"])
    service = ProductService(session)

    rows, total = service.list_products(
        firm_scope=firm.id,
        filters=ProductListFilters(),
        page=2,
        page_size=2,
        search="rice",
        sort_by="code",
        descending=False,
    )

    assert total == 5
    assert [row.code for row in rows] == ["P002", "P003"]


def test_the_product_csv_export_quotes_a_comma() -> None:
    """A name with a comma stays in its column."""
    session = _session()
    firm = _firm(session)
    _products(session, firm.id, ["Rice, basmati"])

    text = ProductService(session).export_products_csv(firm_scope=firm.id, search=None)

    rows = list(csv.reader(io.StringIO(text)))
    assert rows[1][1] == "Rice, basmati"
    assert len(rows[1]) == len(rows[0])


def test_the_settings_say_stock_transfers_are_built() -> None:
    """`/api/v1/inventory/transfers` shipped, across branches too."""
    settings = BranchWarehouseSettingsResponse()
    assert settings.stock_transfer_ready is True
    assert settings.inter_branch_transfer_ready is True


def test_a_blank_gstin_is_not_a_claim_on_one() -> None:
    """Two vendors without a GSTIN do not clash over the empty value."""
    session = _session()
    firm = _firm(session)
    service = VendorService(session)
    service.create(_vendor(gstin=None), firm_id=firm.id, actor_id=_ACTOR)
    service.create(_vendor(code="VEN-2", gstin=None), firm_id=firm.id, actor_id=_ACTOR)
    assert len(session.scalars(select(Vendor)).all()) == 2
