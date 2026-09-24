"""One walk down `parent_id`, and both callers take it.

D-TER-18. `SalesTerritoryService._subtree` (#574, for copying a hierarchy) and
`SalesTargetService._covered_by` (#581, for measuring a target on a region)
each walked the same relation breadth-first for the same answer; they were
written on branches that had not met. Two implementations of one rule is two
places for the next correction to be applied to only one of, so what this file
pins is the shared walk's behaviour **and** that neither caller has grown its
own again.

The cases are the ones the `path LIKE '<prefix>%'` this replaced got wrong: a
sibling whose code merely starts the same way (`T-N` beside `T-N2`), and `_`
in a code, which is a wildcard to LIKE.
"""

import ast
from datetime import date
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.core.database.all_models  # noqa: F401
from app.core.database.base import Base
from app.firms.models import Firm
from app.sales.models import SalesTerritoryNode
from app.sales.services.territory_tree import covered_territory_ids, live_subtree

_SOURCES = (
    Path(__file__).resolve().parents[1].parent
    / "app"
    / "sales"
    / "services"
    / "territory_service.py",
    Path(__file__).resolve().parents[1].parent
    / "app"
    / "sales_targets"
    / "services"
    / "sales_target_service.py",
)


def _session() -> Session:
    """Build one in-memory schema holding every table."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _firm(session: Session, code: str) -> Firm:
    """Create one firm."""
    row = Firm(
        code=code,
        name=f"Firm {code}",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(row)
    session.commit()
    return row


def _node(
    session: Session,
    *,
    firm_id: UUID,
    code: str,
    parent: SalesTerritoryNode | None = None,
    sort_order: int = 0,
) -> SalesTerritoryNode:
    """Write one node under its parent, with the path the tree keeps."""
    row = SalesTerritoryNode(
        firm_id=firm_id,
        hierarchy_level_id=uuid4(),
        parent_id=parent.id if parent else None,
        code=code,
        name=f"{code} node",
        path=code if parent is None else f"{parent.path}/{code}",
        sort_order=sort_order,
    )
    session.add(row)
    session.commit()
    return row


def test_the_walk_takes_the_children_and_not_a_look_alike_sibling() -> None:
    """`T-N2` and `T_N` are what a `path LIKE 'T-N%'` swept in."""
    session = _session()
    firm = _firm(session, "TREE")
    region = _node(session, firm_id=firm.id, code="T-N")
    city = _node(session, firm_id=firm.id, code="T-N-CITY", parent=region)
    route = _node(session, firm_id=firm.id, code="T-N-CITY-A", parent=city)
    sibling = _node(session, firm_id=firm.id, code="T-N2")
    _node(session, firm_id=firm.id, code="T-N2-C", parent=sibling)
    _node(session, firm_id=firm.id, code="T_N")

    walked = live_subtree(session, firm_id=firm.id, root=region)

    assert [node.code for node in walked] == ["T-N", "T-N-CITY", "T-N-CITY-A"]
    assert covered_territory_ids(session, firm_id=firm.id, root_id=region.id) == {
        region.id,
        city.id,
        route.id,
    }


def test_the_walk_orders_each_generation_and_skips_retired_children() -> None:
    """`sort_order` then `code`, which is the order a copy has to reproduce."""
    session = _session()
    firm = _firm(session, "ORDER")
    region = _node(session, firm_id=firm.id, code="R")
    _node(session, firm_id=firm.id, code="B", parent=region, sort_order=1)
    _node(session, firm_id=firm.id, code="A", parent=region, sort_order=2)
    gone = _node(session, firm_id=firm.id, code="C", parent=region, sort_order=3)
    gone.is_deleted = True
    session.commit()

    assert [
        node.code for node in live_subtree(session, firm_id=firm.id, root=region)
    ] == [
        "R",
        "B",
        "A",
    ]


def test_a_cycle_in_a_plain_column_does_not_walk_for_ever() -> None:
    """`parent_id` has no cycle check, and a hang would take the platform."""
    session = _session()
    firm = _firm(session, "CYCLE")
    first = _node(session, firm_id=firm.id, code="A")
    second = _node(session, firm_id=firm.id, code="B", parent=first)
    first.parent_id = second.id
    session.commit()

    assert {
        node.code for node in live_subtree(session, firm_id=firm.id, root=first)
    } == {
        "A",
        "B",
    }


def test_a_target_on_a_node_since_retired_still_names_it() -> None:
    """A target set on a round since withdrawn still says which one.

    The root is its own whether or not it is live; only the descendants are
    filtered.
    """
    session = _session()
    firm = _firm(session, "GONE")
    region = _node(session, firm_id=firm.id, code="R")
    region.is_deleted = True
    session.commit()

    assert covered_territory_ids(session, firm_id=firm.id, root_id=region.id) == {
        region.id
    }
    unknown = uuid4()
    assert covered_territory_ids(session, firm_id=firm.id, root_id=unknown) == {unknown}


def test_neither_service_walks_parent_id_for_itself() -> None:
    """The guard that matters: no third copy, and no second one coming back.

    Read as an AST rather than grepped, so a mention of `parent_id` in a
    comment or a docstring is not a finding. Both services still *read*
    `parent_id` -- to reparent a node, to walk upwards -- so what is pinned is
    the loop: a `while` whose body selects on `parent_id`, which is what a
    breadth-first walk down the tree looks like here.
    """
    for source in _SOURCES:
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for loop in ast.walk(tree):
            if not isinstance(loop, ast.While):
                continue
            body = ast.unparse(loop)
            assert "parent_id.in_(" not in body, (
                f"{source.name} has grown its own subtree walk again -- "
                "app/sales/services/territory_tree.py is the one (D-TER-18)."
            )
