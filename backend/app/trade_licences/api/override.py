"""The licence override a sale's approval may carry (backlog 54).

Where the firm's policy blocks a sale for a licence nobody holds, the approval
may go ahead with a reason, given by someone holding
``TRADE_LICENCE_OVERRIDE``. The approve endpoints of the sales order, delivery
note and sales invoice take the reason as a query parameter -- their bodies
are empty and a body added for one optional field would change every caller --
and hand it to the service only once this has said the caller may give it.
"""

from typing import Annotated

from fastapi import Query

from app.common.scope import ResolvedFirmScope
from app.core.exceptions import AuthorizationError

OVERRIDE_PERMISSION = "TRADE_LICENCE_OVERRIDE"

LicenceOverrideReason = Annotated[
    str | None,
    Query(
        max_length=500,
        description=(
            "Why a sale the licence check blocks goes ahead anyway. Needs "
            "TRADE_LICENCE_OVERRIDE; recorded on the document's timeline."
        ),
    ),
]


def authorised_override(scope: ResolvedFirmScope, reason: str | None) -> str | None:
    """Return the reason if the caller may give one; refuse it otherwise."""
    if reason is None or not reason.strip():
        return None
    if not scope.principal.has_permission(OVERRIDE_PERMISSION):
        raise AuthorizationError(
            "Overriding the licence check needs the licence override permission."
        )
    return reason.strip()
