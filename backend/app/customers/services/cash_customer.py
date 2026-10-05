"""The firm's built-in *Cash sale* customer (backlog §87 #2, SG-2).

A counter sells to people who have no customer record and will never need
one. Tally bills them to *Cash*, Busy and Marg to a cash party: one account
that every such bill names, with the buyer's own name typed on the bill.

There is exactly one per firm, marked `is_cash_sale`, and it is made the
first time a counter asks for it -- so a firm that existed before this did
needs no backfill and a new firm no provisioning step. It is unregistered,
which is what places its bills in B2C; it takes no credit, so a bill to it
is paid in full when approved; and it cannot be deleted, registered for GST
or made inactive, because every walk-in bill ever raised names it.
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.common.firm_metadata import FirmMetadataReader
from app.core.exceptions import ValidationError
from app.customers.models import Customer

CASH_CUSTOMER_CODE = "CASH"
CASH_CUSTOMER_NAME = "Cash sale"


def find_cash_customer(session: Session, firm_id: UUID) -> Customer | None:
    """Return the firm's cash customer, if it has been made."""
    return session.scalar(
        select(Customer).where(
            Customer.firm_id == firm_id,
            Customer.is_cash_sale.is_(True),
            Customer.is_deleted.is_(False),
        )
    )


def stage_cash_customer(session: Session, firm_id: UUID, *, actor_id: UUID) -> Customer:
    """Return the firm's cash customer, making it if this is the first ask.

    Flushed, not committed: the caller owns the transaction. Two counters
    asking at once are settled by `UQ_customers_cash_sale_active`.
    """
    found = find_cash_customer(session, firm_id)
    if found is not None:
        return found
    taken = set(
        session.scalars(
            select(Customer.code).where(
                Customer.firm_id == firm_id,
                Customer.is_deleted.is_(False),
                Customer.code.like(f"{CASH_CUSTOMER_CODE}%"),
            )
        ).all()
    )
    code, suffix = CASH_CUSTOMER_CODE, 1
    while code in taken:
        suffix += 1
        code = f"{CASH_CUSTOMER_CODE}-{suffix}"
    customer = Customer(
        firm_id=firm_id,
        code=code,
        customer_type="INDIVIDUAL",
        name=CASH_CUSTOMER_NAME,
        display_name=CASH_CUSTOMER_NAME,
        currency_code=FirmMetadataReader(session).get(firm_id).currency_code or "INR",
        status="ACTIVE",
        is_cash_sale=True,
        created_by=actor_id,
        updated_by=actor_id,
    )
    session.add(customer)
    session.flush()
    record_audit(
        session,
        action="customer.cash_sale_created",
        entity_type="customer",
        entity_id=customer.id,
        actor_id=actor_id,
        firm_id=firm_id,
        after_data={"code": customer.code, "name": customer.name},
    )
    return customer


def assert_cash_customer_stays(customer: Customer, values: dict[str, object]) -> None:
    """Refuse an edit that would stop the cash customer being one.

    Args:
        customer: The customer being edited.
        values: The fields the edit sends, as dumped with ``exclude_unset``.

    Raises:
        ValidationError: When it would be given credit or a GSTIN, or made
            anything but active.

    """
    if not customer.is_cash_sale:
        return
    if Decimal(str(values.get("credit_limit") or 0)) > Decimal("0"):
        raise ValidationError(
            f"{customer.name} is the walk-in customer and takes no credit: "
            "its bills are paid in full at the counter."
        )
    if str(values.get("gst_number") or "").strip():
        raise ValidationError(
            f"{customer.name} is the walk-in customer and is unregistered. "
            "Bill a registered buyer to a customer record of its own."
        )
    status = values.get("status")
    if status is not None and getattr(status, "value", status) != "ACTIVE":
        raise ValidationError(
            f"{customer.name} is the walk-in customer and stays active."
        )


def assert_not_cash_customer(customer: Customer) -> None:
    """Refuse to delete the cash customer."""
    if customer.is_cash_sale:
        raise ValidationError(
            f"{customer.name} is the walk-in customer every counter bill "
            "without a customer record names; it cannot be deleted."
        )


__all__ = [
    "CASH_CUSTOMER_CODE",
    "CASH_CUSTOMER_NAME",
    "assert_cash_customer_stays",
    "assert_not_cash_customer",
    "find_cash_customer",
    "stage_cash_customer",
]
