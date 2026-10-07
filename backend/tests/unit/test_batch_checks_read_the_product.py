"""Batch, lot and serial checks read the product, never the firm's profile.

Backlog 89, step 4. A firm's one business profile used to be a ceiling over
every product in it: a firm on the pharmacy profile was refused a serial number
on anything, and a paint dealer who started carrying medicines could not date a
batch without changing profile. The product's own switches answer now, so one
firm carries a medicine, a paint and a phone, each by its own rules.
"""

from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.batch_serial.models.batch_serial import BatchRecord
from app.batch_serial.schemas.batch_serial import (
    BatchCreate,
    BatchStatus,
    BatchUpdate,
    LotCreate,
    LotType,
    LotUpdate,
    SerialCreate,
    SerialUpdate,
)
from app.batch_serial.services import BatchSerialService
from app.batch_serial.services.product_tracking import (
    FIELD_SWITCHES,
    RECORD_SWITCHES,
)
from app.business.models import (
    BusinessFeature,
    BusinessProfile,
    FirmBusinessProfile,
    ProfileFeature,
)
from app.common.audit.models import AuditLog
from app.core.database.base import Base
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.customers.schemas.customer import (
    CustomerCreate,
    CustomerType,
    CustomerUpdate,
)
from app.customers.services import CustomerService
from app.firms.models import Firm
from app.products.models import Product

#: Every product-behaviour feature the profile used to gate on.
_OLD_CODES = (
    "BATCH_TRACKING",
    "SERIAL_NUMBER",
    "EXPIRY_TRACKING",
    "MANUFACTURING_DATE",
    "SHELF_LIFE",
    "WARRANTY",
)


def _session() -> Session:
    """Return a session on a fresh in-memory schema."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _firm(session: Session, code: str, *, enabled: tuple[str, ...] = ()) -> Firm:
    """Return a firm on a profile that enables only the features named.

    Every old product-behaviour feature is in the catalogue and switched
    **off** on the profile unless named, which is the firm the old gates
    refused: a profile is resolved, so "no profile, nothing enforced" cannot
    be what lets a write through.
    """
    firm = Firm(
        name=f"{code} Firm",
        code=code,
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    profile = BusinessProfile(
        code=f"P-{code}", name=code, industry_type="TRADING", status="ACTIVE"
    )
    session.add_all([firm, profile])
    session.flush()
    for feature_code in _OLD_CODES:
        feature = session.scalar(
            select(BusinessFeature).where(BusinessFeature.code == feature_code)
        )
        if feature is None:
            feature = BusinessFeature(code=feature_code, name=feature_code)
            session.add(feature)
            session.flush()
        session.add(
            ProfileFeature(
                business_profile_id=profile.id,
                feature_id=feature.id,
                is_enabled=feature_code in enabled,
            )
        )
    session.add(
        FirmBusinessProfile(
            firm_id=firm.id,
            business_profile_id=profile.id,
            is_active=True,
            effective_from=date(2026, 4, 1),
        )
    )
    session.commit()
    return firm


def _product(session: Session, firm_id: UUID, code: str, **switches: bool) -> Product:
    """Return a product with only the named tracking switches on."""
    actor_id = uuid4()
    row = Product(
        firm_id=firm_id,
        code=code,
        name=f"Product {code}",
        product_type="STOCK_ITEM",
        status="ACTIVE",
        created_by=actor_id,
        updated_by=actor_id,
        **switches,
    )
    session.add(row)
    session.commit()
    return row


def _medicine(session: Session, firm: Firm) -> Product:
    return _product(
        session,
        firm.id,
        "MED-1",
        track_batch=True,
        track_expiry=True,
        track_manufacturing_date=True,
    )


def _paint(session: Session, firm: Firm) -> Product:
    return _product(session, firm.id, "PAINT-1", track_batch=True)


def _phone(session: Session, firm: Firm) -> Product:
    return _product(session, firm.id, "PHONE-1", track_serial=True, track_warranty=True)


def _batch(product: Product, number: str = "B-1", **fields: object) -> BatchCreate:
    return BatchCreate(
        product_id=product.id,
        batch_number=number,
        status=BatchStatus.AVAILABLE,
        **fields,  # type: ignore[arg-type]
    )


# ── One firm, three lines ────────────────────────────────────────────────────


def test_one_firm_carries_a_medicine_a_paint_and_a_phone() -> None:
    """Each by its own switches, on a profile that enables none of it."""
    session = _session()
    firm = _firm(session, "MIX1")
    service = BatchSerialService(session)
    actor = uuid4()

    dated = service.create_batch(
        firm_scope=firm.id,
        actor_id=actor,
        data=_batch(
            _medicine(session, firm),
            expiry_date=date(2027, 6, 30),
            manufacturing_date=date(2026, 1, 1),
            shelf_life_days=540,
        ),
    )
    plain = service.create_batch(
        firm_scope=firm.id, actor_id=actor, data=_batch(_paint(session, firm))
    )
    unit = service.create_serial(
        firm_scope=firm.id,
        actor_id=actor,
        data=SerialCreate(
            product_id=_phone(session, firm).id,
            serial_number="IMEI-0001",
            warranty_start=date(2026, 10, 1),
            warranty_end=date(2027, 10, 1),
        ),
    )

    assert dated.expiry_date == date(2027, 6, 30)
    assert dated.shelf_life_days == 540
    assert plain.expiry_date is None
    assert unit.warranty_end == date(2027, 10, 1)
    actions = set(session.scalars(select(AuditLog.action)))
    assert {"batch.created", "serial_number.created"} <= actions


# ── May this product have one at all ─────────────────────────────────────────


def test_a_batch_is_refused_for_a_product_not_tracked_by_batch() -> None:
    """Even where the firm's profile enables every old feature."""
    session = _session()
    firm = _firm(session, "REF1", enabled=_OLD_CODES)
    phone = _phone(session, firm)

    with pytest.raises(ValidationError, match="PHONE-1 is not tracked by batch"):
        BatchSerialService(session).create_batch(
            firm_scope=firm.id, actor_id=uuid4(), data=_batch(phone)
        )
    assert session.scalar(select(BatchRecord)) is None


