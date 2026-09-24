"""Decide which territory, route and salesman a sales document belongs to.

Five documents carry `territory_id` / `salesman_id` (and, on three of them,
`route_id`), and until now nothing ever populated them: every seeded sales order
had all three NULL, so `/reports/by-territory`, `/reports/by-route` and
`/reports/by-salesman` answered `[]` from endpoints that were themselves
correct. The reporting chain was built and completely unfed.

This resolves them **server-side** rather than from a form field, because
server-side reaches every creation path at once -- the desktop, a direct API
call, and the demo seeder -- where a field only ever reaches the one screen that
grew it.

A plain function rather than a method on `SalesTerritoryService`: five domains
call it, and importing that service into each would make a cycle (it already
imports from `app.customers`). It is also 2,600 lines, which is not somewhere to
add a sixth caller's entry point.
"""

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.firm_metadata import FirmMetadataReader
from app.core.exceptions import ValidationError
from app.sales.models import (
    SalesTerritoryNode,
    TerritoryCustomerAssignment,
    TerritoryRouteProfile,
    TerritorySalesmanAssignment,
)


@dataclass(frozen=True)
class ResolvedSalesScope:
    """Where a document sits in the territory hierarchy.

    `route_id` is a `territory_route_profiles.id`, not a territory node id --
    that is what the three document columns reference. Quotations and sales
    returns have no `route_id` column and simply ignore it.
    """

    territory_id: UUID | None
    route_id: UUID | None
    salesman_id: UUID | None


def resolve_sales_scope(
    session: Session,
    *,
    firm_id: UUID,
    customer_id: UUID,
    territory_id: UUID | None = None,
    salesman_id: UUID | None = None,
    route_id: UUID | None = None,
    on_date: date | None = None,
) -> ResolvedSalesScope:
    """Resolve the territory, route and salesman for one document.

    What the caller sent is validated, never overridden: a user who picked a
    territory gets that territory or an error, because silently correcting it
    would put the document in a place the person who saved it cannot find. What
    the caller left blank is derived from the customer's assignments.

    Derivation is deliberately conservative. A customer assigned to several
    territories with none marked primary resolves to nothing rather than to the
    first row the database happens to return -- the whole reason these fields
    exist is to make the reports true, and a guess makes them confidently
    wrong.
    """
    resolved_territory = (
        _validated_territory(session, firm_id, customer_id, territory_id)
        if territory_id is not None
        else _derived_territory(session, customer_id)
    )
    resolved_salesman = (
        _validated_salesman(session, firm_id, resolved_territory, salesman_id)
        if salesman_id is not None
        else _derived_salesman(session, firm_id, resolved_territory)
    )
    return ResolvedSalesScope(
        territory_id=resolved_territory,
        # A caller who named a route keeps it once it has been checked: this
        # firm's, in force on the document's date, and a round this customer
        # is on. Callers that have no `route_id` column pass nothing and
        # always get the derived one.
        route_id=(
            validate_named_route(
                session,
                firm_id=firm_id,
                customer_id=customer_id,
                territory_id=resolved_territory,
                route_id=route_id,
                on_date=on_date,
            )
            if route_id is not None
            else _route_profile_for(session, resolved_territory, on_date)
        ),
        salesman_id=resolved_salesman,
    )


