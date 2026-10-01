"""Where a sale's goods go: the ship-to address a document names (backlog 67.3).

A customer keeps several addresses, and until this existed every order,
delivery note and invoice shipped -- on paper -- to the customer's one default
shipping address, whatever the buyer had asked for. Now the order names the
address (default shipping preselected), the delivery note inherits it from the
order and the invoice from the notes it bills, each overridable.

**The address must be the customer's own and live.** An address of another
customer, or one deleted, is refused by name: the ship-to is printed on the
challan the driver carries and, for an unregistered buyer, decides the place of
supply and so the tax (``app/tax/services/place_of_supply.py``).

**None means "the customer's default".** A document saved with no ship-to takes
the customer's default shipping address, then any SHIPPING address; a customer
with neither ships to the billing address, as before. There is no way to say
"ship nowhere", because there is no such thing.

The id is a bare reference with no foreign key, like every cross-document
reference in the sales chain: the address is validated here when it is set,
and a document printed after the address was deleted still prints it.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.customers.models import CustomerAddress


def default_shipping_address_id(session: Session, customer_id: UUID) -> UUID | None:
    """Return the address a customer's goods go to when nobody names one.

    The address marked default shipping, then any SHIPPING address -- the
    oldest, so the answer is stable -- else None.
    """
    rows = list(
        session.scalars(
            select(CustomerAddress)
            .where(
                CustomerAddress.customer_id == customer_id,
                CustomerAddress.is_deleted.is_(False),
            )
            .order_by(CustomerAddress.created_at.asc(), CustomerAddress.id.asc())
        ).all()
    )
    for row in rows:
        if row.is_default_shipping:
            return row.id
    for row in rows:
        if row.address_type == "SHIPPING":
            return row.id
    return None


def resolve_ship_to(
    session: Session, *, customer_id: UUID, address_id: UUID | None
) -> UUID | None:
    """Return the ship-to a document stores, refusing an address not the buyer's.

    Args:
        session: The tenant session the customer lives on.
        customer_id: The document's customer.
        address_id: The address named, or None for the customer's default.

    Returns:
        The address id to store, or None when the customer has no shipping
        address at all.

    Raises:
        ValidationError: If the address is not a live address of this customer.

    """
    if address_id is None:
        return default_shipping_address_id(session, customer_id)
    row = session.scalar(
        select(CustomerAddress).where(
            CustomerAddress.id == address_id,
            CustomerAddress.customer_id == customer_id,
            CustomerAddress.is_deleted.is_(False),
        )
    )
    if row is None:
        raise ValidationError(
            "The ship-to address must be one of this customer's own live "
            "addresses."
        )
    return row.id


def ship_to_is_valid(
    session: Session, *, customer_id: UUID, address_id: UUID | None
) -> bool:
    """Return whether a stored ship-to still names a live address of the buyer."""
    if address_id is None:
        return False
    return (
        session.scalar(
            select(CustomerAddress.id).where(
                CustomerAddress.id == address_id,
                CustomerAddress.customer_id == customer_id,
                CustomerAddress.is_deleted.is_(False),
            )
        )
        is not None
    )
