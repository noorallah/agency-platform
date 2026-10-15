"""Which sales order lines are a part share of an offer (design section 3.7).

A line given as a part share -- 5.5 charged and 0.5 free, six whole pieces --
is marked by a ``sales_order_offers`` row with ``part_share`` set. Half of
such a line is no number of pieces, so the note, the bill and the return that
continue it ask this once per document rather than once per line.
"""

from collections.abc import Collection
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.sales_order.models.sales_order import SalesOrderOffer


def part_share_order_lines(
    session: Session, *, firm_id: UUID, order_line_ids: Collection[UUID]
) -> set[UUID]:
    """Return the order lines among ``order_line_ids`` given as a part share.

    One statement however many lines are asked about; an empty question asks
    nothing.

    Args:
        session: The unit of work the document is being written in.
        firm_id: The firm the order lines belong to.
        order_line_ids: The order lines a document continues.

    Returns:
        The ids of those carrying a live part-share offer row.

    """
    ids = {line_id for line_id in order_line_ids if line_id is not None}
    if not ids:
        return set()
    rows = session.scalars(
        select(SalesOrderOffer.sales_order_line_id).where(
            SalesOrderOffer.firm_id == firm_id,
            SalesOrderOffer.part_share.is_(True),
            SalesOrderOffer.state == "APPLIED",
            SalesOrderOffer.is_deleted.is_(False),
            SalesOrderOffer.sales_order_line_id.in_(ids),
        )
    )
    return {line_id for line_id in rows if line_id is not None}
