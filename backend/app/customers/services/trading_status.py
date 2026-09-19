"""Whether a customer may be sold to: the status the master carries, enforced.

Nothing on the sales side read ``customers.status`` (D-MST-6). The delete
refusal tells the user to "set the customer inactive to stop trading with
them", and doing so stopped nothing: an order for an INACTIVE customer was
raised and approved. The purchase side has always checked its counterparty.

The rule is about **new** documents. A quotation, a sales order and a direct
bill are where a sale to a customer starts, and each is refused by name while
the customer is not ACTIVE. What is already in flight carries on -- an approved
order is still delivered and billed, and money is still collected -- because
marking a customer inactive is how a firm stops taking new business from them,
not how it abandons what it already owes and is owed.
"""

from __future__ import annotations

from app.core.exceptions import ValidationError
from app.customers.models import Customer

#: How each non-trading status reads in a refusal.
_STATUS_WORDS = {"INACTIVE": "inactive", "ON_HOLD": "on hold"}


def assert_customer_takes_new_documents(customer: Customer, *, document: str) -> None:
    """Refuse a new sales document for a customer who is not ACTIVE.

    ``document`` is what is being raised, as it reads in a sentence -- "sales
    order", "quotation".
    """
    if customer.status == "ACTIVE":
        return
    words = _STATUS_WORDS.get(customer.status, customer.status.lower())
    raise ValidationError(
        f"{customer.code} ({customer.display_name}) is {words}, so a new "
        f"{document} cannot be raised for them. Set the customer active "
        "first; documents already in flight are not affected."
    )
