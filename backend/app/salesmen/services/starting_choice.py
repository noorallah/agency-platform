"""What the Salesman box starts on (P2, salesman list design section 5).

On a new order, delivery note or bill the screen asks once, when the customer
is chosen, and fills the box with the answer:

1. the active entry tied to the signed-in user;
2. otherwise the customer's account manager;
3. otherwise the primary salesman of the customer's round;
4. otherwise nobody.

Steps 2 and 3 are `resolve_sales_scope`'s own fill, asked through the helper
it uses (`customer_salesman`), so the box shows what the server would fill.
An inactive entry is never answered.

A module of its own rather than a method on `SalesmanService`: the territory
resolver imports `app.salesmen.services.nameable`, whose package imports that
service, so the service importing the resolver back would be a cycle.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ResourceNotFoundError
from app.customers.models import Customer
from app.sales.services.scope_resolution import customer_salesman
from app.salesmen.models import Salesman
from app.salesmen.schemas import SalesmanStartingChoice


def starting_choice(
    session: Session,
    *,
    firm_id: UUID,
    user_id: UUID,
    customer_id: UUID | None = None,
) -> SalesmanStartingChoice:
    """Return the salesman a new document's box starts on, and why.

    Args:
        session: The firm's own store; nothing is written.
        firm_id: The firm the document is for.
        user_id: The signed-in user.
        customer_id: The customer chosen, or None before one is.

    Returns:
        The entry and its source; ``NONE`` with nulls when nothing applies.

    Raises:
        ResourceNotFoundError: The customer is not one of this firm's.

    """
    own = session.scalar(
        select(Salesman).where(
            Salesman.firm_id == firm_id,
            Salesman.user_id == user_id,
            Salesman.is_deleted.is_(False),
            Salesman.is_active.is_(True),
        )
    )
    if own is not None:
        return SalesmanStartingChoice(salesman_id=own.id, name=own.name, source="USER")
    if customer_id is not None:
        found = session.scalar(
            select(Customer.id).where(
                Customer.id == customer_id,
                Customer.firm_id == firm_id,
                Customer.is_deleted.is_(False),
            )
        )
        if found is None:
            raise ResourceNotFoundError("Customer not found.")
        salesman_id, source = customer_salesman(session, firm_id, customer_id)
        entry = (
            session.scalar(
                select(Salesman).where(
                    Salesman.id == salesman_id,
                    Salesman.firm_id == firm_id,
                    Salesman.is_deleted.is_(False),
                    Salesman.is_active.is_(True),
                )
            )
            if salesman_id is not None
            else None
        )
        if entry is not None and source != "NONE":
            return SalesmanStartingChoice(
                salesman_id=entry.id, name=entry.name, source=source
            )
    return SalesmanStartingChoice(salesman_id=None, name=None, source="NONE")
