"""The columns of one arrangement applied to, or refused on, a sales line (L7).

Declared once here, so ``sales_order_offers`` and ``sales_quotation_offers``
cannot drift (``docs/design/OFFERS_ON_THE_BILL_LINE_DESIGN.md``, section 3.9).
A line's rows are rewritten each time it is priced and nothing refers to them
by id; its APPLIED rows add up to its discount and its offers' free goods.
The order and the quotation write them as each line is priced, through
``app/promotions/services/line_offers.py`` (L7 step 2).
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.types import UUIDType


class LineOfferMixin:
    """One offer, price list or standing rate, as it stood on a line."""

    #: No foreign key: `firms` lives only in the platform schema.
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    #: Order applied, lowest first.
    sequence: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    #: ``promotion``, ``price_list``, ``customer`` or ``customer_group``: the
    #: words a line's ``discount_source`` already uses.
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    #: The revision applied, and the offer's lasting identity: an edit makes
    #: a new revision, so the group is what names the offer.
    promotion_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("promotions.id", ondelete="RESTRICT"), nullable=True
    )
    promotion_group_id: Mapped[UUID | None] = mapped_column(UUIDType())
    price_list_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("price_lists.id", ondelete="RESTRICT"), nullable=True
    )
    #: As they read the day the line was priced.
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    #: ``APPLIED`` or ``REFUSED``.
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    #: True where a person decided it rather than the server.
    chosen: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    #: What this source took off the line.
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    #: Free stock units it gave.
    free_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    #: Given as a part share (section 3.7).
    part_share: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
