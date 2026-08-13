"""Batch, lot, serial number, and expiry management tests."""

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.batch_serial.models.batch_serial  # noqa: F401 – register tables
import app.inventory.models.inventory  # noqa: F401 – register inventories table
from app.batch_serial.models.batch_serial import BatchRecord
from app.batch_serial.schemas.batch_serial import (
    BatchCreate,
    BatchStatus,
    BatchUpdate,
    ExpiryDashboard,
    LotCreate,
    LotType,
    SerialCreate,
    SerialStatus,
)
from app.batch_serial.services import BatchSerialService
from app.core.database.base import Base
from app.core.exceptions import ConflictError, ResourceNotFoundError
from app.core.utils.dates import utc_now
from app.customers.models import customer as _customer_models  # noqa: F401
from app.firms.models import Firm
from app.identity.models import (
    identity as _identity_models,  # noqa: F401 – register users table
)
from app.products.models import Product
from app.sales.models import territory as _geo_models  # noqa: F401
from app.tax.models import tax_framework as _tax_models  # noqa: F401
from app.vendors.models import vendor as _vendor_models  # noqa: F401


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
        status=BatchStatus.AVAILABLE,
    )


# ─── Tests ────────────────────────────────────────────────────────────────────


def test_a_batch_cannot_be_created_holding_stock() -> None:
    """Registering a batch is not a way to put stock on the shelf.

    ``create_batch`` used to take a quantity and write it straight onto the
    batch, which produced a number no movement explained and which the stock
    projection never saw. Stock arrives through a document; the batch says what
    it is, not how much of it there is.
    """
    with pytest.raises(ValidationError) as caught:
        BatchCreate(
            product_id=uuid4(),
            batch_number="BATCH-WITH-STOCK",
            quantity=Decimal("50"),
        )

    assert "quantity" in str(caught.value)


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
            manufacturing_date=date(2026, 1, 1),
            expiry_date=date(2027, 1, 1),
            shelf_life_days=365,
        ),
    )

    assert batch.id is not None
    assert batch.firm_id == firm.id
    assert batch.product_id == product.id
    assert batch.batch_number == "BATCH-2026-001"
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
        ),
    )
    # Create a batch expiring in 5 days
    service.create_batch(
        firm_scope=firm.id,
        actor_id=actor_id,
        data=BatchCreate(
            product_id=product.id,
            batch_number="EXP-002",
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
        ),
    )

    dashboard = service.expiry_dashboard(firm_scope=firm.id)

    assert isinstance(dashboard, ExpiryDashboard)
    # Both halves count the same batches now: the one marked expired by hand
    # and, once UTC passes its date, the one that expired on its own.
    assert dashboard.total_expired == dashboard.expired_today
    assert dashboard.quarantine == 1
    assert dashboard.total_expired >= 1


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


def test_expired_counts_come_from_the_date_not_a_status() -> None:
    """Nothing ever set status = EXPIRED, so every count keyed on it read zero.

    The platform has no scheduler to flip the status, so a batch whose expiry
    date has passed stayed AVAILABLE forever. The summary card reported zero
    expired batches while the expiry card, which looked at the date, listed
    them -- two numbers on one dashboard disagreeing about the same table.
    """
    session = _session_factory()()
    firm = _firm(session, "BSEXP")
    product = _product(session, firm.id)
    actor_id = uuid4()
    service = BatchSerialService(session)
    today = utc_now().date()

    for number, expiry, status in (
        ("PAST-1", today - timedelta(days=5), BatchStatus.AVAILABLE),
        ("PAST-2", today - timedelta(days=1), BatchStatus.AVAILABLE),
        ("SOON", today + timedelta(days=3), BatchStatus.AVAILABLE),
        ("LATER", today + timedelta(days=90), BatchStatus.AVAILABLE),
    ):
        service.create_batch(
            firm_scope=firm.id,
            actor_id=actor_id,
            data=BatchCreate(
                product_id=product.id,
                batch_number=number,
                expiry_date=expiry,
                status=status,
            ),
        )

    summary = service.batch_summary(firm_scope=firm.id)
    dashboard = service.expiry_dashboard(firm_scope=firm.id)

    assert summary.expired == 2
    assert dashboard.total_expired == 2
    assert dashboard.expired_today == 2
    # The two halves of the dashboard now agree.
    assert dashboard.total_expired == dashboard.expired_today
    assert summary.near_expiry == 1
    assert dashboard.expire_in_7_days == 1


def test_a_destroyed_batch_is_not_counted_as_expired() -> None:
    """Destroyed stock has left the building; it is not awaiting disposal."""
    session = _session_factory()()
    firm = _firm(session, "BSDES")
    product = _product(session, firm.id)
    actor_id = uuid4()
    service = BatchSerialService(session)

    service.create_batch(
        firm_scope=firm.id,
        actor_id=actor_id,
        data=BatchCreate(
            product_id=product.id,
            batch_number="GONE",
            expiry_date=utc_now().date() - timedelta(days=10),
            status=BatchStatus.DESTROYED,
        ),
    )

    assert service.batch_summary(firm_scope=firm.id).expired == 0
