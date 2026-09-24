"""Walk a territory down `parent_id`, once, for everybody who needs it.

`SalesTerritoryService._subtree` (#574, for copying a hierarchy) and
`SalesTargetService._covered_by` (#581, for measuring a target on a region)
each walked the same relation breadth-first for the same answer. They were
written on branches that had not met, and neither knew about the other
(D-TER-18): two implementations of one rule is two places for the next
correction to be applied to only one of.

Down `parent_id` rather than by a `path LIKE '<prefix>%'`, which was tried and
is wrong twice over: it also takes a sibling whose code merely starts the same
way (`T-N` and `T-N2`), and `_` in a code is a wildcard to LIKE. Bounded by the
ids already seen, because `parent_id` is a plain column with no cycle check and
a cycle here would hang every save on the platform rather than fail one of them.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.sales.models import SalesTerritoryNode


def live_subtree(
    session: Session, *, firm_id: UUID, root: SalesTerritoryNode
) -> list[SalesTerritoryNode]:
    """Return the root and every live descendant, parents before children.

    Ordered within each generation by `sort_order` then `code`, which is the
    order a copy has to reproduce and the order the tree is drawn in.

    Args:
        session: The firm's session.
        firm_id: The owning firm -- the nodes live in the shared store, where
            an id is only an id.
        root: The node to start from. Returned first whether or not it is
            itself retired, because the caller has already decided it is the
            subject; only its descendants are filtered.

    Returns:
        The nodes, root first.

    """
    nodes = [root]
    seen = {root.id}
    frontier = [root.id]
    while frontier:
        children = [
            child
            for child in session.scalars(
                select(SalesTerritoryNode)
                .where(
                    SalesTerritoryNode.firm_id == firm_id,
                    SalesTerritoryNode.parent_id.in_(frontier),
                    SalesTerritoryNode.is_deleted.is_(False),
                )
                .order_by(
                    SalesTerritoryNode.sort_order.asc(),
                    SalesTerritoryNode.code.asc(),
                )
            )
            if child.id not in seen
        ]
        nodes.extend(children)
        seen.update(child.id for child in children)
        frontier = [child.id for child in children]
    return nodes


def covered_territory_ids(
    session: Session, *, firm_id: UUID, root_id: UUID
) -> frozenset[UUID]:
    """Return the ids a target on this node reaches: itself and its live tree.

    A document carries the node its customer is assigned to -- the route, at
    the bottom of the tree -- so a target matched on its own column alone
    achieved nothing on any level above it (D-TER-12).

    The node the target names is always its own, **even when it has been
    retired**: a target set on a round since withdrawn still says which one,
    and the achievement report still names it.

    Args:
        session: The firm's session.
        firm_id: The owning firm.
        root_id: The node the target names.

    Returns:
        The node's id and every live descendant's.

    """
    root = session.scalar(
        select(SalesTerritoryNode).where(
            SalesTerritoryNode.id == root_id,
            SalesTerritoryNode.firm_id == firm_id,
        )
    )
    if root is None:
        return frozenset({root_id})
    return frozenset(
        node.id for node in live_subtree(session, firm_id=firm_id, root=root)
    )
