"""The answer to "no stock in any lot -- bill anyway?" (L2 step 7a).

A firm costing by lot that allows billing without stock asks the bill maker
before units no lot holds leave (``docs/design/LOT_COST_DESIGN.md``, section
3.7). The server asks; a client that does not confirm is refused, with
``details.confirm`` = ``BILL_WITHOUT_STOCK``. Taken as a query parameter on
every action that dispatches by hand or approves a bill that ships, as the
licence and price overrides are: those actions have no body.
"""

from typing import Annotated

from fastapi import Query

BillWithoutStock = Annotated[
    bool,
    Query(
        description=(
            "Confirms billing units no lot holds, where the firm allows it. "
            "Without it such a sale is refused with the question."
        ),
    ),
]
