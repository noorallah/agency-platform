"""Whether a product may be sold: the status the master carries, enforced.

The product half of D-MST-6, recorded as D-MST-12. #562 taught the sales side
to read ``customers.status`` and left ``products.status`` unread, so a product
withdrawn from sale was still quoted, still ordered and still billed -- the
status column said INACTIVE and nothing anywhere asked it.

The rule is the customer's rule, applied to the other party to the line. A
product is refused where a **new** line naming it is typed: a quotation line, a
sales order line, and the bare lines of a bill raised without an order behind
it. A line **inherited** from a document already agreed is not refused -- an
order approved while the product was on sale is still delivered and still
billed, and a delivery note already dispatched is billed for what left the
warehouse. Withdrawing a product is how a firm stops selling more of it, not
how it walks away from what it has already promised.

Only ACTIVE sells. DRAFT is a product still being set up, INACTIVE one
withdrawn, and ARCHIVED one retired -- none of the three is something to put in
front of a customer.
"""

from __future__ import annotations

from app.core.exceptions import ValidationError
from app.products.models import Product

#: How each non-selling status reads in a refusal.
_STATUS_WORDS = {
    "DRAFT": "still a draft",
    "INACTIVE": "inactive",
    "ARCHIVED": "archived",
}


def assert_product_takes_new_lines(product: Product, *, document: str) -> None:
    """Refuse a new sales line for a product that is not ACTIVE.

    ``document`` is what is being raised, as it reads in a sentence -- "sales
    order", "quotation", "bill".
    """
    if product.status == "ACTIVE":
        return
    words = _STATUS_WORDS.get(product.status, product.status.lower())
    raise ValidationError(
        f"{product.code} ({product.name}) is {words}, so it cannot be put on "
        f"a new {document}. Set the product active first; lines already "
        "raised are not affected."
    )
