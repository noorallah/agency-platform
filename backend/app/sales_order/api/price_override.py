"""The price-floor override a sale's approval may carry (backlog 64 row 2).

Where the firm's policy refuses a sale below cost or below a product's minimum
price, the approval may go ahead with a reason, given by someone holding
``SALES_PRICE_OVERRIDE``. Taken as a query parameter on the sales order and
sales invoice approve endpoints, as the licence override is
(``app/trade_licences/api/override.py``), and handed to the service only once
this has said the caller may give it.
"""

from typing import Annotated

from fastapi import Query

from app.common.scope import ResolvedFirmScope
from app.core.exceptions import AuthorizationError

PRICE_OVERRIDE_PERMISSION = "SALES_PRICE_OVERRIDE"

PriceOverrideReason = Annotated[
    str | None,
    Query(
        max_length=500,
        description=(
            "Why a sale below its floor price goes ahead anyway. Needs "
            "SALES_PRICE_OVERRIDE; recorded on the document's timeline."
        ),
    ),
]


def authorised_price_override(
    scope: ResolvedFirmScope, reason: str | None
) -> str | None:
    """Return the reason if the caller may give one; refuse it otherwise."""
    if reason is None or not reason.strip():
        return None
    if not scope.principal.has_permission(PRICE_OVERRIDE_PERMISSION):
        raise AuthorizationError(
            "Selling below the floor price needs the price override permission."
        )
    return reason.strip()
