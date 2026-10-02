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

Only ACTIVE and DISCONTINUED sell. DRAFT is a product still being set up,
INACTIVE one withdrawn, and ARCHIVED one retired -- none of the three is
something to put in front of a customer. DISCONTINUED is no longer *bought*
but is sold until the stock is gone (STK-17). A product marked *not for sale*
-- packing material, consumables -- is never sold whatever its status.
"""

from __future__ import annotations

from app.core.exceptions import ValidationError
from app.products.models import Product

#: The statuses a product is sold in.
SELLING_STATUSES = frozenset({"ACTIVE", "DISCONTINUED"})

#: How each non-selling status reads in a refusal.
_STATUS_WORDS = {
    "DRAFT": "still a draft",
    "INACTIVE": "inactive",
    "ARCHIVED": "archived",
}


def assert_product_takes_new_lines(product: Product, *, document: str) -> None:
    """Refuse a new sales line for a product that may not be sold.

    ``document`` is what is being raised, as it reads in a sentence -- "sales
    order", "quotation", "bill".
    """
    if product.not_for_sale:
        raise ValidationError(
            f"{product.code} ({product.name}) is marked not for sale, so it "
            f"cannot be put on a {document}. It is bought and stocked only; "
            "untick Not for sale on the product if it is to be sold."
        )
    if product.status in SELLING_STATUSES:
        return
    words = _STATUS_WORDS.get(product.status, product.status.lower())
    raise ValidationError(
        f"{product.code} ({product.name}) is {words}, so it cannot be put on "
        f"a new {document}. Set the product active first; lines already "
        "raised are not affected."
    )