def validate_named_route(
    session: Session,
    *,
    firm_id: UUID,
    customer_id: UUID,
    territory_id: UUID | None,
    route_id: UUID,
    on_date: date | None,
) -> UUID:
    """Accept a caller's route only if the document can honestly carry it.

    Three things, each refused by name (D-TER-9). The profile must be a live
    round on one of **this firm's** nodes -- in the shared store an id is
    just an id, and nothing else stopped one firm tagging its sales with
    another's round. It must have been **in force on the document's date**,
    the same window `_route_profile_for` applies to a blank; a window
    enforced only on what nobody typed is not enforced. And it must be a
    round this document **belongs to**: the resolved territory or one above
    it when the document has a territory, otherwise a round the customer is
    on or one above that. A route above the leaf reaches the document the
    way an inherited one does.

    Args:
        session: The firm's session.
        firm_id: The owning firm.
        customer_id: The customer on the document.
        territory_id: The document's territory, already validated or
            derived, or None when it has none.
        route_id: The `territory_route_profiles.id` the caller sent.
        on_date: The document's own date, or None when it has none.

    Returns:
        The route id, unchanged.

    Raises:
        ValidationError: If the route fails any of the three tests.

    """
    profile = session.scalar(
        select(TerritoryRouteProfile).where(
            TerritoryRouteProfile.id == route_id,
            TerritoryRouteProfile.is_deleted.is_(False),
        )
    )
    node = (
        None
        if profile is None
        else session.scalar(
            select(SalesTerritoryNode).where(
                SalesTerritoryNode.id == profile.territory_id,
                SalesTerritoryNode.firm_id == firm_id,
                SalesTerritoryNode.is_deleted.is_(False),
            )
        )
    )
    if profile is None or node is None:
        raise ValidationError("The selected route does not belong to this firm.")
    if not route_profile_in_force(profile, on_date):
        when = on_date.isoformat() if on_date is not None else "that date"
        raise ValidationError(
            f"Route {node.code} was not in force on {when}. Leave the route "
            "blank to use the one the customer is on."
        )
    anchors = (
        [territory_id]
        if territory_id is not None
        else list(
            session.scalars(
                select(TerritoryCustomerAssignment.territory_id).where(
                    TerritoryCustomerAssignment.customer_id == customer_id,
                    TerritoryCustomerAssignment.is_deleted.is_(False),
                )
            )
        )
    )
    reachable: set[UUID] = set()
    for anchor in anchors:
        reachable.add(anchor)
        reachable.update(_ancestors(session, anchor))
    if node.id not in reachable:
        raise ValidationError(
            f"Route {node.code} does not cover this customer"
            + (" on the selected territory" if territory_id is not None else "")
            + ". Put them on that round first, or leave the route blank to use "
            "the one they are on."
        )
    return route_id


def _validated_territory(
    session: Session, firm_id: UUID, customer_id: UUID, territory_id: UUID
) -> UUID:
    """Accept a caller's territory only if it is one the customer is on."""
    node = session.scalar(
        select(SalesTerritoryNode).where(
            SalesTerritoryNode.id == territory_id,
            SalesTerritoryNode.firm_id == firm_id,
            SalesTerritoryNode.is_deleted.is_(False),
        )
    )
    if node is None:
        raise ValidationError("The selected territory does not belong to this firm.")
    if node.status != "ACTIVE":
        # Closed to new business, open to history: the documents already
        # tagged with it stand, and nothing new may name it (D-TER-21).
        raise ValidationError(
            f"{node.code} is {node.status.lower()}, so it takes no new "
            "documents. Reactivate it, or leave the territory blank."
        )
    assigned = session.scalar(
        select(TerritoryCustomerAssignment.id).where(
            TerritoryCustomerAssignment.territory_id == territory_id,
            TerritoryCustomerAssignment.customer_id == customer_id,
            TerritoryCustomerAssignment.is_deleted.is_(False),
        )
    )
    if assigned is None:
        raise ValidationError(
            f"This customer is not assigned to {node.code}. "
            "Put them on that territory first, or leave it blank to use the "
            "one they are already on."
        )
    return territory_id


def _derived_territory(session: Session, customer_id: UUID) -> UUID | None:
    """Derive the customer's territory, when there is one obvious answer."""
    # Only a live, ACTIVE round: `sales_territories.status` was read by
    # nothing, so a round switched off went on tagging every new sale
    # (D-TER-21). A customer whose only round is inactive is on no round
    # for new business, which is what deactivating it means.
    assignments = list(
        session.scalars(
            select(TerritoryCustomerAssignment)
            .join(
                SalesTerritoryNode,
                SalesTerritoryNode.id == TerritoryCustomerAssignment.territory_id,
            )
            .where(
                TerritoryCustomerAssignment.customer_id == customer_id,
                TerritoryCustomerAssignment.is_deleted.is_(False),
                SalesTerritoryNode.is_deleted.is_(False),
                SalesTerritoryNode.status == "ACTIVE",
            )
        )
    )
    if not assignments:
        return None
    primary = [row for row in assignments if row.is_primary]
    if len(primary) == 1:
        return primary[0].territory_id
    if not primary and len(assignments) == 1:
        return assignments[0].territory_id
    # Several rounds call this shop and none is marked primary -- a distributor
    # visiting the same outlet on a sales beat and a collection round is the
    # ordinary case, not a misconfiguration. Nothing here can say which one the
    # document belongs to, so it says nothing.
    return None


