"""Batch, lot, serial number, and expiry management tests."""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.batch_serial.models.batch_serial import BatchRecord, LotRecord, SerialNumber
from app.batch_serial.schemas.batch_serial import (
    BatchCreate,
    BatchStatus,
    BatchUpdate,
    ExpiryDashboard,
    LotCreate,
    LotStatus,
    LotType,
    SerialCreate,
    SerialStatus,
)
from app.batch_serial.services import BatchSerialService
from app.branches.models import Branch, Warehouse
from app.business.models import BusinessProfile, FirmBusinessProfile
from app.core.database.base import Base
from app.core.exceptions import ConflictError, ResourceNotFoundError
from app.customers.models import customer as _customer_models  # noqa: F401
from app.firms.models import Firm
from app.products.models import Product
from app.sales.models import territory as _geo_models  # noqa: F401
from app.tax.models import tax_framework as _tax_models  # noqa: F401
from app.vendors.models import vendor as _vendor_models  # noqa: F401
from app.identity.models import identity as _identity_models  # noqa: F401 – register users table
import app.batch_serial.models.batch_serial  # noqa: F401 – register tables
import app.inventory.models.inventory  # noqa: F401 – register inventories table


def _session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _firm(session: Session, code: str) -> Firm:
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


def _product(session: Session, firm_id: UUID, code: str = "SKU-BS-001") -> Product:
    actor_id = uuid4()
    p = Product(
        firm_id=firm_id,
        code=code,
        name=f"Product {code}",
        product_type="STOCK_ITEM",
        status="ACTIVE",
        created_by=actor_id,
        updated_by=actor_id,
    )
    session.add(p)
    session.commit()
    return p


def _batch_create(product_id: UUID, batch_number: str = "BATCH-001") -> BatchCreate:
    return BatchCreate(
        product_id=product_id,
        batch_number=batch_number,
        quantity=Decimal("100"),
        status=BatchStatus.AVAILABLE,
    )


# ─── Tests ────────────────────────────────────────────────────────────────────

def test_create_batch_success() -> None:
    session = _session_factory()()
    firm = _firm(session, "BS1")
    product = _product(session, firm.id)
    actor_id = uuid4()
    service = BatchSerialService(session)

    batch = service.create_batch(
        firm_scope=firm.id,
        actor_id=actor_id,
        data=BatchCreate(
            product_id=product.id,
            batch_number="BATCH-2026-001",
            quantity=Decimal("50"),
            manufacturing_date=date(2026, 1, 1),
            expiry_date=date(2027, 1, 1),
            shelf_life_days=365,
        ),
    )

    assert batch.id is not None
    assert batch.firm_id == firm.id
    assert batch.product_id == product.id
    assert batch.batch_number == "BATCH-2026-001"
    assert batch.quantity == Decimal("50")
    assert batch.status == "AVAILABLE"
    assert batch.shelf_life_days == 365
    assert batch.expiry_date == date(2027, 1, 1)


def test_create_batch_duplicate_raises_conflict() -> None:
    session = _session_factory()()
    firm = _firm(session, "BS2")
    product = _product(session, firm.id)
    actor_id = uuid4()
    service = BatchSerialService(session)

    data = _batch_create(product.id, "DUP-BATCH")
    service.create_batch(firm_scope=firm.id, actor_id=actor_id, data=data)

    with pytest.raises(ConflictError):
        service.create_batch(firm_scope=firm.id, actor_id=actor_id, data=data)


def test_get_batch_not_found() -> None:
    session = _session_factory()()
    firm = _firm(session, "BS3")
    service = BatchSerialService(session)

    with pytest.raises(ResourceNotFoundError):
        service.get_batch(firm_scope=firm.id, batch_id=uuid4())


def test_update_batch() -> None:
    session = _session_factory()()
    firm = _firm(session, "BS4")
    product = _product(session, firm.id)
    actor_id = uuid4()
    service = BatchSerialService(session)

    batch = service.create_batch(
        firm_scope=firm.id,
        actor_id=actor_id,
        data=_batch_create(product.id, "UPD-BATCH"),
    )

    updated = service.update_batch(
        firm_scope=firm.id,
        actor_id=actor_id,
        batch_id=batch.id,
        data=BatchUpdate(status=BatchStatus.QUARANTINE, remarks="Needs inspection"),
    )

    assert updated.status == "QUARANTINE"
    assert updated.remarks == "Needs inspection"


def test_delete_batch_soft() -> None:
    session = _session_factory()()
    firm = _firm(session, "BS5")
    product = _product(session, firm.id)
    actor_id = uuid4()
    service = BatchSerialService(session)

    batch = service.create_batch(
        firm_scope=firm.id,
        actor_id=actor_id,
        data=_batch_create(product.id, "DEL-BATCH"),
    )

    service.delete_batch(firm_scope=firm.id, actor_id=actor_id, batch_id=batch.id)

    deleted = session.scalar(select(BatchRecord).where(BatchRecord.id == batch.id))
    assert deleted is not None
    assert deleted.is_deleted is True

    with pytest.raises(ResourceNotFoundError):
        service.get_batch(firm_scope=firm.id, batch_id=batch.id)


