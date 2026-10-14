"""The columns a line typed in boxes and pieces keeps (L5, step 1).

Declared once here, so the nine selling and buying line tables and their nine
headers cannot drift (``docs/design/BOX_AND_PIECE_LINE_DESIGN.md``, section
3.8). A line's quantity stays one figure in the stock unit; boxes and pieces
are worked out from it by the pack size the line was written at, and are never
stored. Nothing reads these columns yet.
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.types import UUIDType


class BoxAndPieceLineMixin:
    """The pack a line's quantity is shown in, as it was when written."""

    #: The pack's unit, for the word printed (BOX, CASE). Null on every line
    #: written before L5 and on a line of an item with no pack.
    pack_uom_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("uoms.id", ondelete="RESTRICT"), nullable=True
    )
    #: Stock units in one pack when the line was written. A line continuing
    #: another inherits it, so a later change of pack size never moves it.
    pack_size: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)


class BoxAndPieceEntryMixin:
    """Whether a header, a setting or a party opens with the box cells."""

    #: On a document: the layout it was saved in. On a firm's settings: the
    #: switch for that side. On a customer or supplier: their documents open
    #: with the box cells, read only where the firm's switch is on.
    box_and_piece_entry: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