def test_a_serial_is_refused_for_a_product_not_tracked_by_serial() -> None:
    """A paint is not numbered, whatever the profile enables."""
    session = _session()
    firm = _firm(session, "REF2", enabled=_OLD_CODES)
    paint = _paint(session, firm)

    with pytest.raises(ValidationError, match="PAINT-1 is not tracked by serial"):
        BatchSerialService(session).create_serial(
            firm_scope=firm.id,
            actor_id=uuid4(),
            data=SerialCreate(product_id=paint.id, serial_number="S-1"),
        )


def test_a_lot_is_taken_by_lot_or_by_batch_and_refused_otherwise() -> None:
    """Either switch admits a lot; a product with neither is refused."""
    session = _session()
    firm = _firm(session, "REF3")
    service = BatchSerialService(session)
    by_lot = _product(session, firm.id, "LOT-1", track_lot=True)

    def lot(product: Product, number: str) -> LotCreate:
        return LotCreate(
            product_id=product.id,
            lot_number=number,
            lot_type=LotType.PRODUCTION,
            quantity=10,
        )

    service.create_lot(firm_scope=firm.id, actor_id=uuid4(), data=lot(by_lot, "L-1"))
    service.create_lot(
        firm_scope=firm.id, actor_id=uuid4(), data=lot(_paint(session, firm), "L-2")
    )
    with pytest.raises(ValidationError, match="PHONE-1 is not tracked by lot"):
        service.create_lot(
            firm_scope=firm.id,
            actor_id=uuid4(),
            data=lot(_phone(session, firm), "L-3"),
        )


def test_another_firms_product_is_not_found() -> None:
    """The check loads the product in the caller's firm, and nowhere else."""
    session = _session()
    firm = _firm(session, "OWN1")
    other = _firm(session, "OTH1")
    theirs = _medicine(session, other)

    with pytest.raises(ResourceNotFoundError):
        BatchSerialService(session).create_batch(
            firm_scope=firm.id, actor_id=uuid4(), data=_batch(theirs)
        )