def _validated_salesman(
    session: Session, firm_id: UUID, territory_id: UUID | None, salesman_id: UUID
) -> UUID:
    """Accept a caller's salesman only if they work here and cover the territory.

    Membership first, because it is the question that has an answer whether or
    not the firm runs territories: the order, the delivery note and the invoice
    each asked it in their own service, and the quotation and the sales return
    -- which do not -- took **any id at all** whenever the customer was on no
    territory (D-TER-15). Asking it here asks it once, for all five.

    Coverage is still only checkable against a territory. With none, the
    caller's choice stands: refusing would block a firm that records who sold
    without running territories at all.
    """
    if not FirmMetadataReader(session).active_member_count(firm_id, [salesman_id]):
        raise ValidationError("Salesman is not an active member of this firm.")
    if territory_id is None:
        return salesman_id
    if not _covers(session, territory_id, salesman_id):
        raise ValidationError(
            "The selected salesperson is not assigned to this territory."
        )
    return salesman_id


def _derived_salesman(
    session: Session, firm_id: UUID, territory_id: UUID | None
) -> UUID | None:
    """Derive the territory's salesperson, when there is one obvious answer.

    Only among the firm's **active members**. Deleting a user or ending a
    membership touches no firm store, so `territory_salesman_assignments`
    keeps them, and an order used to be created and approved in the name of
    somebody who had left -- its delivery note, which does check, was then
    refused (D-TER-11). A person who has gone is skipped here as though
    their row were retired: the round's other assignee, or the inheriting
    manager, or nobody.
    """
    if territory_id is None:
        return None
    direct = _still_here(
        session,
        firm_id,
        list(
            session.scalars(
                select(TerritorySalesmanAssignment).where(
                    TerritorySalesmanAssignment.territory_id == territory_id,
                    TerritorySalesmanAssignment.is_deleted.is_(False),
                )
            )
        ),
    )
    primary = [row for row in direct if row.is_primary]
    if len(primary) == 1:
        return primary[0].user_id
    if not primary and len(direct) == 1:
        return direct[0].user_id
    if direct:
        # Two people share the round with neither marked primary. Same reasoning
        # as the territory above: name nobody rather than the wrong one.
        return None
    return _inherited_salesman(session, firm_id, territory_id)


def _still_here(
    session: Session, firm_id: UUID, rows: list[TerritorySalesmanAssignment]
) -> list[TerritorySalesmanAssignment]:
    """Keep only the assignments whose person is still an active member.

    Through `FirmMetadataReader`, because `users` and `user_firms` live only
    in the platform store and a tenant session cannot see them.
    """
    if not rows:
        return rows
    members = {
        member.user_id for member in FirmMetadataReader(session).active_members(firm_id)
    }
    return [row for row in rows if row.user_id in members]


def _inherited_salesman(
    session: Session, firm_id: UUID, territory_id: UUID
) -> UUID | None:
    """Walk up for an ancestor whose salesperson covers their children."""
    for ancestor_id in _ancestors(session, territory_id):
        covering = _still_here(
            session,
            firm_id,
            list(
                session.scalars(
                    select(TerritorySalesmanAssignment).where(
                        TerritorySalesmanAssignment.territory_id == ancestor_id,
                        TerritorySalesmanAssignment.include_children.is_(True),
                        TerritorySalesmanAssignment.is_deleted.is_(False),
                    )
                )
            ),
        )
        primary = [row for row in covering if row.is_primary]
        if len(primary) == 1:
            return primary[0].user_id
        if len(covering) == 1:
            return covering[0].user_id
        if covering:
            return None
    return None


