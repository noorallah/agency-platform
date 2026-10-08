"""What a product's own tracking switches allow on a batch, a lot or a serial.

The firm's business profile used to answer these questions: a firm on the
pharmacy profile was refused a serial number on anything, and a firm that added
a second line of goods had to change profile to date a batch. The product
answers them now (backlog 89). Its switches are filled from its goods type when
it is created and are the one place a person changes them, so the check reads a
row the caller already has and never the firm.

Two kinds of question are asked:

- **May this product have one at all** -- a batch, a lot, a serial number --
  asked when somebody adds one by hand. One that already exists can always be
  changed or removed: refusing to quarantine a batch because its product's
  switch is off would be the fault, not the control.
- **May it carry this field** -- an expiry date, a manufacturing date, a
  warranty -- asked of the fields a write actually fills. Blank is never
  refused, so a record can always be cleared.
"""

from collections.abc import Mapping
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.products.models import Product

#: The switch that owns each optional field, and how to name it to a person.
#: ``shelf_life_days`` and ``best_before_date`` are facts about expiry and
#: follow that switch; neither has one of its own.
FIELD_SWITCHES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "track_expiry",
        "expiry dates",
        ("expiry_date", "best_before_date", "shelf_life_days"),
    ),
    ("track_manufacturing_date", "manufacturing dates", ("manufacturing_date",)),
    ("track_warranty", "warranty", ("warranty_start", "warranty_end")),
)

#: What each record needs switched on before one is added by hand. A lot is a
#: subdivision of a batch-tracked product's stock, so either switch admits it.
RECORD_SWITCHES: dict[str, tuple[tuple[str, ...], str]] = {
    "batch": (("track_batch",), "batch"),
    "lot": (("track_lot", "track_batch"), "lot or batch"),
    "serial number": (("track_serial",), "serial number"),
}


def tracked_product(session: Session, firm_id: UUID, product_id: UUID) -> Product:
    """Return the firm's product a batch, lot or serial is being written for."""
    product = session.scalar(
        select(Product).where(
            Product.id == product_id,
            Product.firm_id == firm_id,
            Product.is_deleted.is_(False),
        )
    )
    if product is None:
        raise ResourceNotFoundError(f"Product {product_id} not found.")
    return product


def assert_product_keeps(product: Product, record: str) -> None:
    """Refuse a batch, lot or serial for a product that does not track one.

    Args:
        product: The product the record is for.
        record: ``batch``, ``lot`` or ``serial number``.

    Raises:
        ValidationError: If none of the switches that admit it is on.

    """
    switches, tracking = RECORD_SWITCHES[record]
    if any(getattr(product, switch) for switch in switches):
        return
    raise ValidationError(
        f"{product.code} is not tracked by {tracking}, so a {record} cannot be "
        f"added for it. Switch {tracking} tracking on for the product first."
    )


def assert_product_fields(product: Product, values: Mapping[str, object]) -> None:
    """Refuse a field the product's own switch does not allow.

    Only a field that is filled is judged; ``None`` clears and always passes.

    Args:
        product: The product the record is for.
        values: The fields being written, keyed by the name to report.

    Raises:
        ValidationError: If a filled field belongs to a switch that is off.

    """
    for switch, tracking, fields in FIELD_SWITCHES:
        if getattr(product, switch):
            continue
        filled = sorted(name for name in fields if values.get(name) is not None)
        if filled:
            raise ValidationError(
                f"{product.code} does not track {tracking}, so "
                f"{', '.join(filled)} cannot be set. Switch it on for the "
                "product first."
            )


def assert_date_order(
    *,
    manufacturing_date: date | None,
    expiry_date: date | None,
    best_before_date: date | None,
) -> None:
    """Refuse a batch that expires before it was made.

    A batch typed with the two dates the wrong way round was accepted, and
    the expiry monitor then called good stock years out of date (D-STK-23).
    The same day is allowed; a date left blank is not judged.

    Raises:
        ValidationError: If the expiry or best-before date is before the
            manufacturing date.

    """
    if manufacturing_date is None:
        return
    for label, value in (("expiry", expiry_date), ("best-before", best_before_date)):
        if value is not None and value < manufacturing_date:
            raise ValidationError(
                f"The {label} date {value.isoformat()} is before the "
                f"manufacturing date {manufacturing_date.isoformat()}. Check "
                "the two dates."
            )


def assert_expiry_stated(
    product: Product, *, batch_number: str, expiry_date: date | None
) -> None:
    """Refuse a batch with no expiry date where the product tracks expiry.

    A medicine taken in with a batch number and no date sat in stock as a
    batch that never came due: the expiry monitor passed over it and it was
    sold last instead of first (D-STK-48). The goods type says whether the
    date is kept at all; where it is, the batch has to carry one.

    Raises:
        ValidationError: If the product tracks expiry and no date is stated.

    """
    if not product.track_expiry or expiry_date is not None:
        return
    raise ValidationError(
        f"{product.code} tracks expiry, so batch {batch_number} needs an "
        "expiry date. Enter the expiry date, or the manufacturing date where "
        "the product has a shelf life."
    )
