"""Where a customer or a supplier is, in the two words a picker shows.

Two shops of one name are told apart on a screen by their area and city
(first customer, row S3). The customer and vendor masters carry that with the
whole address; the money screens read neither master, so this answers the one
question for a page of ids and nothing more -- never a street line, a
registration or a balance.
"""

from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.core.utils.chunks import chunks
from app.customers.models import CustomerAddress
from app.sales.models import GeoCity, GeoLocality
from app.vendors.models import VendorAddress


def place_text(area: str | None, city: str | None) -> str:
    """Join an area and a city as "Area, City", leaving out what is blank."""
    parts = [part.strip() for part in (area, city) if part and part.strip()]
    return ", ".join(dict.fromkeys(parts))


def customer_places(session: Session, ids: Iterable[UUID]) -> dict[UUID, str]:
    """Return each customer's area and city, from the billing address.

    The default billing address speaks for the customer, and the oldest
    address where none is marked. A customer with no address, or none with a
    place, is left out.
    """
    places: dict[UUID, str] = {}
    for chunk in chunks(list(ids)):
        rows = session.execute(
            select(
                CustomerAddress.customer_id,
                CustomerAddress.area,
                CustomerAddress.city,
            )
            .where(
                CustomerAddress.customer_id.in_(chunk),
                CustomerAddress.is_deleted.is_(False),
            )
            .order_by(
                CustomerAddress.customer_id,
                case((CustomerAddress.is_default_billing.is_(True), 0), else_=1),
                CustomerAddress.created_at,
                CustomerAddress.id,
            )
        )
        for customer_id, area, city in rows:
            places.setdefault(customer_id, place_text(area, city))
    return {key: value for key, value in places.items() if value}


def vendor_places(session: Session, ids: Iterable[UUID]) -> dict[UUID, str]:
    """Return each supplier's area and city, from the primary address.

    A supplier's address holds ids into the geography masters, so the names
    are joined in. The primary address speaks for the supplier, and the
    oldest where none is marked.
    """
    places: dict[UUID, str] = {}
    for chunk in chunks(list(ids)):
        rows = session.execute(
            select(VendorAddress.vendor_id, GeoLocality.name, GeoCity.name)
            .outerjoin(GeoLocality, GeoLocality.id == VendorAddress.locality_id)
            .outerjoin(GeoCity, GeoCity.id == VendorAddress.city_id)
            .where(
                VendorAddress.vendor_id.in_(chunk),
                VendorAddress.is_deleted.is_(False),
            )
            .order_by(
                VendorAddress.vendor_id,
                case((VendorAddress.is_primary.is_(True), 0), else_=1),
                VendorAddress.created_at,
                VendorAddress.id,
            )
        )
        for vendor_id, area, city in rows:
            places.setdefault(vendor_id, place_text(area, city))
    return {key: value for key, value in places.items() if value}