# ── May it carry this field ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("fields", "named"),
    [
        ({"expiry_date": date(2027, 1, 1)}, "expiry_date"),
        ({"best_before_date": date(2027, 1, 1)}, "best_before_date"),
        ({"shelf_life_days": 365}, "shelf_life_days"),
        ({"manufacturing_date": date(2026, 1, 1)}, "manufacturing_date"),
    ],
)
def test_a_paint_batch_is_refused_a_date_it_does_not_track(
    fields: dict[str, object], named: str
) -> None:
    """The profile enables it all; the product does not track it."""
    session = _session()
    firm = _firm(session, "FLD1", enabled=_OLD_CODES)
    paint = _paint(session, firm)

    with pytest.raises(ValidationError, match=f"PAINT-1 does not track .*{named}"):
        BatchSerialService(session).create_batch(
            firm_scope=firm.id, actor_id=uuid4(), data=_batch(paint, **fields)
        )
    assert session.scalar(select(BatchRecord)) is None


def test_a_serial_is_refused_a_warranty_its_product_does_not_track() -> None:
    """On the way in and on a later change; without the dates it is taken."""
    session = _session()
    firm = _firm(session, "FLD2", enabled=_OLD_CODES)
    numbered = _product(session, firm.id, "TOOL-1", track_serial=True)
    service = BatchSerialService(session)

    with pytest.raises(ValidationError, match="TOOL-1 does not track warranty"):
        service.create_serial(
            firm_scope=firm.id,
            actor_id=uuid4(),
            data=SerialCreate(
                product_id=numbered.id,
                serial_number="T-1",
                warranty_end=date(2027, 1, 1),
            ),
        )
    unit = service.create_serial(
        firm_scope=firm.id,
        actor_id=uuid4(),
        data=SerialCreate(product_id=numbered.id, serial_number="T-1"),
    )
    with pytest.raises(ValidationError, match="warranty_start"):
        service.update_serial(
            firm_scope=firm.id,
            actor_id=uuid4(),
            serial_id=unit.id,
            data=SerialUpdate(warranty_start=date(2026, 10, 1)),
        )


def test_a_lot_is_refused_an_expiry_its_product_does_not_track() -> None:
    """On the way in and on a later change; undated it is taken."""
    session = _session()
    firm = _firm(session, "FLD3")
    paint = _paint(session, firm)
    service = BatchSerialService(session)

    with pytest.raises(ValidationError, match="expiry_date"):
        service.create_lot(
            firm_scope=firm.id,
            actor_id=uuid4(),
            data=LotCreate(
                product_id=paint.id,
                lot_number="L-9",
                lot_type=LotType.PRODUCTION,
                quantity=5,
                expiry_date=date(2027, 1, 1),
            ),
        )
    lot = service.create_lot(
        firm_scope=firm.id,
        actor_id=uuid4(),
        data=LotCreate(
            product_id=paint.id,
            lot_number="L-9",
            lot_type=LotType.PRODUCTION,
            quantity=5,
        ),
    )
    with pytest.raises(ValidationError, match="expiry_date"):
        service.update_lot(
            firm_scope=firm.id,
            actor_id=uuid4(),
            lot_id=lot.id,
            data=LotUpdate(expiry_date=date(2027, 1, 1)),
        )


# ── What already exists can always be changed or removed ─────────────────────


def test_a_batch_outlives_its_products_switch() -> None:
    """Held, cleared and removed after the product stopped tracking.

    Refusing to quarantine a batch because its product's switch is off would
    be the fault, not the control.
    """
    session = _session()
    firm = _firm(session, "OUT1")
    medicine = _medicine(session, firm)
    service = BatchSerialService(session)
    actor = uuid4()
    batch = service.create_batch(
        firm_scope=firm.id,
        actor_id=actor,
        data=_batch(medicine, expiry_date=date(2027, 6, 30)),
    )
    medicine.track_batch = False
    medicine.track_expiry = False
    session.commit()

    # The form sends the date the batch already holds: nothing changes, so
    # nothing is judged.
    held = service.update_batch(
        firm_scope=firm.id,
        actor_id=actor,
        batch_id=batch.id,
        data=BatchUpdate(status=BatchStatus.QUARANTINE, expiry_date=date(2027, 6, 30)),
    )
    assert held.status == BatchStatus.QUARANTINE.value

    with pytest.raises(ValidationError, match="expiry_date"):
        service.update_batch(
            firm_scope=firm.id,
            actor_id=actor,
            batch_id=batch.id,
            data=BatchUpdate(expiry_date=date(2028, 1, 1)),
        )
    cleared = service.update_batch(
        firm_scope=firm.id,
        actor_id=actor,
        batch_id=batch.id,
        data=BatchUpdate(expiry_date=None),
    )
    assert cleared.expiry_date is None

    service.delete_batch(firm_scope=firm.id, actor_id=actor, batch_id=batch.id)
    assert session.get(BatchRecord, batch.id).is_deleted  # type: ignore[union-attr]