def _covers(session: Session, territory_id: UUID, user_id: UUID) -> bool:
    """Report whether a salesperson covers this territory, directly or by descent."""
    direct = session.scalar(
        select(TerritorySalesmanAssignment.id).where(
            TerritorySalesmanAssignment.territory_id == territory_id,
            TerritorySalesmanAssignment.user_id == user_id,
            TerritorySalesmanAssignment.is_deleted.is_(False),
        )
    )
    if direct is not None:
        return True
    for ancestor_id in _ancestors(session, territory_id):
        inherited = session.scalar(
            select(TerritorySalesmanAssignment.id).where(
                TerritorySalesmanAssignment.territory_id == ancestor_id,
                TerritorySalesmanAssignment.user_id == user_id,
                TerritorySalesmanAssignment.include_children.is_(True),
                TerritorySalesmanAssignment.is_deleted.is_(False),
            )
        )
        if inherited is not None:
            return True
    return False


def _route_profile_for(
    session: Session, territory_id: UUID | None, on_date: date | None
) -> UUID | None:
    """Find the route profile on this node, or the nearest ancestor that is a route.

    A firm whose hierarchy puts the round above the leaf still gets a route on
    its documents, which is what `/reports/by-route` reads.

    A round that was not running on the document's date is skipped. The
    effective window says when the round operates, and tagging a sale with a
    route that had already ended is the kind of row that makes a report look
    right and be wrong. With no date to judge by, the profile stands: a caller
    that cannot say when the document is dated is not evidence the route was
    closed.
    """
    if territory_id is None:
        return None
    for node_id in (territory_id, *_ancestors(session, territory_id)):
        if not _node_is_active(session, node_id):
            # An inactive round's route is not a round any more (D-TER-21).
            continue
        profile = session.scalar(
            select(TerritoryRouteProfile).where(
                TerritoryRouteProfile.territory_id == node_id,
                TerritoryRouteProfile.is_deleted.is_(False),
            )
        )
        if profile is not None and route_profile_in_force(profile, on_date):
            return profile.id
    return None


def _node_is_active(session: Session, node_id: UUID) -> bool:
    """Whether a territory node is live and ACTIVE."""
    status = session.scalar(
        select(SalesTerritoryNode.status).where(
            SalesTerritoryNode.id == node_id,
            SalesTerritoryNode.is_deleted.is_(False),
        )
    )
    return status == "ACTIVE"


def route_profile_in_force(
    profile: TerritoryRouteProfile, on_date: date | None
) -> bool:
    """Report whether a round was operating on a date.

    `effective_from` / `effective_to` were stored and returned from the first
    migration and read nowhere -- unlike UOM conversion rules and tax profiles,
    which both filter on theirs. A route "effective until June" still appeared
    everywhere and was still called by a beat plan. This is the one place that
    decides it, so both the call list and document tagging agree.
    """
    if on_date is None:
        return True
    if profile.effective_from is not None and on_date < profile.effective_from:
        return False
    return not (profile.effective_to is not None and on_date > profile.effective_to)


def _ancestors(session: Session, territory_id: UUID) -> list[UUID]:
    """List parent ids from the node upwards, nearest first.

    Bounded by the number of nodes walked rather than trusting the tree to be
    acyclic: `parent_id` is a plain column, and a cycle here would hang every
    save on the platform rather than fail one of them.
    """
    seen: set[UUID] = {territory_id}
    chain: list[UUID] = []
    current = territory_id
    while len(chain) < 32:
        parent_id = session.scalar(
            select(SalesTerritoryNode.parent_id).where(
                SalesTerritoryNode.id == current,
                SalesTerritoryNode.is_deleted.is_(False),
            )
        )
        if parent_id is None or parent_id in seen:
            break
        seen.add(parent_id)
        chain.append(parent_id)
        current = parent_id
    return chain