def test_expiry_dashboard() -> None:
    session = _session_factory()()
    firm = _firm(session, "BS6")
    product = _product(session, firm.id)
    actor_id = uuid4()
    service = BatchSerialService(session)

    # Create an expired batch
    service.create_batch(
        firm_scope=firm.id,
        actor_id=actor_id,
        data=BatchCreate(
            product_id=product.id,
            batch_number="EXP-001",
            status=BatchStatus.EXPIRED,
            quantity=Decimal("10"),
        ),
    )
    # Create a batch expiring in 5 days
    service.create_batch(
        firm_scope=firm.id,
        actor_id=actor_id,
        data=BatchCreate(
            product_id=product.id,
            batch_number="EXP-002",
            quantity=Decimal("10"),
            expiry_date=date.today(),
        ),
    )
    # Quarantine batch
    service.create_batch(
        firm_scope=firm.id,
        actor_id=actor_id,
        data=BatchCreate(
            product_id=product.id,
            batch_number="QRN-001",
            status=BatchStatus.QUARANTINE,
            quantity=Decimal("5"),
        ),
    )

    dashboard = service.expiry_dashboard(firm_scope=firm.id)

    assert isinstance(dashboard, ExpiryDashboard)
    assert dashboard.total_expired == 1
    assert dashboard.quarantine == 1
    assert dashboard.expired_today >= 1


def test_create_lot_success() -> None:
    session = _session_factory()()
    firm = _firm(session, "BS7")
    product = _product(session, firm.id)
    actor_id = uuid4()
    service = BatchSerialService(session)

    lot = service.create_lot(
        firm_scope=firm.id,
        actor_id=actor_id,
        data=LotCreate(
            product_id=product.id,
            lot_number="LOT-2026-001",
            lot_type=LotType.PRODUCTION,
            quantity=Decimal("200"),
        ),
    )

    assert lot.id is not None
    assert lot.firm_id == firm.id
    assert lot.lot_number == "LOT-2026-001"
    assert lot.status == "ACTIVE"
    assert lot.lot_type == "PRODUCTION"


def test_create_serial_success() -> None:
    session = _session_factory()()
    firm = _firm(session, "BS8")
    product = _product(session, firm.id)
    actor_id = uuid4()
    service = BatchSerialService(session)

    serial = service.create_serial(
        firm_scope=firm.id,
        actor_id=actor_id,
        data=SerialCreate(
            product_id=product.id,
            serial_number="SN-20260801-0001",
            status=SerialStatus.AVAILABLE,
        ),
    )

    assert serial.id is not None
    assert serial.firm_id == firm.id
    assert serial.serial_number == "SN-20260801-0001"
    assert serial.status == "AVAILABLE"


def test_serial_links_to_batch() -> None:
    session = _session_factory()()
    firm = _firm(session, "BS9")
    product = _product(session, firm.id)
    actor_id = uuid4()
    service = BatchSerialService(session)

    batch = service.create_batch(
        firm_scope=firm.id,
        actor_id=actor_id,
        data=_batch_create(product.id, "LINK-BATCH"),
    )

    serial = service.create_serial(
        firm_scope=firm.id,
        actor_id=actor_id,
        data=SerialCreate(
            product_id=product.id,
            serial_number="SN-LINK-001",
            batch_id=batch.id,
        ),
    )

    assert serial.batch_id == batch.id

    fetched_serial = service.get_serial(firm_scope=firm.id, serial_id=serial.id)
    assert fetched_serial.batch_id == batch.id


def test_list_batches_pagination() -> None:
    session = _session_factory()()
    firm = _firm(session, "BS10")
    product = _product(session, firm.id)
    actor_id = uuid4()
    service = BatchSerialService(session)

    from app.batch_serial.schemas.batch_serial import BatchListFilters

    for i in range(5):
        service.create_batch(
            firm_scope=firm.id,
            actor_id=actor_id,
            data=_batch_create(product.id, f"PAGE-BATCH-{i:03}"),
        )

    page1, total = service.list_batches(
        firm_scope=firm.id,
        filters=BatchListFilters(),
        page=1,
        page_size=3,
        search=None,
        sort_by="created_at",
        descending=False,
    )
    page2, _ = service.list_batches(
        firm_scope=firm.id,
        filters=BatchListFilters(),
        page=2,
        page_size=3,
        search=None,
        sort_by="created_at",
        descending=False,
    )

    assert total == 5
    assert len(page1) == 3
    assert len(page2) == 2
    page1_ids = {r.id for r in page1}
    page2_ids = {r.id for r in page2}
    assert page1_ids.isdisjoint(page2_ids)