# ── A receipt ────────────────────────────────────────────────────────────────


def test_a_receipt_makes_the_batch_and_the_product_decides_what_it_carries() -> None:
    """Goods that arrived are receivable; the dates follow the switches."""
    session = _session()
    firm = _firm(session, "RCV1")
    service = BatchSerialService(session)
    untracked = _product(session, firm.id, "LOOSE-1")
    medicine = _medicine(session, firm)
    dated_only = _product(session, firm.id, "FOOD-1", track_expiry=True)

    # Not tracked by batch, and still received: the number typed is kept.
    loose = service.resolve_for_receipt(
        firm_scope=firm.id,
        actor_id=uuid4(),
        product_id=untracked.id,
        batch_number="R-1",
        manufacturing_date=date(2026, 1, 1),
        shelf_life_days=100,
    )
    assert (loose.manufacturing_date, loose.shelf_life_days) == (None, None)

    with pytest.raises(ValidationError, match="LOOSE-1 does not track expiry"):
        service.resolve_for_receipt(
            firm_scope=firm.id,
            actor_id=uuid4(),
            product_id=untracked.id,
            batch_number="R-2",
            expiry_date=date(2027, 1, 1),
        )

    full = service.resolve_for_receipt(
        firm_scope=firm.id,
        actor_id=uuid4(),
        product_id=medicine.id,
        batch_number="R-3",
        expiry_date=date(2027, 1, 1),
        manufacturing_date=date(2026, 1, 1),
        shelf_life_days=365,
    )
    assert (full.expiry_date, full.manufacturing_date, full.shelf_life_days) == (
        date(2027, 1, 1),
        date(2026, 1, 1),
        365,
    )

    partial = service.resolve_for_receipt(
        firm_scope=firm.id,
        actor_id=uuid4(),
        product_id=dated_only.id,
        batch_number="R-4",
        expiry_date=date(2027, 1, 1),
        manufacturing_date=date(2026, 1, 1),
        shelf_life_days=365,
    )
    assert (partial.manufacturing_date, partial.shelf_life_days) == (None, 365)


# ── The customer's shelf-life wish ───────────────────────────────────────────


def test_any_firm_may_record_a_customers_minimum_shelf_life() -> None:
    """It was refused without the firm's expiry feature (backlog 89, q. 3)."""
    session = _session()
    firm = _firm(session, "CUS1")
    service = CustomerService(session)
    actor = uuid4()

    customer = service.create(
        CustomerCreate(
            code="C-1",
            customer_type=CustomerType.BUSINESS,
            name="Careful Buyer",
            currency_code="INR",
            minimum_shelf_life_days=90,
        ),
        firm_id=firm.id,
        actor_id=actor,
    )
    assert customer.minimum_shelf_life_days == 90

    changed = service.update(
        customer.id,
        CustomerUpdate(
            code="C-1",
            customer_type=CustomerType.BUSINESS,
            name="Careful Buyer",
            currency_code="INR",
            minimum_shelf_life_days=120,
        ),
        firm_scope=firm.id,
        actor_id=actor,
    )
    assert changed.minimum_shelf_life_days == 120


# ── The guard ────────────────────────────────────────────────────────────────


def test_every_switch_named_is_a_real_product_column() -> None:
    """A switch renamed on the product must not turn a check into a crash."""
    columns = set(Product.__table__.columns.keys())
    named = {switch for switch, _, _ in FIELD_SWITCHES}
    for switches, _ in RECORD_SWITCHES.values():
        named.update(switches)
    assert named <= columns


def test_no_batch_or_serial_code_asks_the_firms_profile_about_a_product() -> None:
    """The six product-behaviour features are read nowhere under ``app``.

    ``BATCH_PTR_PTS`` stays a feature of the firm and is not in this list.
    The catalogue rows themselves, which only migrations and the seed scripts
    name, go in step 6.
    """
    from pathlib import Path

    app_root = Path(__file__).resolve().parents[2] / "app"
    offenders: list[str] = []
    for path in sorted(app_root.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for code in _OLD_CODES:
            if f'"{code}"' in text:
                offenders.append(f"{path.relative_to(app_root)}: {code}")
    assert offenders == []
