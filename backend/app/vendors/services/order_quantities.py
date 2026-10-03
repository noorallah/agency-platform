"""A supplier's minimum order and order multiple (BUY-5, decision A103).

Ordering 115 of something a supplier sells from 100 in twenties suggests
120. The catalogue row in force on the order's date says the minimum and the
multiple; a firm chooses whether a breach only warns (the default) or is
refused. The reorder planner rounds its suggestion the same way.
"""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_CEILING, Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.vendors.services.supplier_catalogue import current_rows

ZERO = Decimal("0")


@dataclass(frozen=True)
class QuantityHint:
    """One line ordered off the supplier's minimum or multiple."""

    line_number: int
    product_id: UUID
    quantity: Decimal
    minimum_order_quantity: Decimal | None
    order_multiple: Decimal | None
    suggested_quantity: Decimal

    def describe(self) -> str:
        """Say what is wrong with the line and what would do."""
        terms = []
        if self.minimum_order_quantity:
            terms.append(f"minimum {self.minimum_order_quantity.normalize():f}")
        if self.order_multiple:
            terms.append(f"in multiples of {self.order_multiple.normalize():f}")
        return (
            f"line {self.line_number}: {self.quantity.normalize():f} is off the "
            f"supplier's terms ({', '.join(terms)}); "
            f"{self.suggested_quantity.normalize():f} would do"
        )


def rounded_quantity(
    quantity: Decimal, *, minimum: Decimal | None, multiple: Decimal | None
) -> Decimal:
    """Raise a quantity to the minimum, then up to the next multiple."""
    rounded = quantity
    if minimum is not None and minimum > ZERO and rounded < minimum:
        rounded = minimum
    if multiple is not None and multiple > ZERO:
        rounded = (rounded / multiple).to_integral_value(ROUND_CEILING) * multiple
    return rounded


def quantity_hints(
    session: Session,
    *,
    firm_id: UUID,
    vendor_id: UUID,
    on: date,
    lines: list[tuple[int, UUID, Decimal]],
) -> list[QuantityHint]:
    """Return each ``(line_number, product_id, quantity)`` off the terms."""
    if not lines:
        return []
    terms = current_rows(
        session,
        firm_id=firm_id,
        vendor_id=vendor_id,
        product_ids=[product_id for _, product_id, _ in lines],
        on=on,
    )
    hints: list[QuantityHint] = []
    for line_number, product_id, quantity in lines:
        row = terms.get(product_id)
        if row is None or quantity <= ZERO:
            continue
        minimum = (
            None
            if row.minimum_order_quantity is None
            else Decimal(str(row.minimum_order_quantity))
        )
        multiple = (
            None if row.order_multiple is None else Decimal(str(row.order_multiple))
        )
        suggested = rounded_quantity(quantity, minimum=minimum, multiple=multiple)
        if suggested != quantity:
            hints.append(
                QuantityHint(
                    line_number=line_number,
                    product_id=product_id,
                    quantity=quantity,
                    minimum_order_quantity=minimum,
                    order_multiple=multiple,
                    suggested_quantity=suggested,
                )
            )
    return hints
